import json
from datetime import datetime, date

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model, UserMixin):
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    name   = db.Column(db.String(20),  nullable=True)
    avatar = db.Column(db.String(200), nullable=True)

    # Геймификация
    last_study = db.Column(db.Date,    nullable=True)
    streak     = db.Column(db.Integer, default=0, nullable=False)
    xp         = db.Column(db.Integer, default=0, nullable=False)
    level      = db.Column(db.Integer, default=1, nullable=False)
    badges     = db.Column(db.String(255), default='', nullable=True)

    # Персонализация
    interests      = db.Column(db.String(200), default='', nullable=True)  # "games,sport,music"
    class_number   = db.Column(db.Integer, default=8, nullable=True)

    # Магазин скинов
    owned_skins   = db.Column(db.String(500), default='default', nullable=True)
    equipped_skin = db.Column(db.String(50),  default='default', nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Chat(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject      = db.Column(db.String(100), nullable=False)
    class_number = db.Column(db.Integer, nullable=False)
    mode         = db.Column(db.String(50), nullable=False)
    title        = db.Column(db.String(200), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    has_messages = db.Column(db.Boolean, default=False, nullable=False)
    user         = db.relationship('User', backref=db.backref('chats', lazy=True))


class History(db.Model):
    id        = db.Column(db.Integer, primary_key=True)
    chat_id   = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    user_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject   = db.Column(db.String(100), nullable=False)
    mode      = db.Column(db.String(50),  nullable=False)
    question  = db.Column(db.Text, nullable=False)
    answer    = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    rating    = db.Column(db.Integer, nullable=True)
    chat      = db.relationship('Chat', backref=db.backref('messages', lazy=True))
    user      = db.relationship('User', backref=db.backref('history', lazy=True))


# ════════════════════════════════════════════════════════
#  СИСТЕМА ДОЛГОСРОЧНОЙ ПАМЯТИ ОШИБОК
# ════════════════════════════════════════════════════════

class WeakTopic(db.Model):
    """Слабая тема — записывается когда ученик даёт низкую оценку или делает ошибку."""
    __tablename__ = 'weak_topic'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    subject    = db.Column(db.String(100), nullable=False)   # "Математика"
    topic      = db.Column(db.String(200), nullable=False)   # "Квадратные уравнения"
    details    = db.Column(db.Text, nullable=True)           # Что именно было неправильно

    # Счётчики
    error_count   = db.Column(db.Integer, default=1)   # Сколько раз ошибался
    review_count  = db.Column(db.Integer, default=0)   # Сколько раз повторял
    mastery_score = db.Column(db.Float,   default=0.0) # 0.0–1.0, рост при успешных повторениях

    # Интервальное повторение (алгоритм SM-2)
    easiness     = db.Column(db.Float, default=2.5)  # E-фактор
    interval     = db.Column(db.Integer, default=1)  # Дней до следующего повторения
    repetitions  = db.Column(db.Integer, default=0)  # Успешных повторений подряд

    first_seen   = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen    = db.Column(db.DateTime, default=datetime.utcnow)
    next_review  = db.Column(db.DateTime, default=datetime.utcnow)  # Когда повторить
    last_review  = db.Column(db.DateTime, nullable=True)

    is_mastered  = db.Column(db.Boolean, default=False)  # True если mastery_score >= 0.85

    user = db.relationship('User', backref=db.backref('weak_topics', lazy=True))

    def to_dict(self):
        return {
            'id':            self.id,
            'subject':       self.subject,
            'topic':         self.topic,
            'details':       self.details,
            'error_count':   self.error_count,
            'review_count':  self.review_count,
            'mastery_score': round(self.mastery_score, 2),
            'is_mastered':   self.is_mastered,
            'next_review':   self.next_review.isoformat() if self.next_review else None,
            'last_seen':     self.last_seen.isoformat() if self.last_seen else None,
            'days_ago':      (datetime.utcnow() - self.first_seen).days if self.first_seen else 0,
        }


class ReviewSession(db.Model):
    """Сессия повторения — когда ученик прошёл мини-повторение по слабой теме."""
    __tablename__ = 'review_session'

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    weak_topic_id = db.Column(db.Integer, db.ForeignKey('weak_topic.id'), nullable=False)

    started_at    = db.Column(db.DateTime, default=datetime.utcnow)
    completed     = db.Column(db.Boolean, default=False)
    score         = db.Column(db.Integer, nullable=True)   # 1–5, оценка от ученика

    user       = db.relationship('User', backref=db.backref('review_sessions', lazy=True))
    weak_topic = db.relationship('WeakTopic', backref=db.backref('sessions', lazy=True))


class MemoryNote(db.Model):
    """Личные заметки ИИ о конкретном ученике — накапливаются со временем."""
    __tablename__ = 'memory_note'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    note_type  = db.Column(db.String(50))    # 'learning_style', 'strength', 'struggle', 'personality'
    content    = db.Column(db.Text)          # Сам текст заметки
    subject    = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('memory_notes', lazy=True))


# ════════════════════════════════════════════════════════
#  АЛГОРИТМ SM-2 (интервальное повторение)
# ════════════════════════════════════════════════════════

def sm2_update(topic: WeakTopic, quality: int) -> WeakTopic:
    """
    Обновляет интервал повторения по алгоритму SM-2.
    quality: 0–5 (0=полный провал, 5=идеально)
    """
    from datetime import timedelta

    q = max(0, min(5, quality))

    if q >= 3:
        # Успешное повторение
        if topic.repetitions == 0:
            topic.interval = 1
        elif topic.repetitions == 1:
            topic.interval = 6
        else:
            topic.interval = round(topic.interval * topic.easiness)
        topic.repetitions += 1
        topic.mastery_score = min(1.0, topic.mastery_score + 0.15 * (q - 2) / 3)
    else:
        # Провал — сброс
        topic.repetitions = 0
        topic.interval = 1
        topic.mastery_score = max(0.0, topic.mastery_score - 0.2)

    # Обновляем E-фактор
    topic.easiness = max(1.3, topic.easiness + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))

    topic.last_review  = datetime.utcnow()
    topic.next_review  = datetime.utcnow() + timedelta(days=max(1, topic.interval))
    topic.review_count += 1
    topic.is_mastered   = topic.mastery_score >= 0.85

    return topic


def get_topics_due(user_id: int, limit: int = 5) -> list:
    """Возвращает темы которые пора повторить прямо сейчас."""
    now = datetime.utcnow()
    return WeakTopic.query.filter(
        WeakTopic.user_id    == user_id,
        WeakTopic.is_mastered == False,
        WeakTopic.next_review <= now,
    ).order_by(
        WeakTopic.mastery_score.asc(),   # сначала самые слабые
        WeakTopic.next_review.asc(),
    ).limit(limit).all()


def add_weak_topic(user_id: int, subject: str, topic: str, details: str = '') -> WeakTopic:
    """Добавляет или обновляет слабую тему."""
    existing = WeakTopic.query.filter_by(
        user_id=user_id, subject=subject, topic=topic
    ).first()

    if existing:
        existing.error_count += 1
        existing.last_seen    = datetime.utcnow()
        # Если долго не повторял — сдвигаем next_review на сейчас
        if existing.next_review > datetime.utcnow():
            from datetime import timedelta
            existing.next_review = datetime.utcnow() + timedelta(days=1)
        db.session.commit()
        return existing
    else:
        wt = WeakTopic(
            user_id = user_id,
            subject = subject,
            topic   = topic,
            details = details,
        )
        db.session.add(wt)
        db.session.commit()
        return wt


def get_user_memory_context(user_id: int) -> str:
    """
    Строит текстовый контекст из памяти для передачи в промпт.
    Используется в build_cluster_profile() чтобы ИИ знал историю ученика.
    """
    lines = []

    # Слабые темы
    weak = WeakTopic.query.filter_by(
        user_id=user_id, is_mastered=False
    ).order_by(WeakTopic.mastery_score.asc()).limit(8).all()

    if weak:
        lines.append("СЛАБЫЕ ТЕМЫ УЧЕНИКА (из долгосрочной памяти):")
        for w in weak:
            days_ago = (datetime.utcnow() - w.first_seen).days
            lines.append(f"  • {w.subject}: «{w.topic}» — ошибок: {w.error_count}, "
                         f"изучена {days_ago} дн. назад, освоение: {int(w.mastery_score*100)}%")
        lines.append("")

    # Освоенные темы (чтобы не повторять)
    mastered = WeakTopic.query.filter_by(
        user_id=user_id, is_mastered=True
    ).order_by(WeakTopic.updated_at.desc()).limit(5).all()

    if mastered:
        topics_str = ', '.join(f'«{m.topic}»' for m in mastered)
        lines.append(f"ОСВОЕННЫЕ ТЕМЫ (не повторяй): {topics_str}")
        lines.append("")

    # Заметки ИИ о характере обучения
    notes = MemoryNote.query.filter_by(user_id=user_id).order_by(
        MemoryNote.updated_at.desc()
    ).limit(5).all()

    if notes:
        lines.append("ЗАМЕТКИ О СТИЛЕ ОБУЧЕНИЯ УЧЕНИКА:")
        for n in notes:
            lines.append(f"  • [{n.note_type}] {n.content}")

    return "\n".join(lines) if lines else ""

def save_history(chat_id, subject, mode, question, answer):
    chat = db.session.get(Chat, chat_id)
    if not chat:
        raise ValueError("Chat not found")
    entry = History(
        chat_id  = chat_id,
        user_id  = chat.user_id,
        subject  = subject,
        mode     = mode,
        question = question,
        answer   = answer,
    )
    db.session.add(entry)
    if not chat.has_messages:
        chat.has_messages = True
    db.session.commit()
    return entry.id


def get_history(chat_id):
    return History.query.filter_by(
        chat_id=chat_id
    ).order_by(History.timestamp.asc()).all()