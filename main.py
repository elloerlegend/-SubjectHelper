from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import flask_sqlalchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'  # путь к БД
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.secret_key = 'your_secret_key'
db = SQLAlchemy(app)

# Модель пользователя
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(150), nullable=True)




model_name = "EleutherAI/gpt-neo-125M"


tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

model.eval()


@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json()
    question = data.get("question")
    subject = data.get("subject")
    mode = data.get("mode")

    if mode == "explain":
        prompt = f"""
Ты — опытный и доброжелательный школьный репетитор по предмету "{subject}".

Объясни тему ниже так, чтобы понял ученик 8–10 класса, который не знает ничего.

Тема: {question}

Используй понятный язык, простые примеры, аналогии, бытовые ситуации.
Не используй сложных терминов без объяснения.

Объяснение:
"""

    elif mode == "step":
        prompt = f"""
Ты — учитель по предмету "{subject}". Реши задачу ниже по шагам, объясняя каждое действие, как будто объясняешь ученику 9 класса.

Задача: {question}

Решение по шагам:
"""

    elif mode == "quiz":
        prompt = f"""
Ты — школьный репетитор по предмету "{subject}". Задай несколько коротких вопросов ученику по теме ниже, чтобы проверить его знания.

Тема: {question}

Вопросы:
"""

    elif mode == "exam":
        prompt = f"""
Ты — школьный репетитор по предмету "{subject}". Составь план подготовки к экзамену по теме ниже, включая что учить, как тренироваться и какие советы ты можешь дать.

Тема: {question}

План подготовки:
"""

    else:
        # Если  неизвестный режим — выдадим ошибку
        return jsonify({"answer": "Неизвестный режим обучения"}), 400


    inputs = tokenizer(prompt, return_tensors="pt")

    outputs = model.generate(
        **inputs,
        max_length=inputs.input_ids.shape[1] + 400,
        do_sample=True,
        temperature=0.8
    )

    full_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    answer = full_text[len(prompt):].strip()

    return jsonify({"answer": answer})


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # проверка, существует ли уже email
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return 'Такой email уже зарегистрирован'

        hashed_password = generate_password_hash(password, method='sha256')
        new_user = User(email=email, password=hashed_password)

        db.session.add(new_user)
        db.session.commit()

        return redirect('/login')
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['email'] = user.email
            return redirect(url_for('dashboard'))
        else:
            return "Неверный логин или пароль"
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' in session:
        return f"Привет, {session['username']}! <a href='/logout'>Выйти</a>"
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'



@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.username = request.form['username']
        db.session.commit()
        return redirect('/profile')
    return render_template('profile.html', user=current_user)


if __name__ == "__main__":
    app.run(debug=True)
