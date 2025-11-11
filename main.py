# main.py
from flask import Flask, request, jsonify, redirect, render_template, flash, session, url_for
from flask_cors import CORS
from flask_login import current_user
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
from werkzeug.utils import secure_filename
from functools import wraps
import os
import logging
from datetime import datetime

from models import db, User, History, save_history, get_history

# === ЛОГИРОВАНИЕ ===
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

# === ИИ ===
model_name = "EleutherAI/gpt-neo-125M"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)
model.eval()

if tokenizer.pad_token_id is None:
    tokenizer.pad_token_id = tokenizer.eos_token_id

if torch.cuda.is_available():
    model.to('cuda')

# === ДЕКОРАТОР ===
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Войдите в аккаунт.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# === МЕНЮ + JS — БЕЗ ДУБЛЕЙ ===
@app.context_processor
def inject_menu():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if not user:
            session.clear()
            flash('Сессия истекла. Войдите заново.', 'danger')
            return dict(menu='''
            <div class="header_registration">
              <a href="/register" class="start-button">Регистрация</a>
              <a href="/login" class="start-button">Вход</a>
            </div>
            ''', menu_js='')
        if user.avatar:
            avatar_html = f'<img src="{user.avatar}" class="menu-avatar" id="userCircle">'
        else:
            name = (user.name or "U")[0].upper()
            avatar_html = f'<div class="user-circle" id="userCircle">{name}</div>'

        menu = f'''
        <div class="user-menu">
          {avatar_html}

          <div class="dropdown-menu" id="dropdownMenu">
            <a href="{url_for('profile')}">Профиль</a>
            <a href="{url_for('history_page')}">История</a>
            <a href="{url_for('logout')}">Выйти</a>
          </div>
        </div>
        '''
        js = '''
        <script>
          document.addEventListener("DOMContentLoaded", () => {
            const c = document.getElementById("userCircle");
            const m = document.getElementById("dropdownMenu");
            if (c && m) {
              c.onclick = e => { e.stopPropagation(); m.style.display = m.style.display === "block" ? "none" : "block"; };
              document.onclick = () => m.style.display = "none";
            }
          });
        </script>
        '''
    else:
        menu = '''
        <div class="header_registration">
          <a href="/register" class="start-button">Регистрация</a>
          <a href="/login" class="start-button">Вход</a>
        </div>
        '''
        js = ''
    return dict(menu=menu, menu_js=js)

# === СТРАНИЦЫ ===
@app.route("/")
def welcome():
    return render_template("welcome.html")

@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html")

# === ПРОФИЛЬ===
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        nickname = request.form.get('nickname', '').strip()
        file = request.files.get('avatar')

        # === обновление ника ===
        if nickname and len(nickname) <= 20:
            user.name = nickname
            session['nickname'] = nickname
            flash('Ник обновлён!', 'success')

        if file and file.filename:
            filename = secure_filename(f"avatar_{user.id}.png")
            path = os.path.join("static/avatars", filename)
            os.makedirs("static/avatars", exist_ok=True)
            file.save(path)
            user.avatar = f"/static/avatars/{filename}"
            session['avatar'] = user.avatar  # 🔥 добавь вот это
            flash("Аватар обновлён!", "success")

        db.session.commit()

    history = get_history(user.id)
    total = len(history)
    rated = [h for h in history if h.rating]
    avg = round(sum(h.rating for h in rated)/len(rated), 1) if rated else 0
    subjects = {}
    for h in history:
        subjects[h.subject] = subjects.get(h.subject, 0) + 1
    top = max(subjects, key=subjects.get) if subjects else "—"

    return render_template('profile.html',
                           total_queries=total,
                           avg_rating=avg,
                           top_subject=top,
                           current_user=user)

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
        db.session.add(user)
        db.session.commit()
        flash("Регистрация успешна!", "success")
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
        flash("Неверно", "danger")
    return render_template("login.html")

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли.')
    return redirect(url_for('welcome'))

# === /ask ===
@app.route("/ask", methods=["POST"])
@login_required
def ask():
    question = request.form.get("question", "").strip()
    question = request.form.get('question', '').strip()
    if not question or question == "[только файл]":
        question = "Анализ прикреплённого файла"
    subject = request.form.get("subject", "Общее")
    mode = request.form.get("mode", "explain")
    user_id = session['user_id']

    if not question:
        return jsonify({"error": "Вопрос пуст"}), 400

    file_url = None
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename:
            fn = secure_filename(f"{user_id}_{file.filename}")
            path = os.path.join("static/uploads", fn)
            os.makedirs("static/uploads", exist_ok=True)
            file.save(path)
            file_url = f"/static/uploads/{fn}"

    prompts = {
        "explain": f"Объясни '{question}' просто.",
        "step": f"Реши '{question}' по шагам.",
        "quiz": f"5 вопросов по '{question}'.",
        "exam": f"План по '{question}'."
    }
    prompt = prompts.get(mode, "Ответь.")
    if file_url: prompt += f"\n[Файл: {file_url}]"

    try:
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
        if torch.cuda.is_available():
            inputs = {k: v.to('cuda') for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=200,
                do_sample=True,
                temperature=0.7,
                pad_token_id=tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id
            )

        answer = tokenizer.decode(outputs[0], skip_special_tokens=True)
        answer = answer[len(prompt):].strip() or "Извини, не смог ответить."

        hid = save_history(user_id, subject, mode, question, answer)
        entry = History.query.get(hid)
        ts = entry.timestamp.strftime("%H:%M")

        logger.info("="*60)
        logger.info(f"QID: {hid} | User: {user_id} | {subject} | {mode}")
        logger.info(f"Q: {question}")
        logger.info(f"A: {answer[:100]}...")
        logger.info(f"Time: {entry.timestamp}")
        logger.info("="*60)

        return jsonify({
            "answer": answer,
            "question_id": hid,
            "timestamp": ts
        })

    except Exception as e:
        logger.error(f"ASK ERROR: {e}", exc_info=True)
        return jsonify({"error": "Ошибка"}), 500

# === ИСТОРИЯ ===
@app.route('/history')
@login_required
def history_page():
    user = User.query.get(session['user_id'])
    if not user:
        flash("Пользователь не найден", "danger")
        return redirect(url_for('logout'))
    return render_template('history.html', current_user=user)

@app.route('/api/history', methods=['POST'])
@login_required
def api_history():
    h = get_history(session['user_id'])
    return jsonify([{
        "id": x.id,
        "subject": x.subject,
        "mode": x.mode,
        "question": x.question,
        "answer": x.answer,
        "timestamp": x.timestamp.strftime('%d.%m %H:%M'),
        "rating": x.rating or 0
    } for x in h])

@app.route("/rate", methods=["POST"])
@login_required
def rate():
    data = request.get_json() or {}
    hid = data.get("history_id")
    r = data.get("rating")
    if not hid or r not in (1,2,3,4,5):
        return jsonify({"error": "Нет"}), 400
    e = History.query.get(hid)
    if e and e.user_id == session['user_id']:
        e.rating = r
        db.session.commit()
        logger.info(f"RATE: QID {hid} → {r} stars")
        return jsonify({"ok": True})
    return jsonify({"error": "Не найдено"}), 404
@app.route('/update_avatar', methods=['POST'])
@login_required
def update_avatar():
    user = User.query.get(session['user_id'])
    if not user:
        flash('Ошибка: пользователь не найден.', 'danger')
        return redirect(url_for('logout'))

    file = request.files.get('avatar')
    if not file or not file.filename:
        flash('Файл не выбран.', 'warning')
        return redirect(url_for('profile'))

    # сохраняем аватар в папку static/avatars
    os.makedirs('static/avatars', exist_ok=True)
    filename = secure_filename(f"avatar_{user.id}.png")
    path = os.path.join('static/avatars', filename)
    file.save(path)

    # обновляем пользователя
    user.avatar = f"/static/avatars/{filename}"
    db.session.commit()
    session['avatar'] = user.avatar
    flash('✅ Аватар обновлён!', 'success')

    return redirect(url_for('profile'))


@app.route('/update_nickname', methods=['POST'])
@login_required
def update_nickname():
    user = User.query.get(session['user_id'])
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

# === ЗАПУСК ===
if __name__ == "__main__":
    os.makedirs("static/uploads", exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)