from flask import Flask, request, jsonify, redirect, render_template, flash, session, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
from functools import wraps
import os
import logging
from datetime import datetime, timedelta

from groq import Groq
from dotenv import load_dotenv
load_dotenv()

from models import db, User, History, Chat, save_history, get_history, DuelSession

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


def ask_groq(prompt: str, system: str = None, max_tokens: int = 1000) -> str:
    """Запрос к Groq API."""
    try:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
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

def build_cluster_profile(class_number: int, subject: str, user_stats: dict) -> str:
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

    return persona + personal


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
            <a href="{url_for('leaderboard')}">🏆 Лидерборд</a>
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
    # Топ по XP за эту неделю
    from datetime import datetime, timedelta
    week_ago = datetime.now() - timedelta(days=7)

    # Все пользователи отсортированные по XP
    top_users = User.query.order_by(User.xp.desc()).limit(50).all()

    # Позиция текущего пользователя
    current = db.session.get(User, session['user_id'])
    all_by_xp = User.query.order_by(User.xp.desc()).all()
    my_rank = next((i+1 for i,u in enumerate(all_by_xp) if u.id == current.id), 0)

    return render_template('leaderboard.html',
                           top_users=top_users,
                           current_user=current,
                           my_rank=my_rank)

@app.route('/duel/create', methods=['POST'])
@login_required
def duel_create():
    subject = request.json.get('subject', 'Математика')
    duel = DuelSession(player1_id=session['user_id'], subject=subject)
    db.session.add(duel); db.session.commit()
    return jsonify({'duel_id': duel.id, 'status': 'waiting'})

@app.route('/duel/join/<int:duel_id>', methods=['POST'])
@login_required
def duel_join(duel_id):
    duel = db.session.get(DuelSession, duel_id)
    if not duel or duel.status != 'waiting':
        return jsonify({'error': 'Дуэль недоступна'}), 400
    duel.player2_id = session['user_id']
    duel.status = 'active'
    db.session.commit()
    return jsonify({'ok': True})

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

    answer = ask_groq(question, system=system, max_tokens=800)

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
        return redirect(url_for('profile'))
    os.makedirs('static/avatars', exist_ok=True)
    filename = secure_filename(f"avatar_{user.id}.png")
    file.save(os.path.join('static/avatars', filename))
    user.avatar = f"/static/avatars/{filename}"
    db.session.commit()
    session['avatar'] = user.avatar
    flash('✅ Аватар обновлён!', 'success')
    return redirect(url_for('profile'))


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


# ====================== ЗАПУСК ======================
if __name__ == "__main__":
    os.makedirs("static/uploads", exist_ok=True)
    os.makedirs("static/avatars", exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)