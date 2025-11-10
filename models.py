# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    mode = db.Column(db.String(50), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    rating = db.Column(db.Integer, nullable=True)
    user = db.relationship('User', backref=db.backref('history', lazy=True))

def register_user(email, password):
    if User.query.filter_by(email=email).first():
        return None
    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user

def login_user(email, password):
    user = User.query.filter_by(email=email).first()
    if user and user.check_password(password):
        return user
    return None

def save_history(user_id, subject, mode, question, answer):
    entry = History(
        user_id=user_id,
        subject=subject,
        mode=mode,
        question=question,
        answer=answer,
        timestamp=datetime.utcnow()
    )
    db.session.add(entry)
    db.session.commit()
    return entry.id

def get_history(user_id):
    return History.query.filter_by(user_id=user_id).order_by(History.timestamp.desc()).all()