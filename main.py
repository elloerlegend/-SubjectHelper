from flask import Flask, request, jsonify, redirect, render_template, flash, session, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
from functools import wraps
import os
import logging
from datetime import datetime, date, timedelta

from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

from models import db, User, History, Chat, save_history, get_history

# ====================== НАСТРОЙКИ ======================
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = '7e4c956c8ab1a339f9f347927f09fa30de5dd8d1539f930e146f9d5c693389df'
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

with app.app_context():
    db.init_app(app)
    db.create_all()

# ====================== ИИ ======================
model_name = "EleutherAI/gpt-neo-125M"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)
model.eval()

if tokenizer.pad_token_id is None:
    tokenizer.pad_token_id = tokenizer.eos_token_id
if torch.cuda.is_available():
    model.to('cuda')


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
    """Получить всю историю пользователя (для профиля)"""
    return History.query.join(Chat).filter(Chat.user_id == user_id).order_by(History.timestamp.desc()).all()


# ====================== МЕНЮ ======================
@app.context_processor
def inject_menu():
    if 'user_id' in session:
        # ИСПРАВЛЕНО: используем db.session.get вместо User.query.get
        user = db.session.get(User, session['user_id'])
        if not user:
            session.clear()
            return dict(menu='', menu_js='')

        avatar_html = f'<img src="{user.avatar}" class="menu-avatar" id="userCircle">' if user.avatar else \
            f'<div class="user-circle" id="userCircle">{(user.name or "U")[0].upper()}</div>'

        menu = f'''
        <div class="user-menu">
          {avatar_html}
          <div class="dropdown-menu" id="dropdownMenu">
            <a href="{url_for('profile')}">Профиль</a>
            <a href="{url_for('chats_list')}">Мои чаты</a>
            <a href="{url_for('history_page')}">История</a>
            <a href="{url_for('logout')}">Выйти</a>
          </div>
        </div>
        '''
        js = '''<script>document.addEventListener("DOMContentLoaded", () => {{
            const c = document.getElementById("userCircle"), m = document.getElementById("dropdownMenu");
            if (c && m) {{
              c.onclick = e => {{ e.stopPropagation(); m.style.display = m.style.display === "block" ? "none" : "block"; }};
              document.onclick = () => m.style.display = "none";
            }}
        }});</script>'''
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


# === ПРОФИЛЬ (ДОБАВЛЕН) ===
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = db.session.get(User, session['user_id'])
    if not user:
        flash("Пользователь не найден", "danger")
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

    # Получаем историю через новую функцию
    history = get_user_history(user.id)
    total = len(history)
    rated = [h for h in history if h.rating]
    avg = round(sum(h.rating for h in rated) / len(rated), 1) if rated else 0

    subjects = {}
    for h in history:
        subjects[h.subject] = subjects.get(h.subject, 0) + 1
    top = max(subjects, key=subjects.get) if subjects else "—"
    max_queries = max(subjects.values()) if subjects else 1

    # Геймификация
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

    # Качество знаний
    quality = {}
    for h in history:
        if h.rating:
            quality[h.subject] = quality.get(h.subject, []) + [h.rating]
    for s in quality:
        quality[s] = round(sum(quality[s]) / len(quality[s]), 1) if quality[s] else 0

    weak_subject = min(quality, key=quality.get, default="—") if quality else "—"

    # График
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


# === ЧАТ (исправлен) ===
@app.route("/chat")
@login_required
def chat():
    # Если нет текущего чата, создаем временный или перенаправляем на список чатов
    if 'current_chat_id' not in session:
        return redirect(url_for('chats_list'))
    return render_template("chat.html")


# === СПИСОК ВСЕХ ЧАТОВ ===
@app.route("/chats")
@login_required
def chats_list():
    user_id = session['user_id']
    chats = Chat.query.filter_by(user_id=user_id, has_messages=True).order_by(Chat.updated_at.desc()).all()
    return render_template("chats.html", chats=chats)


# === СОЗДАНИЕ НОВОГО ЧАТА ===
@app.route("/new_chat", methods=["POST"])
@login_required
def new_chat():
    subject = request.form.get("subject", "Математика")
    class_number = int(request.form.get("class_number", 8))
    mode = request.form.get("mode", "explain")

    title = f"{subject} — {class_number} класс ({mode})"

    chat = Chat(
        user_id=session['user_id'],
        subject=subject,
        class_number=class_number,
        mode=mode,
        title=title
    )
    db.session.add(chat)
    db.session.commit()

    session['current_chat_id'] = chat.id
    flash(f"Создан новый чат: {title}", "success")
    return redirect(url_for('open_chat', chat_id=chat.id))


# === ОТКРЫТЬ КОНКРЕТНЫЙ ЧАТ ===
@app.route("/chat/<int:chat_id>")
@login_required
def open_chat(chat_id):
    chat = Chat.query.get_or_404(chat_id)
    if chat.user_id != session['user_id']:
        flash("Доступ запрещён", "danger")
        return redirect(url_for('chats_list'))

    session['current_chat_id'] = chat_id
    messages = get_history(chat_id)
    return render_template("chat.html", chat=chat, messages=messages)


# === ИСТОРИЯ (для страницы истории) ===
@app.route('/history')
@login_required
def history_page():
    user = db.session.get(User, session['user_id'])
    if not user:
        flash("Пользователь не найден", "danger")
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
        "id": x.id,
        "subject": x.subject,
        "mode": x.mode,
        "question": x.question,
        "answer": x.answer,
        "timestamp": x.timestamp.strftime('%d.%m %H:%M'),
        "rating": x.rating or 0
    } for x in history])


# === ОСНОВНОЙ ЗАПРОС К ИИ ===
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
    subject = chat.subject
    mode = chat.mode

    # Генерация промпта в зависимости от режима
    prompts = {
        "explain": f"Объясни '{question}' просто и понятно школьнику.",
        "step": f"Реши '{question}' по шагам с объяснениями.",
        "quiz": f"Составь 5 вопросов по теме '{question}'.",
        "exam": f"Составь план подготовки по теме '{question}'."
    }
    prompt = prompts.get(mode, "Ответь подробно.")

    try:
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
        if torch.cuda.is_available():
            inputs = {k: v.to('cuda') for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=300,
                do_sample=True,
                temperature=0.7,
                pad_token_id=tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id
            )

        answer = tokenizer.decode(outputs[0], skip_special_tokens=True)
        answer = answer[len(prompt):].strip() or "Извини, не смог ответить."

        hid = save_history(chat_id, subject, mode, question, answer)

        # Начисление XP
        user = db.session.get(User, session['user_id'])
        user.xp += 10
        user.level = user.xp // 100 + 1
        db.session.commit()

        entry = History.query.get(hid)
        ts = entry.timestamp.strftime("%H:%M")

        return jsonify({
            "answer": answer,
            "question_id": hid,
            "timestamp": ts
        })

    except Exception as e:
        logger.error(f"ASK ERROR: {e}", exc_info=True)
        return jsonify({"error": "Ошибка сервера"}), 500


# === ПЛАН ПРАКТИКИ ===
@app.route("/plan", methods=["POST"])
@login_required
def generate_plan():
    data = request.get_json() or {}
    subject = data.get("subject", "Математика").strip()
    user = db.session.get(User, session['user_id'])

    prompt = f"""Ты — лучший репетитор SubjectHelper.
Составь план практики по предмету "{subject}" на 7 дней.

ОТВЕЧАЙ ТОЛЬКО ЭТИМ ФОРМАТОМ, БЕЗ ЛИШНИХ СЛОВ:

ДЕНЬ 1: Краткое название
• Задание 1
• Задание 2
• Задание 3
Самопроверка: ...

(и так до ДЕНЬ 7)

Итоговая цель недели: ...

Сделай план весёлым и мотивирующим, учитывая стрик {user.streak} дней."""

    try:
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
        if torch.cuda.is_available():
            inputs = {k: v.to('cuda') for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=700,
                do_sample=True,
                temperature=0.5,
                pad_token_id=tokenizer.eos_token_id
            )

        plan = tokenizer.decode(outputs[0], skip_special_tokens=True)
        plan = plan[len(prompt):].strip()

        # Создаем временный чат для плана или используем текущий
        chat_id = session.get('current_chat_id')
        if not chat_id:
            # Создаем чат для плана
            new_chat = Chat(
                user_id=user.id,
                subject=subject,
                class_number=8,
                mode="plan",
                title=f"План по {subject}"
            )
            db.session.add(new_chat)
            db.session.commit()
            chat_id = new_chat.id

        save_history(chat_id, subject, "plan", f"План по {subject}", plan)
        return jsonify({"plan": plan})

    except Exception as e:
        logger.error(f"PLAN ERROR: {e}")
        return jsonify({"plan": "Извини, не смог создать план. Попробуй ещё раз."}), 500


# === РЕГИСТРАЦИЯ / ЛОГИН ===
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
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
        user.streak = 0
        user.xp = 0
        user.level = 1
        user.badges = ''

        db.session.add(user)
        db.session.commit()
        flash("Регистрация успешна! Добро пожаловать в SubjectHelper 🎉", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
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


# === ОЦЕНКА ОТВЕТА ===
@app.route("/rate", methods=["POST"])
@login_required
def rate():
    data = request.get_json() or {}
    hid = data.get("history_id")
    r = data.get("rating")
    if not hid or r not in (1,2,3,4,5):
        return jsonify({"error": "Нет"}), 400
    e = History.query.get(hid)
    if e and e.chat.user_id == session['user_id']:  # Проверяем через chat
        e.rating = r
        db.session.commit()
        logger.info(f"RATE: QID {hid} → {r} stars")
        return jsonify({"ok": True})
    return jsonify({"error": "Не найдено"}), 404


# === ОБНОВЛЕНИЕ АВАТАРА И НИКА ===
@app.route('/update_avatar', methods=['POST'])
@login_required
def update_avatar():
    user = db.session.get(User, session['user_id'])
    if not user:
        flash('Ошибка: пользователь не найден.', 'danger')
        return redirect(url_for('logout'))

    file = request.files.get('avatar')
    if not file or not file.filename:
        flash('Файл не выбран.', 'warning')
        return redirect(url_for('profile'))

    os.makedirs('static/avatars', exist_ok=True)
    filename = secure_filename(f"avatar_{user.id}.png")
    path = os.path.join('static/avatars', filename)
    file.save(path)

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
        flash('Ошибка: пользователь не найден.', 'danger')
        return redirect(url_for('logout'))

    nickname = request.form.get('nickname', '').strip()
    if not nickname:
        flash('Введите никнейм.', 'warning')
        return redirect(url_for('profile'))
    if len(nickname) > 20:
        flash('Никнейм слишком длинный (до 20 символов).', 'warning')
        return redirect(url_for('profile'))

    user.name = nickname
    db.session.commit()
    session['nickname'] = nickname
    flash('✅ Ник успешно изменён!', 'success')
    return redirect(url_for('profile'))


# ====================== ЗАПУСК ======================
if __name__ == "__main__":
    os.makedirs("static/uploads", exist_ok=True)
    os.makedirs("static/avatars", exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)