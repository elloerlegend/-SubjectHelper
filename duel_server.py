# ════════════════════════════════════════════════════════
#  ДУЭЛИ — Flask-SocketIO backend
#  Подключи к main.py (инструкция внизу файла)
# ════════════════════════════════════════════════════════
import json
import logging
import random
import string
from datetime import datetime

from flask_socketio import SocketIO, emit, join_room

logger = logging.getLogger(__name__)

# ── Инициализируется в attach_duel(app) ──
socketio = None

# ── Хранилище активных дуэлей (in-memory) ──
# duel_id → dict
active_duels = {}
# code → duel_id (быстрый поиск по коду)
code_to_duel = {}


# ══════════════════════════════════════════════════
#  ГЕНЕРАЦИЯ ВОПРОСОВ ЧЕРЕЗ GROQ
# ══════════════════════════════════════════════════
def generate_questions(subject: str, count: int, groq_client, model: str) -> list:
    """Генерирует N вопросов для дуэли через Groq."""
    system = (
        "Ты генератор вопросов для школьных дуэлей. "
        "Отвечай ТОЛЬКО валидным JSON-массивом. Никакого другого текста."
    )
    prompt = (
        f"Сгенерируй {count} вопросов по предмету «{subject}» для школьников.\n"
        "Каждый вопрос — объект:\n"
        '{"question": "текст", "options": ["A","B","C","D"], "correct_index": 0}\n'
        "correct_index — индекс правильного ответа (0-3).\n"
        "Вопросы разные, средней сложности. Ответь ТОЛЬКО JSON-массивом без комментариев."
    )
    try:
        resp = groq_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=1500,
            temperature=0.8,
        )
        raw = resp.choices[0].message.content.strip()
        # Извлекаем JSON-массив даже если модель добавила лишнее
        import re
        match = re.search(r'\[[\s\S]*\]', raw)
        if not match:
            raise ValueError("No JSON array found")
        questions = json.loads(match.group(0))
        # Валидируем структуру
        valid = []
        for q in questions:
            if (isinstance(q, dict)
                    and 'question' in q
                    and 'options' in q and len(q['options']) == 4
                    and 'correct_index' in q
                    and 0 <= int(q['correct_index']) <= 3):
                valid.append(q)
        if not valid:
            raise ValueError("Empty after validation")
        return valid[:count]
    except Exception as e:
        logger.error(f"generate_questions error: {e}")
        # Fallback — базовые вопросы
        return _fallback_questions(subject, count)


def _fallback_questions(subject: str, count: int) -> list:
    """Запасные вопросы если Groq недоступен."""
    pool = [
        {"question": f"Вопрос по {subject} №1", "options": ["Ответ A","Ответ B","Ответ C","Ответ D"], "correct_index": 0},
        {"question": f"Вопрос по {subject} №2", "options": ["Вариант 1","Вариант 2","Вариант 3","Вариант 4"], "correct_index": 1},
        {"question": f"Вопрос по {subject} №3", "options": ["Да","Нет","Может быть","Не знаю"], "correct_index": 0},
    ]
    result = []
    for i in range(count):
        result.append(pool[i % len(pool)])
    return result


# ══════════════════════════════════════════════════
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ══════════════════════════════════════════════════
def _gen_code() -> str:
    """Генерирует уникальный 7-символьный код: A7X-4K2"""
    while True:
        part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
        part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
        code = f"{part1}-{part2}"
        if code not in code_to_duel:
            return code


def _send_next_question(duel: dict) -> None:
    """Отправляет следующий вопрос обоим игрокам."""
    duel['current_q_idx'] += 1
    idx = duel['current_q_idx']

    if idx >= len(duel['questions']):
        _finish_duel(duel)
        return

    q   = duel['questions'][idx]
    room = duel['id']

    duel['q_answers'] = {}  # сбрасываем ответы на этот вопрос

    socketio.emit('next_question', {
        'q_num':      idx + 1,
        'question':   q['question'],
        'options':    q['options'],
        'time_limit': duel['t_per_q'],
    }, room=room)

    logger.info(f"DUEL {duel['code']} Q{idx+1}/{len(duel['questions'])}")


def _finish_duel(duel: dict) -> None:
    """Подсчитывает итог и отправляет game_over."""
    p1_id = duel['player1']['user_id']
    p2_id = duel['player2']['user_id']
    s1    = duel['scores'].get(str(p1_id), 0)
    s2    = duel['scores'].get(str(p2_id), 0)

    if s1 > s2:
        winner = p1_id
    elif s2 > s1:
        winner = p2_id
    else:
        winner = None  # ничья

    room = duel['id']
    socketio.emit('game_over', {
        'winner':    winner,
        'my_score':  s1,    # для p1 (каждый интерпретирует на клиенте)
        'opp_score': s2,
        'p1_score':  s1,
        'p2_score':  s2,
        'p1_id':     p1_id,
        'p2_id':     p2_id,
    }, room=room)

    # Начисляем XP через db (если передан)
    _award_xp(duel, winner, p1_id, p2_id, s1, s2)

    # Чистим память
    code_to_duel.pop(duel['code'], None)
    active_duels.pop(duel['id'], None)
    logger.info(f"DUEL {duel['code']} finished. Winner={winner}")


def _award_xp(duel, winner, p1_id, p2_id, s1, s2):
    """Начисляет XP победителю и участнику."""
    db = duel.get('_db')
    User = duel.get('_User')
    if not db or not User:
        return
    try:
        for uid, score, is_winner in [(p1_id, s1, winner==p1_id), (p2_id, s2, winner==p2_id)]:
            u = db.session.get(User, uid)
            if u:
                u.xp = (u.xp or 0) + (25 if is_winner else 10) + score * 2
                u.level = u.xp // 100 + 1
        db.session.commit()
    except Exception as e:
        logger.error(f"XP award error: {e}")


# ══════════════════════════════════════════════════
#  SOCKETIO СОБЫТИЯ
# ══════════════════════════════════════════════════
def _register_events(sio, groq_client, ai_model, db, User):
    """Регистрирует все SocketIO обработчики."""

    @sio.on('create_duel')
    def on_create_duel(data):
        user_id = data.get('user_id')
        name    = data.get('name', 'Игрок')
        subject = data.get('subject', 'Математика')
        mode    = data.get('mode', 'fast')
        q_count = int(data.get('q_count', 5))
        t_per_q = int(data.get('t_per_q', 15))

        code    = _gen_code()
        duel_id = f"duel_{code}"

        # Предварительно генерируем вопросы
        questions = generate_questions(subject, q_count, groq_client, ai_model)

        duel = {
            'id':            duel_id,
            'code':          code,
            'subject':       subject,
            'mode':          mode,
            'q_count':       q_count,
            't_per_q':       t_per_q,
            'questions':     questions,
            'current_q_idx': -1,
            'scores':        {},
            'q_answers':     {},
            'player1': {
                'user_id': user_id,
                'name':    name,
                'sid':     None,  # заполнится при join
            },
            'player2':   None,
            'started':   False,
            'created_at': datetime.utcnow(),
            '_db':    db,
            '_User':  User,
        }

        active_duels[duel_id] = duel
        code_to_duel[code]    = duel_id

        # Подключаем создателя в комнату
        join_room(duel_id)
        from flask import request as _req
        duel['player1']['sid'] = _req.sid

        emit('duel_created', {
            'duel_id': duel_id,
            'code':    code,
            'subject': subject,
        })
        logger.info(f"DUEL created: {code} by {name} ({subject})")


    @sio.on('join_duel')
    def on_join_duel(data):
        code    = data.get('code', '').strip().upper()
        user_id = data.get('user_id')
        name    = data.get('name', 'Соперник')

        duel_id = code_to_duel.get(code)
        if not duel_id:
            emit('error_msg', {'message': f'Дуэль с кодом {code} не найдена'})
            return

        duel = active_duels.get(duel_id)
        if not duel:
            emit('error_msg', {'message': 'Дуэль уже завершена'})
            return

        if duel['player2'] is not None:
            emit('error_msg', {'message': 'Дуэль уже заполнена'})
            return

        if duel['player1']['user_id'] == user_id:
            emit('error_msg', {'message': 'Нельзя сыграть с собой :)'})
            return

        duel['player2'] = {
            'user_id': user_id,
            'name':    name,
            'sid':     None,
        }
        duel['scores'][str(duel['player1']['user_id'])] = 0
        duel['scores'][str(user_id)] = 0

        join_room(duel_id)

        # Сообщаем создателю что соперник подключился
        socketio.emit('opponent_joined', {
            'user_id': user_id,
            'name':    name,
        }, room=duel_id)

        # Через секунду начинаем игру
        import threading
        def start_after_delay():
            import time; time.sleep(1.5)
            duel['started'] = True
            first_q = duel['questions'][0]
            duel['current_q_idx'] = 0
            duel['q_answers'] = {}
            socketio.emit('game_start', {
                'q_num':      1,
                'question':   first_q['question'],
                'options':    first_q['options'],
                'time_limit': duel['t_per_q'],
            }, room=duel_id)

        threading.Thread(target=start_after_delay, daemon=True).start()
        logger.info(f"DUEL {code}: {name} joined. Game starting.")


    @sio.on('answer')
    def on_answer(data):
        duel_id  = data.get('duel_id')
        user_id  = data.get('user_id')
        answer   = data.get('answer', -1)
        time_left = int(data.get('time_left', 0))

        duel = active_duels.get(duel_id)
        if not duel or not duel['started']:
            return

        idx = duel['current_q_idx']
        if idx < 0 or idx >= len(duel['questions']):
            return

        uid_str = str(user_id)
        if uid_str in duel['q_answers']:
            return  # уже ответил

        q = duel['questions'][idx]
        correct = int(q['correct_index'])
        is_correct = (answer == correct)

        # Очки: за скорость бонус
        points = 0
        if is_correct:
            points = 10 + min(time_left, 10)  # базово 10 + бонус за скорость (макс +10)

        duel['q_answers'][uid_str] = {
            'answer':     answer,
            'is_correct': is_correct,
            'points':     points,
        }
        duel['scores'][uid_str] = duel['scores'].get(uid_str, 0) + points

        # Сообщаем второму игроку что первый ответил
        socketio.emit('opponent_answered', {
            'user_id': user_id,
        }, room=duel_id)

        # Если оба ответили — показываем результат и переходим к следующему
        if len(duel['q_answers']) >= 2 or _only_one_player(duel):
            _resolve_question(duel)


    def _only_one_player(duel):
        """True если второй игрок отключился."""
        return duel['player2'] is None


    def _resolve_question(duel):
        """Отправляет итог вопроса и запускает следующий."""
        idx     = duel['current_q_idx']
        q       = duel['questions'][idx]
        correct = int(q['correct_index'])
        room    = duel['id']

        p1_id = str(duel['player1']['user_id'])
        p2_id = str(duel['player2']['user_id']) if duel['player2'] else None

        socketio.emit('question_result', {
            'correct_index': correct,
            'my_answer':     duel['q_answers'].get(p1_id, {}).get('answer', -1),
            'opp_answer':    duel['q_answers'].get(p2_id, {}).get('answer', -1) if p2_id else -1,
            'my_score':      duel['scores'].get(p1_id, 0),
            'opp_score':     duel['scores'].get(p2_id, 0) if p2_id else 0,
            'explanation':   q.get('explanation', ''),
        }, room=room)

        import threading, time
        def next_q():
            time.sleep(2.0)
            _send_next_question(duel)
        threading.Thread(target=next_q, daemon=True).start()


    @sio.on('disconnect')
    def on_disconnect():
        # Ищем дуэль по SID и уведомляем соперника
        for duel in list(active_duels.values()):
            pass  # упрощённо — в реальном проекте нужен sid→duel mapping
        logger.info("Client disconnected")


# ══════════════════════════════════════════════════
#  ТОЧКА ПОДКЛЮЧЕНИЯ К main.py
# ══════════════════════════════════════════════════
def attach_duel(app, groq_client, ai_model, db, User):
    """
    Вызови эту функцию в main.py ПОСЛЕ создания app.

    Пример в main.py:
        from duel_server import attach_duel, socketio
        attach_duel(app, client, AI_MODEL, db, User)
        # И запускай через socketio.run():
        # socketio.run(app, debug=True, host='0.0.0.0', port=5000)
    """
    global socketio
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode='threading',
        logger=False,
        engineio_logger=False,
    )

    # Маршрут страницы дуэлей
    from flask import render_template, session, redirect, url_for
    from functools import wraps

    def login_required_duel(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated

    @app.route('/duel')
    @login_required_duel
    def duel_page():
        return render_template('duel.html')

    _register_events(socketio, groq_client, ai_model, db, User)
    logger.info("✅ Duel module attached (Flask-SocketIO)")
    return socketio