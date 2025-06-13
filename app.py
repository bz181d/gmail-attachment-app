from flask import Flask, redirect, request, session, url_for, render_template
import os
import datetime
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
from apscheduler.schedulers.background import BackgroundScheduler
from storage import upload_file_to_supabase, list_user_files
from gmail import check_and_download_attachments
from models import db, init_db, save_user_tokens, get_all_user_tokens

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-dev-secret')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
db.init_app(app)


with app.app_context():
    db.create_all()


SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid'
]
CLIENT_SECRETS_FILE = 'client_secret.json'

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
    session.permanent = True  # <-- Add this
    session['state'] = state
    return redirect(auth_url)


"""
@app.route('/oauth2callback')
def oauth2callback():
    state = session.get('state')
    if not state:
        return "Session state missing. Try logging in again.", 400

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state
    )
    flow.redirect_uri = url_for('oauth2callback', _external=True)

    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        return f"Token fetch failed: {str(e)}", 400

    credentials = flow.credentials

    if not credentials or not credentials.valid:
        return "Invalid or missing credentials.", 401

    # Ensure all required fields are present
    if not (credentials.token and credentials.refresh_token and credentials.client_id and credentials.client_secret):
        return "Incomplete credentials. Try again with consent screen.", 401

    try:
        userinfo_service = googleapiclient.discovery.build(
            'oauth2', 'v2', credentials=credentials
        )
        userinfo = userinfo_service.userinfo().get().execute()
    except Exception as e:
        return f"Failed to fetch user info: {str(e)}", 401

    email = userinfo['email']

    save_user_tokens(email, credentials)
    session['email'] = email
    return redirect(url_for('dashboard'))
"""

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
    return redirect(url_for('dashboard'))



@app.route('/dashboard')
def dashboard():
    if 'email' not in session:
        return redirect(url_for('index'))
    email = session['email']
    files = list_user_files(email)
    return render_template('dashboard.html', files=files, email=email)

def job():
    print("[Job] Checking inboxes...")
    users = get_all_user_tokens()
    for user in users:
        check_and_download_attachments(user)

scheduler = BackgroundScheduler()
scheduler.add_job(job, 'interval', minutes=5)
scheduler.start()

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
