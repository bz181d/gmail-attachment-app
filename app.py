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

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
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
        include_granted_scopes='true'
    )
    session.permanent = True  # <-- Add this
    session['state'] = state
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    try:
        state = session['state']
    except KeyError:
        return "Session expired or tampered. Please <a href='/'>try again</a>.", 400

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state
    )
    flow.redirect_uri = url_for('oauth2callback', _external=True)

    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials

    if not credentials or not credentials.valid:
        return "Invalid credentials received from Google.", 401

    userinfo = googleapiclient.discovery.build('oauth2', 'v2', credentials=credentials).userinfo().get().execute()
    email = userinfo['email']

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
