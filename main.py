from flask import Flask, request, jsonify, redirect, render_template, flash, session, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
from functools import wraps
import os
import logging
from datetime import datetime, timedelta
from duel_server import attach_duel, socketio as duel_socketio
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

from models import (
    db, User, History, Chat, save_history, get_history,
    WeakTopic, ReviewSession, MemoryNote,
    add_weak_topic, sm2_update, get_topics_due, get_user_memory_context
)

# ====================== НАСТРОЙКИ ======================
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', '7e4c956c8ab1a339f9f347927f09fa30de5dd8d1539f930e146f9d5c693389df')
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

with app.app_context():
    db.init_app(app)
    db.create_all()

# ====================== GROQ ======================
client = Groq(api_key=os.environ.get('GROQ_API_KEY'))
AI_MODEL = "llama-3.3-70b-versatile"
attach_duel(app, client, AI_MODEL, db, User)

def ask_groq(prompt: str, system: str = None, max_tokens: int = 1000,
             chat_history: list = None) -> str:
    """Запрос к Groq API."""
    try:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        # Контекст предыдущих сообщений чата (последние 8 пар)
        if chat_history:
            messages.extend(chat_history[-16:])
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(
            model=AI_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"Groq API error: {e}", exc_info=True)
        err = str(e).lower()
        if "api key" in err or "auth" in err:
            return "Ошибка API-ключа. Проверь GROQ_API_KEY в .env"
        if "rate limit" in err:
            return "Слишком много запросов. Подожди несколько секунд."
        return "Произошла ошибка. Попробуй ещё раз."


# ====================== ПРОМПТЫ ======================

def build_cluster_profile(class_number: int, subject: str, user_stats: dict, user_id: int = None) -> str:
    """Строит персонализированный профиль ученика для системного промпта."""

    # 1–4 класс
    if class_number <= 4:
        persona = (
            "ТЫ ГОВОРИШЬ С МЛАДШЕКЛАССНИКОМ (7–10 лет). ПРАВИЛА ОБЯЗАТЕЛЬНЫ:\n"
            "— Максимум 3 предложения на одну мысль. Короче = лучше.\n"
            "— НИКАКИХ терминов без объяснения прямо в тексте.\n"
            "— Всегда используй сравнения с играми, животными, едой, мультиками.\n"
            "— Примеры: «это как Майнкрафт», «представь что ты волшебник».\n"
            "— Используй смайлы умеренно: 1–2 на сообщение.\n"
            "— В конце ВСЕГДА задай один простой вопрос на проверку, как в игре.\n"
            "— Хвали за каждый ответ: «Молодец!», «Отлично соображаешь!»\n"
            "— Если ошибся — НИКОГДА не говори «неправильно». Говори: «Почти! Давай попробуем вместе 🤝»\n"
        )

    # 5–7 класс
    elif class_number <= 7:
        persona = (
            "ТЫ ГОВОРИШЬ С УЧЕНИКОМ 5–7 КЛАССА (11–14 лет). ПРАВИЛА:\n"
            "— Общайся как старший друг, не как учитель. Можно лёгкий юмор.\n"
            "— Термины вводи постепенно: сначала простым языком, потом официальное название в скобках.\n"
            "— Примеры из реальной жизни: спорт, музыка, соцсети, видеоигры.\n"
            "— Структура: сначала «зачем это нужно в жизни», потом объяснение.\n"
            "— Мотивируй: «Это пригодится тебе в 8 классе», «Ты уже знаешь половину ЕГЭ».\n"
            "— Если ученик ошибся — объясни почему, без осуждения.\n"
        )

    # 8–9 класс
    elif class_number <= 9:
        persona = (
            "ТЫ ГОВОРИШЬ С УЧЕНИКОМ 8–9 КЛАССА (14–16 лет), ГОТОВЯЩИМСЯ К ОГЭ. ПРАВИЛА:\n"
            "— Используй правильную терминологию, но объясняй сложные термины.\n"
            "— Всегда указывай связь с форматом ОГЭ: «В ОГЭ это задание №5».\n"
            "— Показывай типичные ошибки: «Многие здесь теряют баллы потому что...»\n"
            "— Структурированные ответы с нумерацией шагов.\n"
            "— Задавай вопросы на понимание, а не на запоминание.\n"
            "— Уважай как взрослого — не сюсюкай, но и не будь сухим.\n"
        )

    # 10–11 класс
    else:
        persona = (
            "ТЫ РАБОТАЕШЬ СО СТАРШЕКЛАССНИКОМ (16–18 лет), ЦЕЛЬ — ЕГЭ. ПРАВИЛА:\n"
            "— Общайся как равный с равным. Академический стиль, без упрощений.\n"
            "— Используй точные термины без лишних объяснений.\n"
            "— Указывай конкретные критерии ЕГЭ: «по критерию К2 снимут 1 балл если...»\n"
            "— Давай задания в точном формате ЕГЭ текущего года.\n"
            "— Указывай первичный балл → вторичный балл → примерный процентиль.\n"
            "— Если ученик делает системную ошибку — скажи прямо и дай план исправления.\n"
        )

    # Персонализация по статистике
    personal_parts = []
    avg_r  = user_stats.get('avg_rating', 0)
    streak = user_stats.get('streak', 0)
    weak   = user_stats.get('weak_subjects', [])
    total  = user_stats.get('total_questions', 0)

    if 0 < avg_r < 3:
        personal_parts.append(
            f"ВНИМАНИЕ: ученик оценивает ответы низко (средняя {avg_r}/5). "
            "Объясняй ПРОЩЕ, используй больше примеров."
        )
    elif avg_r >= 4.5:
        personal_parts.append(
            f"Ученик хорошо понимает материал (оценка {avg_r}/5). Можно усложнять задания."
        )

    if streak >= 7:
        personal_parts.append(
            f"Ученик занимается {streak} дней подряд — он мотивирован! Можно давать более сложные задания."
        )
    elif streak == 0:
        personal_parts.append("Ученик только начинает. Будь особенно поддерживающим.")

    if weak and subject in weak:
        personal_parts.append(
            f"ЭТОТ ПРЕДМЕТ ({subject}) является слабым для ученика. Объясняй особенно тщательно."
        )

    if total > 100:
        personal_parts.append(f"Опытный пользователь ({total} вопросов). Не объясняй очевидные вещи.")

    personal = ("\n— ".join(personal_parts))
    if personal:
        personal = "\nДОПОЛНИТЕЛЬНО:\n— " + personal + "\n"

    # Долгосрочная память ошибок
    memory_ctx   = get_user_memory_context(user_id) if user_id else ""
    memory_block = "\n\n" + memory_ctx if memory_ctx else ""

    return persona + ("\n\n" + personal if personal else "") + memory_block


def build_system(mode: str, subject: str, class_number: int, submode: str = "") -> str:
    """Строит системный промпт под режим, предмет и класс."""

    if class_number <= 4:
        level = "младшеклассника (7–10 лет), объясняй очень просто"
    elif class_number <= 7:
        level = "ученика 5–7 класса (11–14 лет), используй примеры из жизни"
    elif class_number <= 9:
        level = "ученика 8–9 класса (14–16 лет), готовящегося к ОГЭ"
    else:
        level = "ученика 10–11 класса (16–18 лет), готовящегося к ЕГЭ"

    base = (
        f"Ты — репетитор SubjectHelper для {level}. "
        f"Предмет: {subject}. Класс: {class_number}. "
        "Отвечай ТОЛЬКО на русском языке. "
        "Будь дружелюбным и поддерживающим."
    )

    if mode == "explain":
        return (
            f"{base}\n\n"
            "РЕЖИМ: ОБЪЯСНЕНИЕ ТЕМЫ.\n"
            "Структура ответа:\n"
            "1) Простое определение (1–2 предложения)\n"
            "2) Подробное объяснение с аналогией из жизни\n"
            "3) Конкретный пример\n"
            "4) Короткий вопрос для самопроверки в конце\n"
            "Если тема содержит формулы — объясни каждый символ."
        )

    elif mode == "step":
        return (
            f"{base}\n\n"
            "РЕЖИМ: ПОШАГОВОЕ РЕШЕНИЕ.\n"
            "КРИТИЧЕСКИ ВАЖНО: давай ТОЛЬКО ОДИН шаг за раз.\n"
            "Формат одного шага:\n"
            "**Шаг N:** [название действия]\n"
            "[Подробное объяснение что делаем и ПОЧЕМУ]\n"
            "**Результат:** [что получилось]\n\n"
            "После шага ОСТАНОВИСЬ и жди реакции ученика.\n"
            "НЕ давай следующий шаг пока ученик не попросит.\n"
            "Если это последний шаг — напиши '**Ответ:**' и итог."
        )

    elif mode == "quiz":
        return (
            f"{base}\n\n"
            "РЕЖИМ: ПРОВЕРКА ЗНАНИЙ.\n"
            "Задавай ОДИН вопрос с 4 вариантами ответа.\n"
            "ОБЯЗАТЕЛЬНО возвращай ТОЛЬКО валидный JSON без лишнего текста:\n"
            '{"question": "текст вопроса", '
            '"options": ["вариант A", "вариант B", "вариант C", "вариант D"], '
            '"correct_index": 0, '
            '"explanation": "краткое объяснение почему этот ответ правильный"}\n\n'
            "correct_index — индекс правильного ответа (0, 1, 2 или 3).\n"
            "Варианты должны быть правдоподобными. Только JSON, никакого другого текста."
        )

    elif mode == "exam":
        if submode == "practice":
            return (
                f"{base}\n\n"
                "РЕЖИМ: ТРЕНИРОВКА ОТДЕЛЬНЫХ ЗАДАНИЙ ЕГЭ/ОГЭ.\n"
                f"Давай задания в точном формате реального экзамена по {subject}.\n"
                "Структура задания:\n"
                "**Задание [номер типа]** (Часть [1/2], [X] баллов)\n"
                "[Текст задания точно как в ЕГЭ/ОГЭ]\n\n"
                "После ответа ученика: оцени по критериям, укажи баллы, разбери ошибки."
            )
        elif submode == "full":
            return (
                f"{base}\n\n"
                "РЕЖИМ: ПОЛНЫЙ ЭКЗАМЕН ЕГЭ/ОГЭ.\n"
                f"Симулируй реальный экзамен по {subject}.\n"
                "Давай задания строго по порядку как в настоящем экзамене.\n"
                "Не давай подсказок до конца экзамена.\n"
                "В конце — полный разбор всех ответов с баллами."
            )
        else:
            return (
                f"{base}\n\n"
                "РЕЖИМ: ПОДГОТОВКА К ЕГЭ/ОГЭ.\n"
                f"Помогай ученику понять формат экзамена по {subject}.\n"
                "Объясняй типы заданий, критерии оценивания, типичные ошибки.\n"
                "Давай советы по стратегии прохождения экзамена."
            )

    return base


def get_user_stats(user_id: int, subject: str) -> dict:
    """Собирает статистику пользователя для персонализации промпта."""
    history_all = get_user_history(user_id)

    rated = [h.rating for h in history_all if h.rating]
    avg_r = round(sum(rated) / len(rated), 1) if rated else 0

    # Слабые предметы: те где средняя оценка < 3
    quality = {}
    for h in history_all:
        if h.rating:
            if h.subject not in quality:
                quality[h.subject] = []
            quality[h.subject].append(h.rating)

    weak_subjects = [
        s for s, ratings in quality.items()
        if (sum(ratings) / len(ratings)) < 3.0
    ]

    user = db.session.get(User, user_id)

    return {
        'avg_rating':      avg_r,
        'streak':          user.streak or 0 if user else 0,
        'weak_subjects':   weak_subjects,
        'total_questions': len(history_all),
    }


# ====================== ДЕКОРАТОР ======================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Войдите в аккаунт.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ====================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======================
def get_user_history(user_id):
    return History.query.join(Chat).filter(Chat.user_id == user_id).order_by(History.timestamp.desc()).all()


# ====================== МЕНЮ ======================
@app.context_processor
def inject_menu():
    if 'user_id' in session:
        user = db.session.get(User, session['user_id'])
        if not user:
            session.clear()
            return dict(menu='', menu_js='')

        avatar_html = (
            f'<img src="{user.avatar}" class="menu-avatar" id="userCircle">'
            if user.avatar else
            f'<div class="user-circle" id="userCircle">{(user.name or "U")[0].upper()}</div>'
        )

        menu = f'''
        <div class="user-menu">
          {avatar_html}
          <div class="dropdown-menu" id="dropdownMenu">
            <a href="{url_for('profile')}">Профиль</a>
            <a href="{url_for('chats_list')}">Мои чаты</a>
            <a href="{url_for('history_page')}">История</a>
            <a href="{url_for('duel_page')}">⚔️ Дуэли</a>
            <a href="{url_for('shop_page')}">🛍️ Магазин</a>
            <a href="{url_for('leaderboard')}">🏆 Лидерборд</a>
            <a href="{url_for('settings_page')}">⚙️ Настройки</a>
            <a href="{url_for('logout')}">Выйти</a>
          </div>
        </div>
        '''
        js = '''<script>document.addEventListener("DOMContentLoaded", () => {
            const c = document.getElementById("userCircle"), m = document.getElementById("dropdownMenu");
            if (c && m) {
              c.onclick = e => { e.stopPropagation(); m.classList.toggle("show"); };
              document.onclick = () => m.classList.remove("show");
            }
        });</script>'''
    else:
        menu = '''<div class="auth-menu">
            <a href="/login" class="auth-btn login-btn"><span class="material-icons">login</span> Войти</a>
            <a href="/register" class="auth-btn register-btn"><span class="material-icons">person_add</span> Регистрация</a>
        </div>'''
        js = ''
    return dict(menu=menu, menu_js=js)


# ====================== СТРАНИЦЫ ======================
@app.route("/")
def welcome():
    return render_template("welcome.html")


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = db.session.get(User, session['user_id'])
    if not user:
        return redirect(url_for('logout'))

    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        if nickname and len(nickname) <= 20:
            user.name = nickname
            session['nickname'] = nickname
            flash('Ник обновлён!', 'success')
        file = request.files.get('avatar')
        if file and file.filename:
            filename = secure_filename(f"avatar_{user.id}.png")
            os.makedirs("static/avatars", exist_ok=True)
            file.save(os.path.join("static/avatars", filename))
            user.avatar = f"/static/avatars/{filename}"
            session['avatar'] = user.avatar
            flash("Аватар обновлён!", "success")
        db.session.commit()

    history = get_user_history(user.id)
    total = len(history)
    rated = [h for h in history if h.rating]
    avg = round(sum(h.rating for h in rated) / len(rated), 1) if rated else 0

    subjects = {}
    for h in history:
        subjects[h.subject] = subjects.get(h.subject, 0) + 1
    top = max(subjects, key=subjects.get) if subjects else "—"
    max_queries = max(subjects.values()) if subjects else 1

    # Геймификация: обновляем стрик и XP при заходе на профиль
    today = datetime.now().date()
    if user.last_study is None or user.last_study != today:
        if user.last_study == today - timedelta(days=1):
            user.streak += 1
            user.xp += 20
        else:
            user.streak = 1
        user.last_study = today
        user.xp += 5
        user.level = user.xp // 100 + 1
        db.session.commit()

    quality = {}
    for h in history:
        if h.rating:
            quality.setdefault(h.subject, []).append(h.rating)
    for s in quality:
        quality[s] = round(sum(quality[s]) / len(quality[s]), 1)
    weak_subject = min(quality, key=quality.get, default="—") if quality else "—"

    week_ago = datetime.now() - timedelta(days=7)
    recent = [h for h in history if h.timestamp > week_ago]
    dates = {}
    for h in recent:
        day = h.timestamp.strftime('%d.%m')
        dates[day] = dates.get(day, 0) + 1

    return render_template('profile.html',
                           current_user=user,
                           total_queries=total,
                           avg_rating=avg,
                           top_subject=top,
                           subject_stats=subjects,
                           max_queries=max_queries,
                           quality=quality,
                           weak_subject=weak_subject,
                           dates=dates)


@app.route("/chat")
@login_required
def chat():
    if 'current_chat_id' not in session:
        return redirect(url_for('chats_list'))
    return render_template("chat.html")


@app.route("/chats")
@login_required
def chats_list():
    user_id = session['user_id']
    chats = Chat.query.filter_by(user_id=user_id, has_messages=True).order_by(Chat.updated_at.desc()).all()
    return render_template("chats.html", chats=chats)


@app.route("/new_chat", methods=["POST"])
@login_required
def new_chat():
    subject      = request.form.get("subject", "Математика")
    class_number = int(request.form.get("class_number", 8))
    mode         = request.form.get("mode", "explain")

    title = f"{subject} — {class_number} класс ({mode})"
    chat = Chat(
        user_id=session['user_id'],
        subject=subject,
        class_number=class_number,
        mode=mode,
        title=title,
    )
    db.session.add(chat)
    db.session.commit()

    session['current_chat_id'] = chat.id
    return redirect(url_for('open_chat', chat_id=chat.id))


@app.route("/chat/<int:chat_id>")
@login_required
def open_chat(chat_id):
    chat = db.session.get(Chat, chat_id)
    if not chat:
        flash("Чат не найден", "danger")
        return redirect(url_for('chats_list'))
    if chat.user_id != session['user_id']:
        flash("Доступ запрещён", "danger")
        return redirect(url_for('chats_list'))

    session['current_chat_id'] = chat_id
    messages = get_history(chat_id)
    return render_template("chat.html", chat=chat, messages=messages)


@app.route('/history')
@login_required
def history_page():
    user = db.session.get(User, session['user_id'])
    if not user:
        return redirect(url_for('logout'))
    return render_template('history.html', current_user=user)


@app.route('/api/history', methods=['POST'])
@login_required
def api_history():
    chat_id = session.get('current_chat_id')
    if not chat_id:
        return jsonify([])
    history = History.query.filter_by(chat_id=chat_id).order_by(History.timestamp.asc()).all()
    return jsonify([{
        "id":        x.id,
        "subject":   x.subject,
        "mode":      x.mode,
        "question":  x.question,
        "answer":    x.answer,
        "timestamp": x.timestamp.strftime('%d.%m %H:%M'),
        "rating":    x.rating or 0,
    } for x in history])


# ====================== ЛИДЕРБОРД ======================
@app.route('/leaderboard')
@login_required
def leaderboard():
    top_users = User.query.order_by(User.xp.desc()).limit(50).all()

    current   = db.session.get(User, session['user_id'])
    all_users = User.query.order_by(User.xp.desc()).all()
    my_rank   = next((i + 1 for i, u in enumerate(all_users) if u.id == current.id), 0)

    return render_template('leaderboard.html',
                           top_users=top_users,
                           current_user=current,
                           my_rank=my_rank)


# ====================== ОСНОВНОЙ ЗАПРОС К ИИ ======================
@app.route("/ask", methods=["POST"])
@login_required
def ask():
    chat_id = session.get('current_chat_id')
    if not chat_id:
        return jsonify({"error": "Сначала выбери или создай чат"}), 400

    question = request.form.get("question", "").strip()
    if not question:
        return jsonify({"error": "Вопрос пуст"}), 400

    chat = db.session.get(Chat, chat_id)
    if not chat:
        return jsonify({"error": "Чат не найден"}), 404

    subject      = chat.subject
    mode         = chat.mode
    class_number = chat.class_number
    submode      = request.form.get("submode", "")

    user = db.session.get(User, session['user_id'])

    # Собираем статистику для персонализации
    user_stats = get_user_stats(session['user_id'], subject)

    # Строим полный системный промпт: кластер + режим
    cluster = build_cluster_profile(class_number, subject, user_stats)
    mode_prompt = build_system(mode, subject, class_number, submode)
    system = cluster + "\n\n" + mode_prompt

    # Загружаем историю чата для контекста (последние 8 пар)
    raw_history = History.query.filter_by(chat_id=chat_id).order_by(
        History.timestamp.asc()
    ).all()
    chat_history = []
    for h in raw_history[-8:]:
        chat_history.append({"role": "user",      "content": h.question})
        chat_history.append({"role": "assistant",  "content": h.answer})

    answer = ask_groq(question, system=system, max_tokens=800, chat_history=chat_history)

    hid = save_history(chat_id, subject, mode, question, answer)

    # Начисляем XP
    user.xp += 10
    user.level = user.xp // 100 + 1
    db.session.commit()

    entry = db.session.get(History, hid)
    ts = entry.timestamp.strftime("%H:%M") if entry else ""

    logger.info(f"ASK user={session['user_id']} mode={mode} submode={submode} class={class_number}")

    return jsonify({"answer": answer, "question_id": hid, "timestamp": ts})


# ====================== ПЛАН ПРАКТИКИ ======================
@app.route("/plan", methods=["POST"])
@login_required
def generate_plan():
    data    = request.get_json() or {}
    subject = data.get("subject", "Математика").strip()
    user    = db.session.get(User, session['user_id'])

    system = (
        "Ты — репетитор SubjectHelper. "
        "Составляй планы обучения строго по запрошенному формату. "
        "Отвечай только на русском языке."
    )
    prompt = (
        f"Составь план практики по предмету «{subject}» на 7 дней.\n\n"
        "СТРОГО следуй этому формату:\n\n"
        "ДЕНЬ 1: Название темы\n"
        "• Задание 1\n• Задание 2\n• Задание 3\n"
        "Самопроверка: вопрос\n\n"
        "(повтори для каждого из 7 дней)\n\n"
        "Итоговая цель недели: ...\n\n"
        f"Стрик пользователя: {user.streak} дней. Сделай план мотивирующим."
    )

    plan = ask_groq(prompt, system=system, max_tokens=1500)

    chat_id = session.get('current_chat_id')
    if not chat_id:
        new_chat_obj = Chat(
            user_id=user.id,
            subject=subject,
            class_number=8,
            mode="plan",
            title=f"План по {subject}",
        )
        db.session.add(new_chat_obj)
        db.session.commit()
        chat_id = new_chat_obj.id

    save_history(chat_id, subject, "plan", f"План по {subject}", plan)
    return jsonify({"plan": plan})


# ====================== РЕГИСТРАЦИЯ / ЛОГИН ======================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        if not email or not password:
            flash("Заполните поля", "danger")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("Email занят", "warning")
            return redirect(url_for("register"))

        user = User(email=email)
        user.set_password(password)
        user.last_study = None
        user.streak     = 0
        user.xp         = 0
        user.level      = 1
        user.badges     = ''
        db.session.add(user)
        db.session.commit()

        flash("Добро пожаловать в SubjectHelper 🎉", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        user     = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session["user_id"]  = user.id
            session["nickname"] = user.name or "Пользователь"
            flash("Привет!", "success")
            return redirect(url_for("profile"))
        flash("Неверный email или пароль", "danger")
    return render_template("login.html")


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из аккаунта.')
    return redirect(url_for('welcome'))


# ====================== ОЦЕНКА ОТВЕТА ======================
@app.route("/rate", methods=["POST"])
@login_required
def rate():
    data = request.get_json() or {}
    hid  = data.get("history_id")
    r    = data.get("rating")
    if not hid or r not in (1, 2, 3, 4, 5):
        return jsonify({"error": "Нет"}), 400
    e = db.session.get(History, hid)
    if e and e.chat.user_id == session['user_id']:
        e.rating = r
        db.session.commit()
        logger.info(f"RATE: QID {hid} → {r} stars")
        return jsonify({"ok": True})
    return jsonify({"error": "Не найдено"}), 404


# ====================== АВАТАР И НИК ======================
@app.route('/update_avatar', methods=['POST'])
@login_required
def update_avatar():
    user = db.session.get(User, session['user_id'])
    if not user:
        return redirect(url_for('logout'))
    file = request.files.get('avatar')
    if not file or not file.filename:
        flash('Файл не выбран.', 'warning')
        return redirect(url_for('settings_page'))
    os.makedirs('static/avatars', exist_ok=True)
    filename = secure_filename(f"avatar_{user.id}.png")
    file.save(os.path.join('static/avatars', filename))
    user.avatar = f"/static/avatars/{filename}"
    db.session.commit()
    session['avatar'] = user.avatar
    flash('✅ Аватар обновлён!', 'success')
    return redirect(url_for('welcome'))


@app.route('/update_nickname', methods=['POST'])
@login_required
def update_nickname():
    user = db.session.get(User, session['user_id'])
    if not user:
        return redirect(url_for('logout'))
    nickname = request.form.get('nickname', '').strip()
    if not nickname:
        flash('Введите никнейм.', 'warning')
        return redirect(url_for('profile'))
    if len(nickname) > 20:
        flash('Никнейм слишком длинный.', 'warning')
        return redirect(url_for('profile'))
    user.name = nickname
    db.session.commit()
    session['nickname'] = nickname
    flash('✅ Ник изменён!', 'success')
    return redirect(url_for('profile'))




# ====================== TTS ПРОКСИ ====================
@app.route('/api/tts', methods=['POST'])
@login_required
def tts_proxy():
    """Прокси для VoiceRSS — решает проблему CORS."""
    key = os.environ.get('VOICERSS_API_KEY', '')
    if not key:
        return jsonify({'error': 'VOICERSS_API_KEY не настроен в .env'}), 404

    text = request.json.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Пустой текст'}), 400

    # Ограничиваем длину
    text = text[:500]

    try:
        import urllib.request, urllib.parse
        params = urllib.parse.urlencode({
            'key':  key,
            'src':  text,
            'hl':   'ru-ru',
            'v':    'Ekaterina',
            'r':    '-1',
            'c':    'mp3',
            'f':    '44khz_16bit_stereo',
            'ssml': 'false',
            'b64':  'false',
        })
        url = f'https://api.voicerss.org/?{params}'
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get('Content-Type', '')
            data = resp.read()
            # VoiceRSS возвращает текст ошибки если что-то не так
            if 'audio' not in content_type and data.startswith(b'ERROR'):
                err = data.decode('utf-8', errors='ignore')
                logger.error(f"VoiceRSS error: {err}")
                return jsonify({'error': err}), 400
            from flask import Response
            return Response(data, mimetype='audio/mpeg')
    except Exception as e:
        logger.error(f"TTS proxy error: {e}")
        return jsonify({'error': str(e)}), 500


# ====================== ФАЙРИК API ======================
SHOP_SKINS = [
    {'id': 'default', 'name': 'Классический', 'price': 0,   'css': '',                                                        'emoji': '🐉'},
    {'id': 'fire',    'name': 'Огненный',      'price': 150, 'css': 'hue-rotate(300deg) saturate(2)',                          'emoji': '🔥'},
    {'id': 'ice',     'name': 'Ледяной',       'price': 150, 'css': 'hue-rotate(180deg) saturate(1.5) brightness(1.1)',        'emoji': '❄️'},
    {'id': 'galaxy',  'name': 'Галактический', 'price': 300, 'css': 'hue-rotate(250deg) saturate(3) brightness(1.2)',          'emoji': '🌌'},
    {'id': 'gold',    'name': 'Золотой',       'price': 500, 'css': 'sepia(1) saturate(4) hue-rotate(5deg) brightness(1.1)',   'emoji': '✨'},
    {'id': 'shadow',  'name': 'Теневой',       'price': 400, 'css': 'grayscale(0.8) brightness(0.6) contrast(1.5)',            'emoji': '🌑'},
    {'id': 'nature',  'name': 'Лесной',        'price': 200, 'css': 'hue-rotate(80deg) saturate(2)',                           'emoji': '🌿'},
    {'id': 'neon',    'name': 'Неоновый',      'price': 350, 'css': 'hue-rotate(140deg) saturate(5) brightness(1.3)',          'emoji': '💜'},
]

@app.route('/api/fairik')
@login_required
def fairik_api():
    """Отдаёт данные пользователя для Файрика."""
    user = db.session.get(User, session['user_id'])
    if not user:
        return jsonify({'error': 'not found'}), 404
    skin_id = user.equipped_skin or 'default'
    skin    = next((s for s in SHOP_SKINS if s['id'] == skin_id), SHOP_SKINS[0])
    return jsonify({
        'level':    user.level  or 1,
        'xp':       user.xp     or 0,
        'streak':   user.streak or 0,
        'name':     user.name   or 'Ученик',
        'skin_css': skin['css'],
        'skin_id':  skin_id,
    })


# ====================== МАГАЗИН ======================
@app.route('/shop')
@login_required
def shop_page():
    user  = db.session.get(User, session['user_id'])
    owned = (user.owned_skins or 'default').split(',')
    return render_template('shop.html', current_user=user, skins=SHOP_SKINS,
                           owned=owned, equipped=user.equipped_skin or 'default')


@app.route('/api/shop/buy', methods=['POST'])
@login_required
def shop_buy():
    data    = request.get_json() or {}
    skin_id = data.get('skin_id')
    skin    = next((s for s in SHOP_SKINS if s['id'] == skin_id), None)
    if not skin:
        return jsonify({'error': 'Скин не найден'}), 404
    user  = db.session.get(User, session['user_id'])
    owned = (user.owned_skins or 'default').split(',')
    if skin_id in owned:
        return jsonify({'error': 'Уже куплен'}), 400
    if (user.xp or 0) < skin['price']:
        return jsonify({'error': f"Недостаточно XP. Нужно {skin['price']}"}), 400
    user.xp = (user.xp or 0) - skin['price']
    owned.append(skin_id)
    user.owned_skins = ','.join(owned)
    db.session.commit()
    logger.info(f"SHOP buy: user={user.id} skin={skin_id}")
    return jsonify({'ok': True, 'xp_left': user.xp})


@app.route('/api/shop/equip', methods=['POST'])
@login_required
def shop_equip():
    data    = request.get_json() or {}
    skin_id = data.get('skin_id')
    user    = db.session.get(User, session['user_id'])
    owned   = (user.owned_skins or 'default').split(',')
    if skin_id not in owned:
        return jsonify({'error': 'Не куплен'}), 400
    user.equipped_skin = skin_id
    db.session.commit()
    return jsonify({'ok': True})


# ════════════════════════════════════════════════════════
#  СИСТЕМА ДОЛГОСРОЧНОЙ ПАМЯТИ
# ════════════════════════════════════════════════════════

@app.route('/memory')
@login_required
def memory_page():
    """Страница памяти ошибок ученика."""
    user_id = session['user_id']
    user    = db.session.get(User, user_id)

    weak     = WeakTopic.query.filter_by(user_id=user_id, is_mastered=False)                              .order_by(WeakTopic.mastery_score.asc()).all()
    mastered = WeakTopic.query.filter_by(user_id=user_id, is_mastered=True)                              .order_by(WeakTopic.last_seen.desc()).limit(20).all()
    due      = get_topics_due(user_id)
    notes    = MemoryNote.query.filter_by(user_id=user_id)                               .order_by(MemoryNote.updated_at.desc()).limit(10).all()

    return render_template('memory.html',
                           current_user=user,
                           weak_topics=weak,
                           mastered_topics=mastered,
                           due_topics=due,
                           memory_notes=notes)


@app.route('/api/memory/due')
@login_required
def api_memory_due():
    """Возвращает темы для повторения сегодня."""
    due = get_topics_due(session['user_id'], limit=5)
    return jsonify([t.to_dict() for t in due])


@app.route('/api/memory/topics')
@login_required
def api_memory_topics():
    """Все слабые темы пользователя."""
    topics = WeakTopic.query.filter_by(
        user_id=session['user_id']
    ).order_by(WeakTopic.mastery_score.asc()).all()
    return jsonify([t.to_dict() for t in topics])


@app.route('/api/memory/review_start', methods=['POST'])
@login_required
def api_review_start():
    """Начинает сессию повторения — генерирует мини-урок по слабой теме."""
    data     = request.get_json() or {}
    topic_id = data.get('topic_id')

    wt = db.session.get(WeakTopic, topic_id)
    if not wt or wt.user_id != session['user_id']:
        return jsonify({'error': 'Тема не найдена'}), 404

    user       = db.session.get(User, session['user_id'])
    class_num  = user.class_number or 8
    interests  = user.interests    or ''

    # Строим персональный промпт для мини-повторения
    days_ago = (datetime.utcnow() - wt.first_seen).days

    system = f"""Ты — репетитор SubjectHelper. Отвечай только на русском языке.
Ученик: класс {class_num}, интересы: {interests or 'не указаны'}.

ЗАДАЧА: Проведи дружелюбное мини-повторение темы которую ученик плохо знает.

КОНТЕКСТ ОШИБКИ:
- Предмет: {wt.subject}
- Слабая тема: {wt.topic}
- Детали: {wt.details or 'нет деталей'}
- Ученик ошибался {wt.error_count} раз(а)
- Первый раз столкнулся {days_ago} дней назад
- Текущее освоение: {int(wt.mastery_score * 100)}%

ФОРМАТ ОТВЕТА (строго):
1. Начни с ТЁПЛОГО напоминания: «Помню, ты раньше путался с [тема]...»
2. Объясни суть за 3–4 предложения — максимально просто
3. Дай 1 конкретный пример
4. Задай 1 проверочный вопрос с 3 вариантами ответа (A, B, C)

Тон: как добрый старший друг, не как учитель. Используй примеры из интересов ученика."""

    prompt = f"Проведи мини-повторение по теме «{wt.topic}» (предмет: {wt.subject})."

    answer = ask_groq(prompt, system=system, max_tokens=600)

    # Создаём сессию повторения
    review = ReviewSession(
        user_id       = session['user_id'],
        weak_topic_id = wt.id,
    )
    db.session.add(review)
    db.session.commit()

    return jsonify({
        'review_id':  review.id,
        'topic':      wt.topic,
        'subject':    wt.subject,
        'error_count': wt.error_count,
        'mastery':    int(wt.mastery_score * 100),
        'content':    answer,
    })


@app.route('/api/memory/review_complete', methods=['POST'])
@login_required
def api_review_complete():
    """Завершает сессию повторения и обновляет SM-2."""
    data      = request.get_json() or {}
    review_id = data.get('review_id')
    score     = data.get('score', 3)  # 1–5

    review = db.session.get(ReviewSession, review_id)
    if not review or review.user_id != session['user_id']:
        return jsonify({'error': 'Не найдено'}), 404

    review.completed = True
    review.score     = score

    # Обновляем SM-2 (quality: score * 5/5 → 0–5)
    quality = round((score - 1) * 5 / 4)  # 1→0, 2→1.25, 3→2.5, 4→3.75, 5→5
    wt      = db.session.get(WeakTopic, review.weak_topic_id)
    if wt:
        sm2_update(wt, quality)
        # Начисляем XP
        user      = db.session.get(User, session['user_id'])
        user.xp   = (user.xp or 0) + (5 * score)
        user.level = user.xp // 100 + 1
        db.session.commit()

    return jsonify({
        'ok':           True,
        'mastery':      int(wt.mastery_score * 100) if wt else 0,
        'is_mastered':  wt.is_mastered if wt else False,
        'next_review':  wt.next_review.isoformat() if wt else None,
        'xp_gained':    5 * score,
    })


@app.route('/api/memory/add_error', methods=['POST'])
@login_required
def api_add_error():
    """Добавляет ошибку в память. Вызывается из quiz когда ученик ошибся."""
    data    = request.get_json() or {}
    subject = data.get('subject', '')
    topic   = data.get('topic', '')
    details = data.get('details', '')

    if not subject or not topic:
        return jsonify({'error': 'Нет данных'}), 400

    wt = add_weak_topic(session['user_id'], subject, topic, details)
    return jsonify({'ok': True, 'topic_id': wt.id})


@app.route('/api/memory/analyze', methods=['POST'])
@login_required
def api_memory_analyze():
    """
    ИИ анализирует последние ответы ученика и автоматически
    выявляет слабые темы + обновляет заметки.
    Вызывается раз в несколько сессий.
    """
    user_id = session['user_id']
    user    = db.session.get(User, user_id)

    # Берём последние 20 вопросов с низкими оценками
    recent_bad = History.query.join(Chat).filter(
        Chat.user_id == user_id,
        History.rating <= 2,
        History.rating != None,
    ).order_by(History.timestamp.desc()).limit(20).all()

    if not recent_bad:
        return jsonify({'ok': True, 'found': 0})

    # Формируем список для анализа
    items = []
    for h in recent_bad:
        items.append(f"Предмет: {h.subject} | Вопрос: {h.question[:120]} | Оценка: {h.rating}/5")

    system = """Ты — аналитик обучения. Отвечай ТОЛЬКО валидным JSON.
Твоя задача: найти паттерны слабых тем из истории ошибок."""

    prompt = f"""Проанализируй ошибки ученика и верни JSON:
{{
  "weak_topics": [
    {{"subject": "...", "topic": "...", "details": "...", "priority": 1-3}}
  ],
  "learning_style_note": "...",
  "strength_note": "..."
}}

ИСТОРИЯ ОШИБОК:
{chr(10).join(items)}

Верни только JSON, без пояснений."""

    try:
        raw    = ask_groq(prompt, system=system, max_tokens=600)
        match  = __import__('re').search(r'\{[\s\S]*\}', raw)
        parsed = __import__('json').loads(match.group(0)) if match else {}

        added = 0
        for wt_data in parsed.get('weak_topics', []):
            if wt_data.get('subject') and wt_data.get('topic'):
                add_weak_topic(
                    user_id  = user_id,
                    subject  = wt_data['subject'],
                    topic    = wt_data['topic'],
                    details  = wt_data.get('details', ''),
                )
                added += 1

        # Сохраняем заметки ИИ
        for note_type, key in [('learning_style', 'learning_style_note'),
                                ('strength',       'strength_note')]:
            if parsed.get(key):
                existing = MemoryNote.query.filter_by(
                    user_id=user_id, note_type=note_type
                ).first()
                if existing:
                    existing.content    = parsed[key]
                    existing.updated_at = datetime.utcnow()
                else:
                    db.session.add(MemoryNote(
                        user_id   = user_id,
                        note_type = note_type,
                        content   = parsed[key],
                    ))
        db.session.commit()
        return jsonify({'ok': True, 'found': added})

    except Exception as e:
        logger.error(f"Memory analyze error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/memory/daily_reminder')
@login_required
def api_daily_reminder():
    """
    Возвращает данные для ежедневного напоминания от Файрика.
    Вызывается при загрузке любой страницы.
    """
    user_id = session['user_id']
    due     = get_topics_due(user_id, limit=3)

    if not due:
        return jsonify({'has_reminder': False})

    # Берём самую срочную тему
    top   = due[0]
    days  = (datetime.utcnow() - top.first_seen).days
    month = top.first_seen.strftime('%B')

    messages = [
        f"Помнишь, {days} дней назад ты разбирал «{top.topic}» по {top.subject}? Давай повторим за 2 минуты! 🧠",
        f"У тебя есть {len(due)} тем{'а' if len(due)==1 else 'ы'} для повторения. Начнём с «{top.topic}»? 📚",
        f"Файрик помнит: «{top.topic}» — это было сложно. Проверим, стало ли лучше? 🐉",
    ]

    return jsonify({
        'has_reminder': True,
        'count':        len(due),
        'top_topic':    top.to_dict(),
        'message':      messages[hash(top.topic) % len(messages)],
    })


# ====================== НАСТРОЙКИ ======================
@app.route('/settings')
@login_required
def settings_page():
    user = db.session.get(User, session['user_id'])
    return render_template('settings.html', current_user=user)

@app.route('/api/settings/save', methods=['POST'])
@login_required
def settings_save():
    data = request.get_json() or {}
    user = db.session.get(User, session['user_id'])
    # Сохраняем тему и другие настройки в будущем
    # Пока только подтверждаем сохранение (тема хранится в localStorage)
    return jsonify({'ok': True})

# ====================== ЗАПУСК ======================
if __name__ == "__main__":
    os.makedirs("static/uploads", exist_ok=True)
    os.makedirs("static/avatars", exist_ok=True)
    from duel_server import socketio as _sio
    _sio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)