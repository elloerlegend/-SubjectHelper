import json as _json
from datetime import datetime, date, timedelta

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
    interests      = db.Column(db.String(200), default='', nullable=True)
    class_number   = db.Column(db.Integer, default=8, nullable=True)

    # Онбординг
    is_onboarded   = db.Column(db.Boolean,   default=False, nullable=False)
    learning_style = db.Column(db.String(30), default='', nullable=True)
    goal           = db.Column(db.String(30), default='', nullable=True)
    hard_subjects  = db.Column(db.String(200), default='', nullable=True)
    referral       = db.Column(db.String(30), default='', nullable=True)

    # Магазин и кастомизация
    owned_skins   = db.Column(db.Text, default='default', nullable=True)
    equipped_skin = db.Column(db.String(50), default='default', nullable=True)

    # Настройки интерфейса
    theme        = db.Column(db.String(20), default='dark',  nullable=True)
    tts_enabled  = db.Column(db.Boolean,   default=False,   nullable=False)
    anim_enabled = db.Column(db.Boolean,   default=True,    nullable=False)
    enter_send   = db.Column(db.Boolean,   default=True,    nullable=False)
    daily_goal   = db.Column(db.Integer,   default=5,       nullable=False)

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

    subject    = db.Column(db.String(100), nullable=False)
    topic      = db.Column(db.String(200), nullable=False)
    details    = db.Column(db.Text, nullable=True)

    error_count   = db.Column(db.Integer, default=1)
    review_count  = db.Column(db.Integer, default=0)
    mastery_score = db.Column(db.Float,   default=0.0)

    # SM-2
    easiness    = db.Column(db.Float,   default=2.5)
    interval    = db.Column(db.Integer, default=1)
    repetitions = db.Column(db.Integer, default=0)

    first_seen  = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen   = db.Column(db.DateTime, default=datetime.utcnow)
    next_review = db.Column(db.DateTime, default=datetime.utcnow)
    last_review = db.Column(db.DateTime, nullable=True)

    is_mastered = db.Column(db.Boolean, default=False)

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
    __tablename__ = 'review_session'

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    weak_topic_id = db.Column(db.Integer, db.ForeignKey('weak_topic.id'), nullable=False)

    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed  = db.Column(db.Boolean, default=False)
    score      = db.Column(db.Integer, nullable=True)

    user       = db.relationship('User', backref=db.backref('review_sessions', lazy=True))
    weak_topic = db.relationship('WeakTopic', backref=db.backref('sessions', lazy=True))


class MemoryNote(db.Model):
    __tablename__ = 'memory_note'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    note_type  = db.Column(db.String(50))
    content    = db.Column(db.Text)
    subject    = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('memory_notes', lazy=True))


# ════════════════════════════════════════════════════════
#  LEARNING PATHS — три режима обучения
# ════════════════════════════════════════════════════════

class LearningPath(db.Model):
    """
    Активный учебный путь пользователя для конкретного предмета.
    mode = 'sprint' | 'journey'
    Casual = нет записи (path is None) — это намеренно, не создаём мусор в БД.
    """
    __tablename__ = 'learning_path'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject     = db.Column(db.String(100), nullable=False)
    mode        = db.Column(db.String(20),  nullable=False)   # 'sprint' | 'journey'
    is_active   = db.Column(db.Boolean, default=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    last_active = db.Column(db.DateTime, default=datetime.utcnow)

    # ── Sprint ────────────────────────────────────────
    sprint_goal        = db.Column(db.String(300), nullable=True)
    sprint_confidence  = db.Column(db.String(20), nullable=True)  # weak|medium|strong
    sprint_topics      = db.Column(db.Text, default='[]')      # JSON list of strings
    sprint_deadline    = db.Column(db.Date, nullable=True)
    sprint_done        = db.Column(db.Boolean, default=False)
    sprint_topics_done = db.Column(db.Text, default='[]')      # JSON list of completed topics

    # ── Journey ───────────────────────────────────────
    journey_goal     = db.Column(db.String(300), nullable=True)
    journey_level    = db.Column(db.String(30),  nullable=True)  # beginner|intermediate|advanced
    journey_roadmap  = db.Column(db.Text, default='[]')           # JSON [{unit, title, topics[], sessions_needed}]
    current_unit     = db.Column(db.Integer, default=1)
    sessions_done    = db.Column(db.Integer, default=0)
    minutes_per_week = db.Column(db.Integer, default=120)
    # Результаты мини-пробника для персонализации промпта
    probe_strong     = db.Column(db.Text, default='[]')   # JSON: темы которые знает хорошо
    probe_weak       = db.Column(db.Text, default='[]')   # JSON: темы-пробелы

    user = db.relationship('User', backref=db.backref('learning_paths', lazy=True))

    # ── Хелперы ───────────────────────────────────────

    def get_sprint_topics(self):
        try:
            return _json.loads(self.sprint_topics or '[]')
        except Exception:
            return []

    def get_sprint_done(self):
        try:
            return _json.loads(self.sprint_topics_done or '[]')
        except Exception:
            return []

    def get_roadmap(self):
        try:
            return _json.loads(self.journey_roadmap or '[]')
        except Exception:
            return []

    def get_probe_strong(self):
        try:
            return _json.loads(self.probe_strong or '[]')
        except Exception:
            return []

    def get_probe_weak(self):
        try:
            return _json.loads(self.probe_weak or '[]')
        except Exception:
            return []

    def get_current_unit_data(self):
        roadmap = self.get_roadmap()
        return next((u for u in roadmap if u.get('unit') == self.current_unit), {})

    def days_left(self):
        if not self.sprint_deadline:
            return None
        return max(0, (self.sprint_deadline - date.today()).days)

    def sprint_progress_pct(self):
        topics = self.get_sprint_topics()
        done   = self.get_sprint_done()
        if not topics:
            return 0
        return round(len(done) / len(topics) * 100)

    def journey_progress_pct(self):
        roadmap = self.get_roadmap()
        if not roadmap:
            return 0
        return round((self.current_unit - 1) / len(roadmap) * 100)

    def to_dict(self):
        d = {
            'id':        self.id,
            'subject':   self.subject,
            'mode':      self.mode,
            'is_active': self.is_active,
        }
        if self.mode == 'sprint':
            topics     = self.get_sprint_topics()
            done       = self.get_sprint_done()
            topics_left = [t for t in topics if t not in done]
            d.update({
                'sprint_goal':        self.sprint_goal,
                'sprint_confidence':  self.sprint_confidence,
                'sprint_topics':      topics,
                'sprint_topics_done': done,
                'sprint_topics_left': topics_left,
                'sprint_deadline':    self.sprint_deadline.isoformat() if self.sprint_deadline else None,
                'days_left':          self.days_left(),
                'progress_pct':       self.sprint_progress_pct(),
                'sprint_done':        self.sprint_done,
            })
        if self.mode == 'journey':
            roadmap = self.get_roadmap()
            d.update({
                'journey_goal':      self.journey_goal,
                'journey_level':     self.journey_level,
                'current_unit':      self.current_unit,
                'sessions_done':     self.sessions_done,
                'roadmap':           roadmap,
                'current_unit_data': self.get_current_unit_data(),
                'progress_pct':      self.journey_progress_pct(),
                'probe_strong':      self.get_probe_strong(),
                'probe_weak':        self.get_probe_weak(),
            })
        return d


# ════════════════════════════════════════════════════════
#  АЛГОРИТМ SM-2
# ════════════════════════════════════════════════════════

def sm2_update(topic: WeakTopic, quality: int) -> WeakTopic:
    q = max(0, min(5, quality))

    if q >= 3:
        if topic.repetitions == 0:
            topic.interval = 1
        elif topic.repetitions == 1:
            topic.interval = 6
        else:
            topic.interval = round(topic.interval * topic.easiness)
        topic.repetitions  += 1
        topic.mastery_score = min(1.0, topic.mastery_score + 0.15 * (q - 2) / 3)
    else:
        topic.repetitions   = 0
        topic.interval      = 1
        topic.mastery_score = max(0.0, topic.mastery_score - 0.2)

    topic.easiness     = max(1.3, topic.easiness + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    topic.last_review  = datetime.utcnow()
    topic.next_review  = datetime.utcnow() + timedelta(days=max(1, topic.interval))
    topic.review_count += 1
    topic.is_mastered   = topic.mastery_score >= 0.85

    return topic


def get_topics_due(user_id: int, limit: int = 5) -> list:
    now = datetime.utcnow()
    return WeakTopic.query.filter(
        WeakTopic.user_id     == user_id,
        WeakTopic.is_mastered == False,
        WeakTopic.next_review <= now,
    ).order_by(
        WeakTopic.mastery_score.asc(),
        WeakTopic.next_review.asc(),
    ).limit(limit).all()


def add_weak_topic(user_id: int, subject: str, topic: str, details: str = '') -> WeakTopic:
    existing = WeakTopic.query.filter_by(
        user_id=user_id, subject=subject, topic=topic
    ).first()

    if existing:
        existing.error_count += 1
        existing.last_seen    = datetime.utcnow()
        if existing.next_review > datetime.utcnow():
            existing.next_review = datetime.utcnow() + timedelta(days=1)
        db.session.commit()
        return existing
    else:
        wt = WeakTopic(user_id=user_id, subject=subject, topic=topic, details=details)
        db.session.add(wt)
        db.session.commit()
        return wt


def get_user_memory_context(user_id: int) -> str:
    lines = []

    weak = WeakTopic.query.filter_by(
        user_id=user_id, is_mastered=False
    ).order_by(WeakTopic.mastery_score.asc()).limit(8).all()

    if weak:
        lines.append("СЛАБЫЕ ТЕМЫ УЧЕНИКА (из долгосрочной памяти):")
        for w in weak:
            days_ago = (datetime.utcnow() - w.first_seen).days
            lines.append(
                f"  • {w.subject}: «{w.topic}» — ошибок: {w.error_count}, "
                f"изучена {days_ago} дн. назад, освоение: {int(w.mastery_score*100)}%"
            )
        lines.append("")

    mastered = WeakTopic.query.filter_by(
        user_id=user_id, is_mastered=True
    ).order_by(WeakTopic.last_seen.desc()).limit(5).all()

    if mastered:
        topics_str = ', '.join(f'«{m.topic}»' for m in mastered)
        lines.append(f"ОСВОЕННЫЕ ТЕМЫ (не повторяй): {topics_str}")
        lines.append("")

    notes = MemoryNote.query.filter_by(user_id=user_id).order_by(
        MemoryNote.updated_at.desc()
    ).limit(5).all()

    if notes:
        lines.append("ЗАМЕТКИ О СТИЛЕ ОБУЧЕНИЯ УЧЕНИКА:")
        for n in notes:
            lines.append(f"  • [{n.note_type}] {n.content}")

    return "\n".join(lines) if lines else ""


# ════════════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ════════════════════════════════════════════════════════

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