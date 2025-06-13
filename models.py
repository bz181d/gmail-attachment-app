from flask_sqlalchemy import SQLAlchemy
from google.oauth2.credentials import Credentials
import json

db = SQLAlchemy()

class UserToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, unique=True, nullable=False)
    token_json = db.Column(db.Text, nullable=False)

def init_db():
    db.create_all()

def save_user_tokens(email, credentials: Credentials):
    token_json = credentials.to_json()
    user = UserToken.query.filter_by(email=email).first()
    if user:
        user.token_json = token_json
    else:
        user = UserToken(email=email, token_json=token_json)
        db.session.add(user)
    db.session.commit()

def get_all_user_tokens():
    tokens = []
    for user in UserToken.query.all():
        creds = Credentials.from_authorized_user_info(json.loads(user.token_json))
        tokens.append(creds)
    return tokens
