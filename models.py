import json
from datetime import datetime, date

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    name = db.Column(db.String(20), nullable=True)
    avatar = db.Column(db.String(200), nullable=True)

    # Геймификация
    last_study = db.Column(db.Date, nullable=True)
    streak = db.Column(db.Integer, default=0, nullable=False)
    xp = db.Column(db.Integer, default=0, nullable=False)
    level = db.Column(db.Integer, default=1, nullable=False)
    badges = db.Column(db.String(255), default='', nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


# === НОВАЯ МОДЕЛЬ — ОТДЕЛЬНЫЕ ЧАТЫ ===
class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    subject = db.Column(db.String(100), nullable=False)
    class_number = db.Column(db.Integer, nullable=False)
    mode = db.Column(db.String(50), nullable=False)

    title = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Новое поле: есть ли в чате хотя бы одно сообщение
    has_messages = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship('User', backref=db.backref('chats', lazy=True))


class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)  # ← главное изменение
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    subject = db.Column(db.String(100), nullable=False)
    mode = db.Column(db.String(50), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    rating = db.Column(db.Integer, nullable=True)

    chat = db.relationship('Chat', backref=db.backref('messages', lazy=True))
    user = db.relationship('User', backref=db.backref('history', lazy=True))


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
def save_history(chat_id, subject, mode, question, answer):
    chat = db.session.get(Chat, chat_id)
    if not chat:
        raise ValueError("Chat not found")
    entry = History(
        chat_id=chat_id,
        user_id=chat.user_id,
        subject=subject,
        mode=mode,
        question=question,
        answer=answer
    )
    db.session.add(entry)
    # Если это первое сообщение, помечаем чат как активный
    if not chat.has_messages:
        chat.has_messages = True
    db.session.commit()
    return entry.id

def get_history(chat_id):
    """Возвращает все сообщения чата, отсортированные по времени (от старых к новым)"""
    return History.query.filter_by(chat_id=chat_id).order_by(History.timestamp.asc()).all()