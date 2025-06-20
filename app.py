from flask import Flask, redirect, request, session, url_for, render_template, render_template_string
import os
import datetime
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
from apscheduler.schedulers.background import BackgroundScheduler
from storage import upload_file_to_supabase, list_user_files
from gmail import check_and_download_attachments
from models import db, init_db, save_user_tokens, get_all_user_tokens
from base64 import urlsafe_b64decode
from datetime import datetime, timezone
import io
import mimetypes
import pytz
import pandas as pd
from functools import wraps

# --- Flask App Initialization ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-dev-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
db.init_app(app)

with app.app_context():
    db.create_all()

# --- Auth Config ---
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid'
]
CLIENT_SECRETS_FILE = 'client_secret.json'

# --- Login Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# --- Gmail Service Factory ---
def get_gmail_service():
    credentials_data = session.get('credentials')
    if not credentials_data:
        raise Exception("❌ No credentials found in session.")

    creds = google.oauth2.credentials.Credentials(**credentials_data)
    return googleapiclient.discovery.build('gmail', 'v1', credentials=creds)

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/authorize')
def authorize():
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES
    )
    flow.redirect_uri = url_for('oauth2callback', _external=True)
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    session.permanent = True
    session['state'] = state
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES
    )
    flow.redirect_uri = url_for('oauth2callback', _external=True)

    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ Token fetch failed: {str(e)}", 400

    credentials = flow.credentials

    if not credentials or not credentials.valid:
        return "❌ Invalid or missing credentials.", 401

    try:
        userinfo_service = googleapiclient.discovery.build(
            'oauth2', 'v2', credentials=credentials
        )
        userinfo = userinfo_service.userinfo().get().execute()
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ Failed to fetch user info: {str(e)}", 401

    email = userinfo.get('email')
    if not email:
        return "❌ Email not found in user info.", 400

    save_user_tokens(email, credentials)
    session['email'] = email
    session['credentials'] = credentials_to_dict(credentials)
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    service = get_gmail_service()
    user_email = session.get('email')

    query = 'has:attachment after:2025/06/13'
    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get('messages', [])

    previews = []

    for msg in messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
        internal_date = int(msg_data.get('internalDate')) / 1000
        email_datetime = datetime.fromtimestamp(internal_date, tz=timezone.utc)

        if email_datetime >= datetime(2025, 6, 13, tzinfo=timezone.utc):
            parts = msg_data.get('payload', {}).get('parts', [])
            for part in parts:
                filename = part.get('filename', '')
                if filename.endswith('.csv') or filename.endswith('.xlsx'):
                    att_id = part['body'].get('attachmentId')
                    attachment = service.users().messages().attachments().get(userId='me', messageId=msg['id'], id=att_id).execute()
                    data = urlsafe_b64decode(attachment['data'].encode('UTF-8'))

                    try:
                        if filename.endswith('.csv'):
                            df = pd.read_csv(io.BytesIO(data))
                        else:
                            df = pd.read_excel(io.BytesIO(data))

                        html_table = df.to_html(classes='table table-bordered', index=False)
                        previews.append({'filename': filename, 'table': html_table})
                    except Exception as e:
                        previews.append({'filename': filename, 'table': f"<p>Could not parse file: {e}</p>"})

    return render_template_string("""
        <h2>Hello {{ email }}</h2>
        <h3>Attachment Previews (since 13 June 2025):</h3>
        {% if previews %}
            {% for preview in previews %}
                <h4>{{ preview.filename }}</h4>
                <div>{{ preview.table|safe }}</div>
                <hr>
            {% endfor %}
        {% else %}
            <p>No CSV or Excel attachments found since 13 June 2025.</p>
        {% endif %}
    """, email=user_email, previews=previews)

# --- Background Job ---
def job():
    print("[Job] Checking inboxes...")
    users = get_all_user_tokens()
    for user in users:
        check_and_download_attachments(user)

scheduler = BackgroundScheduler()
scheduler.add_job(job, 'interval', minutes=5)
scheduler.start()

# --- Utility ---
def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
