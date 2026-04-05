from flask import Flask, request, jsonify, redirect, render_template, flash, session, url_for
from flask_cors import CORS
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from functools import wraps
from typing import Optional
import os
import json as _json
import logging
import re
from datetime import datetime, timedelta, date
from duel_server import attach_duel, socketio as duel_socketio
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

from models import (
    db, User, History, Chat, save_history, get_history,
    WeakTopic, ReviewSession, MemoryNote, LearningPath,
    add_weak_topic, sm2_update, get_topics_due, get_user_memory_context,
)
from subject_ru import subject_po, decline_subject

# ====================== НАСТРОЙКИ ======================
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
migrate = Migrate(app, db)
app.secret_key = os.environ.get('SECRET_KEY', '7e4c956c8ab1a339f9f347927f09fa30de5dd8d1539f930e146f9d5c693389df')
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

def _migrate_learning_path_columns():
    """Добавляет колонки в SQLite без Alembic (уже существующие таблицы)."""
    try:
        from sqlalchemy import text
        with db.engine.begin() as conn:
            rows = conn.execute(text("PRAGMA table_info(learning_path)")).fetchall()
            colnames = {row[1] for row in rows}
            if 'sprint_confidence' not in colnames:
                conn.execute(text(
                    "ALTER TABLE learning_path ADD COLUMN sprint_confidence VARCHAR(20)"
                ))
                logger.info("DB: column sprint_confidence added to learning_path")
    except Exception as e:
        logger.warning("DB migration learning_path: %s", e)


def _migrate_chat_columns():
    """Добавляет submode и math_level в таблицу chat если их нет."""
    try:
        from sqlalchemy import text
        with db.engine.begin() as conn:
            rows     = conn.execute(text("PRAGMA table_info(chat)")).fetchall()
            colnames = {row[1] for row in rows}
            if 'submode' not in colnames:
                conn.execute(text("ALTER TABLE chat ADD COLUMN submode VARCHAR(50) DEFAULT ''"))
                logger.info("DB: column submode added to chat")
            if 'math_level' not in colnames:
                conn.execute(text("ALTER TABLE chat ADD COLUMN math_level VARCHAR(20) DEFAULT ''"))
                logger.info("DB: column math_level added to chat")
    except Exception as e:
        logger.warning("DB migration chat: %s", e)


with app.app_context():
    db.init_app(app)
    db.create_all()
    _migrate_learning_path_columns()
    _migrate_chat_columns()

# ====================== GROQ ======================
client = Groq(api_key=os.environ.get('GROQ_API_KEY'))
AI_MODEL = "llama-3.3-70b-versatile"
attach_duel(app, client, AI_MODEL, db, User)


def ask_groq(prompt: str, system: str = None, max_tokens: int = 1000,
             chat_history: list = None) -> str:
    try:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
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


# ════════════════════════════════════════════════════════
#  LEARNING PATH — вспомогательные функции
# ════════════════════════════════════════════════════════

def get_active_path(user_id: int, subject: str):
    """
    Возвращает активный LearningPath для предмета или None (→ Casual).
    Sprint автоматически деактивируется после дедлайна + 1 день.
    """
    path = LearningPath.query.filter_by(
        user_id=user_id, subject=subject, is_active=True
    ).order_by(LearningPath.last_active.desc()).first()

    if not path:
        return None

    # Автодеактивация просроченного Sprint
    if path.mode == 'sprint' and path.sprint_deadline:
        if date.today() > path.sprint_deadline + timedelta(days=1):
            path.is_active   = False
            path.sprint_done = True
            db.session.commit()
            return None

    return path


def _build_mode_block(path) -> str:
    """
    Генерирует блок инструкций режима для системного промпта ИИ.
    path=None  →  Casual
    path.mode='sprint'  →  Sprint
    path.mode='journey' →  Journey
    """
    if path is None:
        return """

═══ РЕЖИМ: CASUAL ═══
Ученик задаёт разовый вопрос — домашка, непонятная тема, быстрый ответ.
Никакой долгосрочной цели нет.
ПРАВИЛА:
— Отвечай чётко и по делу, не перегружай лишней информацией
— После ответа предложи 1 вопрос для самопроверки
— Если тема сложная — спроси "хочешь разберём подробнее?"
— Не строй планов, не предлагай курсы — просто закрой этот вопрос
═════════════════════"""

    if path.mode == 'sprint':
        days        = path.days_left()
        topics_all  = path.get_sprint_topics()
        topics_done = path.get_sprint_done()
        topics_left = [t for t in topics_all if t not in topics_done]

        if days == 0:
            urgency    = "ФИНАЛЬНЫЙ ПРОГОН — ДЕДЛАЙН СЕГОДНЯ"
            final_note = "Режим финального прогона: только самое важное, только то что точно спросят. Кратко и по делу."
        elif days == 1:
            urgency    = "КРИТИЧЕСКИ МАЛО ВРЕМЕНИ — ЗАВТРА ДЕДЛАЙН"
            final_note = "Максимально фокусируйся на ключевых формулах и типовых задачах."
        else:
            urgency    = f"ИНТЕНСИВНЫЙ РЕЖИМ — осталось {days} дней"
            final_note = ""

        conf = (path.sprint_confidence or '').strip()
        conf_human = {
            'weak':     'слабо разбирается — объясняй от базы, короткими шагами',
            'medium':   'средне — можно опираться на базу, меньше воды в теории',
            'strong':   'уверенно — цель «дотянуть до идеала»: типовые ошибки, экзаменный формат, шлифовка',
        }.get(conf, 'самооценка не указана — выясни коротким вопросом в начале')

        deadline_line = 'не указан'
        if path.sprint_deadline:
            deadline_line = (
                f"{path.sprint_deadline.strftime('%d.%m.%Y')} "
                f"(осталось дней: {days if days is not None else '?'})"
            )

        subj_po = decline_subject(path.subject)

        if topics_all:
            topics_full = ', '.join(topics_all)
            topics_plan = (
                f"Полный список тем Sprint (держись ТОЛЬКО его, не выдумывай новые учебные блоки без запроса ученика):\n{topics_full}\n"
                f"Уже закрыто: {', '.join(topics_done) if topics_done else 'ничего'}\n"
                f"В фокусе сейчас: {', '.join(topics_left) if topics_left else 'все темы закрыты — итоговый повтор'}"
            )
        else:
            topics_plan = (
                "Список тем в базе пуст — опирайся на цель и дедлайн, предложи явный мини-план из 3–5 тем и согласуй с учеником."
            )

        return f"""

═══ РЕЖИМ: SPRINT — {urgency} ═══
Предмет (формулировки для ученика: «по {subj_po}»): {path.subject}
Цель ученика: {path.sprint_goal or 'не указана'}
Дедлайн: {deadline_line}
Ученик о своей подготовке по теме: {conf_human}
{topics_plan}
{final_note}

ОНБОРДИНГ И ПЕРСОНАЛИЗАЦИЯ (если ещё не ответил — мягко спроси; если уже ответил — используй в каждом объяснении):
— По какому учебнику работает ученик (авторы, название, издательство, класс/часть)?
— Какая программа / уровень (ФГОС, база/углублённый, ОГЭ/ЕГЭ-ориентация)?
— Какие темы из списка Sprint уже проходили в классе и насколько уверенно?
— Есть ли конкретное домашнее задание, номера из сборника или формат контрольной (если цель — контрольная)?
Запоминай ответы и подстраивай формулировки, примеры и номера заданий под указанный учебник и программу.

ПРАВИЛА SPRINT:
— Только материал этих конкретных тем — ничего лишнего
— Темп быстрый, без длинных отступлений в теорию
— После каждого блока: "📌 Запомни: [1 ключевой факт]"
— Ошибка → не объясняй с нуля: "[Правило одной строкой]. Попробуй ещё раз"
— Отмечай прогресс вслух, создавай ощущение что мы движемся
— Тон как у тренера: уверенный, конкретный, поддерживающий
═══════════════════════════════════════"""

    if path.mode == 'journey':
        roadmap = path.get_roadmap()
        current = path.get_current_unit_data()
        strong  = path.get_probe_strong()
        weak    = path.get_probe_weak()

        return f"""

═══ РЕЖИМ: JOURNEY ═══
Цель ученика: {path.journey_goal or 'не указана'}
Уровень входа: {path.journey_level or 'не определён'}
Прогресс: Юнит {path.current_unit} из {len(roadmap)} | Сессий завершено: {path.sessions_done}
Текущий юнит: {current.get('title', '—')}
Темы юнита: {', '.join(current.get('topics', []))}
Сильные стороны (пробник): {', '.join(strong[:3]) if strong else 'определяем в процессе'}
Пробелы (пробник): {', '.join(weak[:3]) if weak else 'определяем в процессе'}
ПРАВИЛА JOURNEY:
— Ты долгосрочный наставник — терпеливый, системный, глубокий
— Строй знания слоями, каждая тема опирается на предыдущую
— Периодически ссылайся на прошлое: "Помнишь из юнита N..."
— Ошибки важны — они уйдут в систему повторений SM-2
— Темп спокойный: лучше меньше, но надёжно, без спешки
— В конце каждой сессии: "Сегодня разобрали [тема]. Следующий раз: [следующая]"
— Если тема из пробника (слабое место) стала лёгкой — отметь это явно: "Помнишь, раньше это было сложно?"
— Тон как у наставника который помнит историю ученика
═══════════════════════════════════════"""

    return ""


def _generate_journey_roadmap(subject, goal, level, weak, strong, minutes_per_week):
    """Генерирует roadmap для Journey через Groq. Возвращает список юнитов."""
    system = (
        "Ты — методист образовательного проекта. "
        "Отвечай ТОЛЬКО валидным JSON-массивом без пояснений и markdown."
    )
    prompt = f"""Составь учебный roadmap по предмету «{subject}» для ученика.
Цель: {goal}
Уровень входа: {level}
Уже знает хорошо: {', '.join(strong[:5]) if strong else 'не определено'}
Пробелы: {', '.join(weak[:5]) if weak else 'не определено'}
Времени в неделю: {minutes_per_week} минут

Верни JSON-массив из 6-12 юнитов (в зависимости от объёма предмета и цели):
[
  {{
    "unit": 1,
    "title": "Название юнита",
    "topics": ["Тема 1", "Тема 2", "Тема 3"],
    "sessions_needed": 3,
    "skip_if_strong": false
  }}
]

skip_if_strong=true если эта тема уже в сильных сторонах ученика.
Только JSON-массив, без markdown, без объяснений."""

    raw   = ask_groq(prompt, system=system, max_tokens=1200)
    match = re.search(r'\[[\s\S]*\]', raw)
    if match:
        try:
            return _json.loads(match.group(0))
        except Exception:
            pass
    # Fallback
    logger.warning(f"Journey roadmap generation failed for {subject}, using fallback")
    return [{"unit": 1, "title": subject, "topics": [], "sessions_needed": 5, "skip_if_strong": False}]


def _generate_sprint_topics(
    subject: str,
    goal: str,
    deadline: Optional[date],
    confidence: str | None,
    user_topics: list,
) -> list:
    """
    Если ученик уже указал темы — возвращаем их.
    Иначе генерируем короткий список тем под цель и дедлайн (Groq).
    """
    clean = [str(t).strip() for t in (user_topics or []) if str(t).strip()]
    if clean:
        return clean[:20]

    dl_note = ""
    if deadline:
        left = max(0, (deadline - date.today()).days)
        dl_note = f"Дедлайн: {deadline.isoformat()} (осталось дней: {left})."

    system = (
        "Ты — методист школы. Отвечай ТОЛЬКО валидным JSON-массивом строк (названия тем). "
        "Без markdown и без пояснений."
    )
    prompt = f"""Предмет: «{subject}».
Цель спринта: {goal or 'подготовка'}.
{dl_note}
Самооценка ученика: {confidence or 'не указана'}.

Подбери 5–8 конкретных учебных тем/подтем (короткие названия, как в школьной программе), которых достаточно для этой цели к дедлайну.
Верни JSON-массив строк. Только JSON."""

    raw = ask_groq(prompt, system=system, max_tokens=500)
    match = re.search(r'\[[\s\S]*\]', raw)
    if match:
        try:
            arr = _json.loads(match.group(0))
            if isinstance(arr, list) and arr:
                out = [str(x).strip() for x in arr if str(x).strip()]
                return out[:12] if out else []
        except Exception:
            pass
    logger.warning(f"Sprint topic generation fallback for subject={subject}")
    return [g for g in [(goal or "").strip(), subject] if g][:3]


# ====================== ПРОМПТЫ ======================

def build_cluster_profile(class_number: int, subject: str, user_stats: dict,
                           user_id: int = None, learning_path=None) -> str:
    """
    Строит персонализированный профиль ученика для системного промпта.
    learning_path=None → Casual, иначе Sprint/Journey.
    """
    if class_number <= 4:
        persona = (
            "ТЫ ГОВОРИШЬ С МЛАДШЕКЛАССНИКОМ (7–10 лет). ПРАВИЛА ОБЯЗАТЕЛЬНЫ:\n"
            "— Максимум 3 предложения на одну мысль. Короче = лучше.\n"
            "— НИКАКИХ терминов без объяснения прямо в тексте.\n"
            "— Всегда используй сравнения с играми, животными, едой, мультиками.\n"
            "— Используй смайлы умеренно: 1–2 на сообщение.\n"
            "— В конце ВСЕГДА задай один простой вопрос на проверку.\n"
            "— Хвали за каждый ответ: «Молодец!», «Отлично соображаешь!»\n"
            "— Если ошибся — НИКОГДА не говори «неправильно». Говори: «Почти! Давай попробуем вместе 🤝»\n"
        )
    elif class_number <= 7:
        persona = (
            "ТЫ ГОВОРИШЬ С УЧЕНИКОМ 5–7 КЛАССА (11–14 лет). ПРАВИЛА:\n"
            "— Общайся как старший друг, не как учитель. Можно лёгкий юмор.\n"
            "— Термины вводи постепенно: сначала простым языком, потом официальное название в скобках.\n"
            "— Примеры из реальной жизни: спорт, музыка, соцсети, видеоигры.\n"
            "— Мотивируй: «Это пригодится тебе в 8 классе».\n"
            "— Если ученик ошибся — объясни почему, без осуждения.\n"
        )
    elif class_number <= 9:
        persona = (
            "ТЫ ГОВОРИШЬ С УЧЕНИКОМ 8–9 КЛАССА (14–16 лет), ГОТОВЯЩИМСЯ К ОГЭ. ПРАВИЛА:\n"
            "— Используй правильную терминологию, но объясняй сложные термины.\n"
            "— Всегда указывай связь с форматом ОГЭ: «В ОГЭ это задание №5».\n"
            "— Показывай типичные ошибки: «Многие здесь теряют баллы потому что...»\n"
            "— Структурированные ответы с нумерацией шагов.\n"
            "— Уважай как взрослого — не сюсюкай, но и не будь сухим.\n"
        )
    else:
        persona = (
            "ТЫ РАБОТАЕШЬ СО СТАРШЕКЛАССНИКОМ (16–18 лет), ЦЕЛЬ — ЕГЭ. ПРАВИЛА:\n"
            "— Общайся как равный с равным. Академический стиль, без упрощений.\n"
            "— Используй точные термины без лишних объяснений.\n"
            "— Указывай конкретные критерии ЕГЭ: «по критерию К2 снимут 1 балл если...»\n"
            "— Давай задания в точном формате ЕГЭ текущего года.\n"
            "— Если ученик делает системную ошибку — скажи прямо и дай план исправления.\n"
        )

    personal_parts = []
    avg_r     = user_stats.get('avg_rating', 0)
    streak    = user_stats.get('streak', 0)
    weak      = user_stats.get('weak_subjects', [])
    total_all = user_stats.get('total_all', 0)
    trend     = user_stats.get('rating_trend', 'stable')
    interests = user_stats.get('interests', '')

    if 0 < avg_r < 2.5:
        personal_parts.append(
            f"КРИТИЧЕСКИ ВАЖНО: ученик оценивает ответы очень низко по {subject} (средняя {avg_r}/5). "
            "Объясняй МАКСИМАЛЬНО просто, используй больше примеров и аналогий."
        )
    elif avg_r >= 4.5:
        personal_parts.append(
            f"Ученик хорошо понимает материал по {subject} (оценка {avg_r}/5). "
            "Можно усложнять задания, давать нетривиальные задачи."
        )

    if trend == 'falling':
        personal_parts.append(
            "ВНИМАНИЕ: последние оценки снижаются. Возможно, темп слишком высокий. "
            "Предложи вернуться к основам или объяснить иначе."
        )
    elif trend == 'rising':
        personal_parts.append("Последние оценки растут — ученик прогрессирует! Можно чуть повышать сложность.")

    if streak >= 14:
        personal_parts.append(f"Ученик занимается {streak} дней подряд — высокая мотивация!")
    elif streak == 0:
        personal_parts.append("Ученик только начинает или давно не занимался. Будь особенно поддерживающим.")

    if weak and subject in weak:
        personal_parts.append(
            f"ЭТОТ ПРЕДМЕТ ({subject}) является слабым для ученика. "
            "Объясняй особенно тщательно, дроби на маленькие шаги."
        )

    if total_all > 200:
        personal_parts.append(f"Очень опытный пользователь ({total_all} вопросов). Не объясняй очевидные вещи.")

    if interests:
        personal_parts.append(
            f"ИНТЕРЕСЫ УЧЕНИКА: {interests}. "
            "Используй эти темы для аналогий и примеров."
        )

    personal = ("\n— ".join(personal_parts))
    if personal:
        personal = "\nДОПОЛНИТЕЛЬНО:\n— " + personal + "\n"

    memory_ctx   = get_user_memory_context(user_id) if user_id else ""
    memory_block = "\n\n" + memory_ctx if memory_ctx else ""

    # Блок режима обучения
    mode_block = _build_mode_block(learning_path)

    return persona + ("\n\n" + personal if personal else "") + memory_block + mode_block


def build_system(mode: str, subject: str, class_number: int,
                 submode: str = "", math_level: str = "") -> str:
    """Строит системный промпт под режим чата (explain/step/quiz/exam)."""
    if class_number <= 4:
        level = "младшеклассника (7–10 лет), объясняй очень просто"
    elif class_number <= 7:
        level = "ученика 5–7 класса (11–14 лет), используй примеры из жизни"
    elif class_number <= 9:
        level = "ученика 8–9 класса (14–16 лет), готовящегося к ОГЭ"
    else:
        level = "ученика 10–11 класса (16–18 лет), готовящегося к ЕГЭ"

    exam_label = "ОГЭ" if class_number <= 9 else "ЕГЭ"
    math_suffix = ""
    if subject == "Математика":
        if math_level == "basic":
            math_suffix = " (базовая математика)"
        elif math_level == "profile":
            math_suffix = " (профильная математика)"

    base = (
        f"Ты — репетитор SubjectHelper для {level}. "
        f"Предмет: {subject}{math_suffix}. Класс: {class_number}. "
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
            "Только JSON, никакого другого текста."
        )
    elif mode == "exam":
        if submode == "explain_tasks":
            return (
                f"{base}\n\n"
                f"РЕЖИМ: РАЗБОР ЗАДАНИЙ {exam_label} ПО ПРЕДМЕТУ {subject}{math_suffix}.\n\n"
                "Когда пользователь называет НОМЕР задания — отвечай строго по структуре:\n\n"
                f"## 📌 Задание №[N] {exam_label} — [Тема задания]\n"
                "[Что проверяется: тема, навык, формат ответа — 2 предложения]\n\n"
                "## 📝 Типичное задание\n"
                f"[Реальное задание из {exam_label} в точном формате как на sdamgia.ru. "
                "Текст, условие, варианты если есть — всё как в КИМ]\n\n"
                "## ✅ Разбор решения\n"
                "[Пошаговое решение с объяснением каждого действия. Почему именно так]\n\n"
                "## ⚠️ Частые ошибки\n"
                "[2–3 типичных ошибки учеников именно на этом задании]\n\n"
                "## 💡 Лайфхак\n"
                "[Один конкретный совет — как решить быстрее или не потерять балл]\n\n"
                "## 🎯 Попробуй сам\n"
                "[Похожее задание для самостоятельного решения — с изменённым условием]\n\n"
                f"ВАЖНО: Знай точную структуру {exam_label} {subject} текущего года. "
                "Каждое задание соответствует реальному формату КИМ. "
                f"Если пользователь пишет «Задание 1» — разбирай первый тип задания из {exam_label}."
            )
        elif submode == "practice":
            return (
                f"{base}\n\n"
                f"РЕЖИМ: ТРЕНИРОВКА ОТДЕЛЬНЫХ ЗАДАНИЙ {exam_label}.\n"
                f"Давай задания в точном формате реального экзамена по {subject}{math_suffix}.\n"
                "Структура задания:\n"
                "**Задание [номер типа]** (Часть [1/2], [X] баллов)\n"
                "[Текст задания точно как в КИМ]\n\n"
                "После ответа ученика: оцени по критериям, укажи баллы, разбери ошибки."
            )
        elif submode == "full":
            return (
                f"{base}\n\n"
                f"РЕЖИМ: ПОЛНЫЙ ЭКЗАМЕН {exam_label} по {subject}{math_suffix}.\n"
                "Симулируй реальный экзамен: задания строго по порядку как в КИМ.\n"
                "Не давай подсказок до конца экзамена.\n"
                "На каждый ответ — только «Принято. Следующее задание:»\n"
                "В конце — полный разбор всех ответов с баллами."
            )
        else:
            return (
                f"{base}\n\n"
                f"РЕЖИМ: ПОДГОТОВКА К {exam_label} ПО {subject}{math_suffix}.\n"
                f"Помогай ученику понять формат {exam_label} по {subject}.\n"
                "Объясняй типы заданий, критерии оценивания, типичные ошибки.\n"
                "Давай советы по стратегии прохождения экзамена."
            )

    return base


def get_user_stats(user_id: int, subject: str) -> dict:
    history_all     = get_user_history(user_id)
    subject_history = [h for h in history_all if h.subject == subject]
    subject_rated   = [h.rating for h in subject_history if h.rating]
    avg_r           = round(sum(subject_rated) / len(subject_rated), 1) if subject_rated else 0

    trend = 'stable'
    if len(subject_rated) >= 10:
        recent_avg = sum(subject_rated[:5]) / 5
        older_avg  = sum(subject_rated[5:10]) / 5
        if recent_avg - older_avg >= 0.5:
            trend = 'rising'
        elif older_avg - recent_avg >= 0.5:
            trend = 'falling'

    quality = {}
    for h in history_all:
        if h.rating:
            quality.setdefault(h.subject, []).append(h.rating)

    weak_subjects = [
        s for s, ratings in quality.items()
        if (sum(ratings) / len(ratings)) < 3.0
    ]

    user = db.session.get(User, user_id)

    return {
        'avg_rating':      avg_r,
        'streak':          user.streak or 0 if user else 0,
        'weak_subjects':   weak_subjects,
        'total_questions': len(subject_history),
        'total_all':       len(history_all),
        'rating_trend':    trend,
        'interests':       (user.interests or '') if user else '',
        'learning_style':  (user.learning_style or '') if user else '',
    }


def update_streak(user):
    today = datetime.now().date()
    if user.last_study is None:
        user.streak     = 1
        user.last_study = today
    elif user.last_study == today:
        pass
    elif user.last_study == today - timedelta(days=1):
        user.streak    += 1
        user.last_study = today
    else:
        user.streak     = 1
        user.last_study = today


def maybe_run_memory_analyze(user_id: int):
    count = History.query.join(Chat).filter(Chat.user_id == user_id).count()
    if count > 0 and count % 10 == 0:
        try:
            _run_memory_analyze(user_id)
        except Exception as e:
            logger.error(f"Auto memory analyze error: {e}")


def _run_memory_analyze(user_id: int):
    user = db.session.get(User, user_id)

    recent_bad = History.query.join(Chat).filter(
        Chat.user_id == user_id,
        History.rating <= 2,
        History.rating != None,
    ).order_by(History.timestamp.desc()).limit(20).all()

    if not recent_bad:
        return

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

    raw   = ask_groq(prompt, system=system, max_tokens=600)
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        return
    try:
        parsed = _json.loads(match.group(0))
    except Exception:
        return

    for wt_data in parsed.get('weak_topics', []):
        if wt_data.get('subject') and wt_data.get('topic'):
            add_weak_topic(
                user_id=user_id,
                subject=wt_data['subject'],
                topic=wt_data['topic'],
                details=wt_data.get('details', ''),
            )

    for note_type, key in [('learning_style', 'learning_style_note'),
                            ('strength',       'strength_note')]:
        if parsed.get(key):
            existing = MemoryNote.query.filter_by(user_id=user_id, note_type=note_type).first()
            if existing:
                existing.content    = parsed[key]
                existing.updated_at = datetime.utcnow()
            else:
                db.session.add(MemoryNote(
                    user_id=user_id,
                    note_type=note_type,
                    content=parsed[key],
                ))
            if note_type == 'learning_style' and user:
                user.learning_style = parsed[key][:200]

    db.session.commit()
    logger.info(f"Memory analyze done for user={user_id}")


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
    # --- ГОСТЕВОЙ ХЕДЕР ---
    if 'user_id' not in session:
        return dict(menu='''
            <header class="lp-header" id="mainHeader">
              <a href="/" class="lp-logo">SubjectHelper<span class="lp-dragon">🐉</span></a>
              <nav class="lp-nav">
                <a href="/#modes">Режимы</a>
                <a href="/#subjects">Предметы</a>
                <a href="/#features">Возможности</a>
              </nav>
              <div class="lp-nav-cta">
                <a href="/login"><button class="btn-ghost">Войти</button></a>
                <a href="/register"><button class="btn-primary">Начать</button></a>
              </div>
              <div class="lp-mob-menu">
                <a href="/login"><button class="btn-ghost" style="padding:6px 14px;font-size:0.8rem;">Войти</button></a>
                <a href="/register"><button class="btn-primary" style="padding:6px 16px;font-size:0.8rem;">Начать</button></a>
              </div>
            </header>''', menu_js='')

    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return dict(menu='', menu_js='')

    current_ep = request.endpoint or ''

    def is_active(ep):
        return 'active' if (ep and (ep == current_ep or current_ep.startswith(ep))) else ''

    # --- ХЕДЕР + САЙДБАР ДЛЯ АВТОРИЗОВАННЫХ ---
    menu = f'''
    <header class="lp-header" id="mainHeader">
      <a href="/" class="lp-logo">SubjectHelper<span class="lp-dragon">🐉</span></a>
      <button class="sidebar-toggle" id="sidebarToggle" aria-label="Меню">☰</button>
    </header>

    <aside class="sidebar" id="mainSidebar">
      <nav class="sidebar-nav">
        <a href="{url_for('welcome')}" class="sidebar-link {is_active('welcome')}"><span class="sidebar-icon">🏡</span><span>Обучение</span></a>
        <a href="{url_for('chats_list')}" class="sidebar-link {is_active('chats_list') or is_active('chat')}"><span class="sidebar-icon">💬</span><span>Мои чаты</span></a>
        <a href="{url_for('history_page')}" class="sidebar-link {is_active('history_page')}"><span class="sidebar-icon">📜</span><span>История</span></a>
        <a href="{url_for('duel_page')}" class="sidebar-link {is_active('duel_page')}"><span class="sidebar-icon">⚡</span><span>Дуэли</span></a>
        <a href="{url_for('shop_page')}" class="sidebar-link {is_active('shop_page')}"><span class="sidebar-icon">🎁</span><span>Магазин</span></a>
        <a href="{url_for('leaderboard')}" class="sidebar-link {is_active('leaderboard')}"><span class="sidebar-icon">🏆</span><span>Лидерборд</span></a>
        <a href="{url_for('settings_page')}" class="sidebar-link {is_active('settings_page')}"><span class="sidebar-icon">⚙️</span><span>Настройки</span></a>
        <div class="sidebar-divider"></div>
        <a href="{url_for('logout')}" class="sidebar-link logout"><span class="sidebar-icon">🌙</span><span>Выйти</span></a>
      </nav>
    </aside>
    '''

    menu_js = '''<script>
    document.addEventListener("DOMContentLoaded", () => {
      const sb = document.getElementById("mainSidebar");
      const tog = document.getElementById("sidebarToggle");
      if (!sb || !tog) return;
      const overlay = document.createElement("div");
      overlay.className = "sidebar-overlay";
      document.body.appendChild(overlay);
      tog.onclick = () => { sb.classList.toggle("open"); overlay.classList.toggle("active"); };
      overlay.onclick = () => { sb.classList.remove("open"); overlay.classList.remove("active"); };
      document.addEventListener("keydown", e => { if (e.key === "Escape" && sb.classList.contains("open")) { sb.classList.remove("open"); overlay.classList.remove("active"); } });

      // Подсветка активного пункта
      const path = window.location.pathname;
      document.querySelectorAll(".sidebar-link").forEach(l => {
        const h = l.getAttribute("href");
        if (h && (path === h || path.startsWith(h + "/"))) l.classList.add("active");
      });
    });
    </script>'''
    return dict(menu=menu, menu_js=menu_js)

# ====================== ГЛАВНАЯ ======================
@app.route("/")
def welcome():
    """
    Главная страница.
    - Гость → landing.html (маркетинговый лендинг)
    - Залогиненный → welcome.html (дашборд с 3 режимами)
    """
    if 'user_id' not in session:
        # Гостевой лендинг — без данных пользователя
        return render_template("landing.html")

    # Залогиненный пользователь
    user = db.session.get(User, session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('welcome'))

    # Онбординг не пройден → отправляем на онбординг
    if hasattr(user, 'is_onboarded') and not user.is_onboarded:
        return redirect(url_for('onboarding'))

    # Последний чат (для карточки "Продолжить")
    last_chat = Chat.query.filter_by(
        user_id=user.id, has_messages=True
    ).order_by(Chat.updated_at.desc()).first()

    # Цель пользователя из онбординга
    user_goal = getattr(user, 'goal', None) or ''

    # Метки режимов (используются в buildQuickGrid на welcome.html)
    mode_labels = {
        'explain':       'Объяснение темы',
        'step':          'По шагам',
        'quiz':          'Квиз',
        'exam':          'ЕГЭ/ОГЭ',
        'explain_tasks': 'Разбор заданий',
        'practice':      'Тренировка',
        'full':          'Полный экзамен',
    }

    return render_template(
        "welcome.html",
        current_user=user,
        last_chat=last_chat,
        user_goal=user_goal,
        mode_labels=mode_labels,
    )


# ====================== ПРОФИЛЬ ======================
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
    total   = len(history)
    rated   = [h for h in history if h.rating]
    avg     = round(sum(h.rating for h in rated) / len(rated), 1) if rated else 0

    subjects = {}
    for h in history:
        subjects[h.subject] = subjects.get(h.subject, 0) + 1
    top         = max(subjects, key=subjects.get) if subjects else "—"
    max_queries = max(subjects.values()) if subjects else 1

    # XP за просмотр профиля убрано — начислялось при каждом обновлении страницы

    quality = {}
    for h in history:
        if h.rating:
            quality.setdefault(h.subject, []).append(h.rating)
    for s in quality:
        quality[s] = round(sum(quality[s]) / len(quality[s]), 1)
    weak_subject = min(quality, key=quality.get, default="—") if quality else "—"

    week_ago = datetime.now() - timedelta(days=7)
    recent   = [h for h in history if h.timestamp > week_ago]
    dates    = {}
    for h in recent:
        day       = h.timestamp.strftime('%d.%m')
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
    cid = session['current_chat_id']
    ch  = db.session.get(Chat, cid)
    if not ch or ch.user_id != session['user_id']:
        return redirect(url_for('chats_list'))
    path_for_chat = get_active_path(session['user_id'], ch.subject)
    initial_path_json = (
        _json.dumps(path_for_chat.to_dict(), ensure_ascii=False)
        if path_for_chat
        else 'null'
    )
    return render_template(
        "chat.html",
        chat=ch,
        subject_po=subject_po(ch.subject),
        initial_path_json=initial_path_json,
    )


@app.route("/chats")
@login_required
def chats_list():
    user_id = session['user_id']
    chats   = Chat.query.filter_by(user_id=user_id, has_messages=True).order_by(Chat.updated_at.desc()).all()
    return render_template("chats.html", chats=chats)


@app.route("/new_chat", methods=["POST"])
@login_required
def new_chat():
    subject      = request.form.get("subject", "Математика").strip()
    class_number = int(request.form.get("class_number", 8))
    mode         = request.form.get("mode", "explain").strip()
    submode      = request.form.get("submode", "").strip()    # explain_tasks|practice|full|''
    math_level   = request.form.get("math_level", "").strip() # basic|profile|''

    exam_label = "ОГЭ" if class_number <= 9 else "ЕГЭ"

    SUBMODE_LABELS = {
        "explain_tasks": "Разбор заданий",
        "practice":      "Тренировка",
        "full":          "Полный экзамен",
    }
    MODE_NAMES = {
        "explain": "Объяснение",
        "step":    "По шагам",
        "quiz":    "Квиз",
    }
    MATH_SUFFIX = {
        "basic":   " (база)",
        "profile": " (профиль)",
    }
    math_suffix = MATH_SUFFIX.get(math_level, "")

    # Строим заголовок чата
    if mode == "exam" and submode:
        title = f"{exam_label} · {subject}{math_suffix} · {SUBMODE_LABELS.get(submode, 'Подготовка')}"
    elif mode == "exam":
        title = f"{exam_label} · {subject}{math_suffix}"
    else:
        title = f"{subject}{math_suffix} — {MODE_NAMES.get(mode, mode)}"
    title = title[:200]

    chat = Chat(
        user_id      = session['user_id'],
        subject      = subject,
        class_number = class_number,
        mode         = mode,
        submode      = submode,
        math_level   = math_level,
        title        = title,
    )
    db.session.add(chat)
    db.session.commit()

    # Если есть активный путь (Sprint/Journey) — перезаписываем заголовок
    active = get_active_path(session['user_id'], subject)
    if active:
        if active.mode == 'sprint':
            g = (active.sprint_goal or 'цель').strip()
            chat.title = f"Sprint · {subject} · {g}"[:200]
        elif active.mode == 'journey':
            g = (active.journey_goal or 'цель').strip()
            chat.title = f"Journey · {subject} · {g}"[:200]
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
    path_for_chat = get_active_path(session['user_id'], chat.subject)
    initial_path_json = (
        _json.dumps(path_for_chat.to_dict(), ensure_ascii=False)
        if path_for_chat
        else 'null'
    )
    return render_template(
        "chat.html",
        chat=chat,
        messages=messages,
        subject_po=subject_po(chat.subject),
        initial_path_json=initial_path_json,
    )


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


# ════════════════════════════════════════════════════════
#  ОСНОВНОЙ ЗАПРОС К ИИ — /ask
# ════════════════════════════════════════════════════════
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
    # Берём submode из чата (фиксированный), но допускаем override из формы
    submode      = request.form.get("submode", "") or getattr(chat, 'submode', '') or ""
    math_level   = getattr(chat, 'math_level', '') or ""

    user = db.session.get(User, session['user_id'])

    # Обновляем стрик при реальной учёбе
    update_streak(user)

    # Начисляем XP за вопрос
    user.xp    = (user.xp or 0) + 10
    user.level = user.xp // 100 + 1
    db.session.commit()

    # Статистика по предмету
    user_stats = get_user_stats(session['user_id'], subject)

    # ── Определяем активный режим обучения ──────────────
    active_path = get_active_path(session['user_id'], subject)

    # Обновляем last_active + счётчик сессий Journey
    if active_path:
        active_path.last_active = datetime.utcnow()
        if active_path.mode == 'journey':
            question_count = History.query.join(Chat).filter(
                Chat.user_id == session['user_id']
            ).count()
            # Считаем сессию каждые 5 вопросов в Journey
            if question_count > 0 and question_count % 5 == 0:
                active_path.sessions_done += 1
                logger.info(f"Journey session #{active_path.sessions_done} for user={session['user_id']}")
        db.session.commit()

    # Строим промпт: кластер персонализации + режим + тип чата
    cluster     = build_cluster_profile(
        class_number, subject, user_stats,
        user_id=session['user_id'],
        learning_path=active_path,
    )
    mode_prompt = build_system(mode, subject, class_number, submode, math_level)
    system      = cluster + "\n\n" + mode_prompt

    # История чата из БД (последние 8 пар)
    raw_history  = History.query.filter_by(chat_id=chat_id).order_by(History.timestamp.asc()).all()
    chat_history = []
    for h in raw_history[-8:]:
        chat_history.append({"role": "user",      "content": h.question})
        chat_history.append({"role": "assistant",  "content": h.answer})

    answer = ask_groq(question, system=system, max_tokens=800, chat_history=chat_history)

    hid   = save_history(chat_id, subject, mode, question, answer)
    entry = db.session.get(History, hid)
    ts    = entry.timestamp.strftime("%H:%M") if entry else ""

    # Автоанализ памяти каждые 10 вопросов
    maybe_run_memory_analyze(session['user_id'])

    logger.info(
        f"ASK user={session['user_id']} mode={mode} submode={submode} "
        f"class={class_number} subject={subject} "
        f"learning_mode={'casual' if not active_path else active_path.mode}"
    )

    return jsonify({
        "answer":        answer,
        "question_id":   hid,
        "timestamp":     ts,
        "xp":            user.xp,
        "level":         user.level,
        "streak":        user.streak,
        "learning_path": active_path.to_dict() if active_path else None,
    })


# ════════════════════════════════════════════════════════
#  LEARNING PATHS API
# ════════════════════════════════════════════════════════

@app.route('/api/learning_path/active')
@login_required
def api_path_active():
    """Возвращает активный путь для предмета или null (Casual)."""
    subject = request.args.get('subject', '').strip()
    if not subject:
        return jsonify(None)
    path = get_active_path(session['user_id'], subject)
    return jsonify(path.to_dict() if path else None)


@app.route('/api/learning_path/list')
@login_required
def api_path_list():
    """Все активные пути пользователя (для дашборда)."""
    paths = LearningPath.query.filter_by(
        user_id=session['user_id'], is_active=True
    ).order_by(LearningPath.last_active.desc()).all()
    return jsonify([p.to_dict() for p in paths])


@app.route('/api/learning_path/create', methods=['POST'])
@login_required
def api_path_create():
    """
    Создать Sprint или Journey.

    Sprint body:
    {
      "subject": "Физика",
      "mode": "sprint",
      "goal": "ОГЭ через 3 дня",
      "topics": ["Кинематика", "Динамика"],
      "deadline": "2025-08-10"
    }

    Journey body:
    {
      "subject": "Английский язык",
      "mode": "journey",
      "goal": "читать без субтитров",
      "level": "beginner",
      "minutes_per_week": 120,
      "probe_strong": ["базовая лексика"],
      "probe_weak": ["отрицательные предложения"]
    }
    """
    data    = request.get_json() or {}
    user_id = session['user_id']
    subject = data.get('subject', '').strip()
    mode    = data.get('mode', '')

    if not subject or mode not in ('sprint', 'journey'):
        return jsonify({'error': 'Укажи subject и mode (sprint|journey)'}), 400

    # Деактивируем предыдущий активный путь для этого предмета
    LearningPath.query.filter_by(
        user_id=user_id, subject=subject, is_active=True
    ).update({'is_active': False})

    path = LearningPath(user_id=user_id, subject=subject, mode=mode)

    if mode == 'sprint':
        path.sprint_goal   = (data.get('goal') or '')[:300]
        raw_conf           = (data.get('topic_confidence') or data.get('sprint_confidence') or '').strip()
        if raw_conf in ('weak', 'medium', 'strong'):
            path.sprint_confidence = raw_conf
        else:
            path.sprint_confidence = None
        deadline_str = data.get('deadline')
        if deadline_str:
            try:
                path.sprint_deadline = date.fromisoformat(deadline_str)
            except ValueError:
                logger.warning(f"Invalid deadline format: {deadline_str}")

        merged_topics = _generate_sprint_topics(
            subject=subject,
            goal=path.sprint_goal,
            deadline=path.sprint_deadline,
            confidence=path.sprint_confidence,
            user_topics=data.get('topics') or [],
        )
        path.sprint_topics = _json.dumps(merged_topics, ensure_ascii=False)

    elif mode == 'journey':
        path.journey_goal     = (data.get('goal') or '')[:300]
        path.journey_level    = data.get('level') or 'beginner'
        path.minutes_per_week = int(data.get('minutes_per_week') or 120)
        path.probe_strong     = _json.dumps(data.get('probe_strong') or [], ensure_ascii=False)
        path.probe_weak       = _json.dumps(data.get('probe_weak') or [],   ensure_ascii=False)

        # Генерируем roadmap через Groq
        roadmap = _generate_journey_roadmap(
            subject=subject,
            goal=path.journey_goal,
            level=path.journey_level,
            weak=data.get('probe_weak') or [],
            strong=data.get('probe_strong') or [],
            minutes_per_week=path.minutes_per_week,
        )
        path.journey_roadmap = _json.dumps(roadmap, ensure_ascii=False)

    db.session.add(path)
    db.session.commit()

    logger.info(f"LearningPath created: user={user_id} mode={mode} subject={subject}")
    return jsonify({'ok': True, 'path': path.to_dict()})


@app.route('/api/learning_path/complete_topic', methods=['POST'])
@login_required
def api_path_complete_topic():
    """Отметить тему Sprint завершённой."""
    data    = request.get_json() or {}
    path_id = data.get('path_id')
    topic   = (data.get('topic') or '').strip()

    path = db.session.get(LearningPath, path_id)
    if not path or path.user_id != session['user_id']:
        return jsonify({'error': 'Путь не найден'}), 404
    if path.mode != 'sprint':
        return jsonify({'error': 'Только для Sprint'}), 400

    done = path.get_sprint_done()
    if topic and topic not in done:
        done.append(topic)
        path.sprint_topics_done = _json.dumps(done, ensure_ascii=False)
        db.session.commit()

    # Проверяем завершён ли весь Sprint
    all_topics = path.get_sprint_topics()
    is_complete = len(done) >= len(all_topics) if all_topics else False

    return jsonify({
        'ok':          True,
        'done':        done,
        'progress_pct':path.sprint_progress_pct(),
        'is_complete': is_complete,
    })


@app.route('/api/learning_path/advance_unit', methods=['POST'])
@login_required
def api_path_advance_unit():
    """Перейти на следующий юнит Journey."""
    data    = request.get_json() or {}
    path_id = data.get('path_id')

    path = db.session.get(LearningPath, path_id)
    if not path or path.user_id != session['user_id']:
        return jsonify({'error': 'Путь не найден'}), 404
    if path.mode != 'journey':
        return jsonify({'error': 'Только для Journey'}), 400

    roadmap   = path.get_roadmap()
    max_unit  = len(roadmap)

    if path.current_unit < max_unit:
        path.current_unit += 1
        db.session.commit()

    return jsonify({
        'ok':           True,
        'current_unit': path.current_unit,
        'unit_data':    path.get_current_unit_data(),
        'progress_pct': path.journey_progress_pct(),
    })


@app.route('/api/learning_path/deactivate', methods=['POST'])
@login_required
def api_path_deactivate():
    """Завершить или отменить активный путь."""
    data    = request.get_json() or {}
    path_id = data.get('path_id')

    path = db.session.get(LearningPath, path_id)
    if not path or path.user_id != session['user_id']:
        return jsonify({'error': 'Путь не найден'}), 404

    path.is_active = False
    if path.mode == 'sprint':
        path.sprint_done = True
    db.session.commit()

    logger.info(f"LearningPath deactivated: id={path_id} user={session['user_id']}")
    return jsonify({'ok': True})


@app.route('/api/learning_path/generate_probe', methods=['POST'])
@login_required
def api_path_generate_probe():
    """
    Генерирует мини-пробник (8 вопросов) для Journey.
    Возвращает JSON-квиз для отображения на фронте.
    """
    data    = request.get_json() or {}
    subject = (data.get('subject') or '').strip()
    goal    = (data.get('goal') or '').strip()
    level   = data.get('level') or 'beginner'

    if not subject:
        return jsonify({'error': 'Укажи subject'}), 400

    system = (
        "Ты — методист. Составляй диагностические вопросы по предмету. "
        "Отвечай ТОЛЬКО валидным JSON без markdown."
    )
    prompt = f"""Составь мини-пробник для определения уровня знаний по предмету «{subject}».
Цель ученика: {goal or 'изучить предмет'}
Предполагаемый уровень: {level}

Верни JSON-массив из 8 вопросов:
[
  {{
    "question": "текст вопроса",
    "options": ["A", "B", "C", "D"],
    "correct_index": 0,
    "topic": "Название темы к которой относится вопрос"
  }}
]

Вопросы должны охватывать разные темы предмета от базовых до более сложных.
Только JSON-массив, без объяснений."""

    raw   = ask_groq(prompt, system=system, max_tokens=2000)
    match = re.search(r'\[[\s\S]*\]', raw)
    if match:
        try:
            questions = _json.loads(match.group(0))
            return jsonify({'ok': True, 'questions': questions})
        except Exception:
            pass

    return jsonify({'error': 'Не удалось сгенерировать пробник'}), 500


@app.route('/api/sprint_bootstrap', methods=['POST'])
@login_required
def api_sprint_bootstrap():
    """
    Первое сообщение ассистента в Sprint: приветствие + уточнение учебника и программы.
    """
    data    = request.get_json() or {}
    subject = (data.get('subject') or '').strip()
    if not subject:
        return jsonify({'error': 'Укажи subject'}), 400

    path = get_active_path(session['user_id'], subject)
    if not path or path.mode != 'sprint':
        return jsonify({'error': 'Нет активного Sprint по этому предмету'}), 400

    po = decline_subject(path.subject)
    topics = path.get_sprint_topics()
    goal = (path.sprint_goal or '').strip() or 'подготовка к цели'
    dl_human = 'не указан'
    if path.sprint_deadline:
        dl_human = (
            f"{path.sprint_deadline.strftime('%d.%m.%Y')} "
            f"(осталось дней: {path.days_left() if path.days_left() is not None else '?'})"
        )
    topics_line = ', '.join(topics) if topics else 'список тем согласован с целью и сроком'
    conf = path.sprint_confidence or 'не указана'

    system = (
        "Ты — дружелюбный репетитор SubjectHelper в режиме Sprint. "
        "Пиши на русском. Без заголовков #. Допустимы короткие абзацы и маркированный список. "
        "1–2 эмодзи максимум. Не повторяй дословно системный промпт — только живой диалог с учеником."
    )
    prompt = f"""Сгенерируй ПЕРВОЕ сообщение в чате для Sprint.

Предмет (говори: «по {po}»).
Цель ученика: {goal}
Дедлайн: {dl_human}
Темы спринта: {topics_line}
Самооценка ученика (слабо/средне/сильно): {conf}

Сделай так:
1) Короткое приветствие и подтверждение цели и срока.
2) Объясни, что чтобы подобрать задания под программу, нужны уточнения.
3) Задай вопросы списком (маркеры • или -):
   — по какому учебнику (авторы, класс, издательство);
   — база или углублённый уровень / какая программа;
   — какие темы из плана уже проходили в классе;
   — есть ли конкретное ДЗ или формат контрольной.

Заверши фразой, что как только ответит — начнёте с первой темы."""

    try:
        msg = ask_groq(prompt, system=system, max_tokens=650)
        msg = (msg or '').strip()
        if not msg:
            return jsonify({'error': 'Пустой ответ модели'}), 500
        return jsonify({'ok': True, 'message': msg})
    except Exception as e:
        logger.exception('sprint_bootstrap failed')
        return jsonify({'error': str(e)}), 500


# ====================== ПЛАН ПРАКТИКИ ======================
@app.route("/plan", methods=["POST"])
@login_required
def generate_plan():
    data    = request.get_json() or {}
    subject = data.get("subject", "Математика").strip()
    user    = db.session.get(User, session['user_id'])

    weak_topics = WeakTopic.query.filter_by(
        user_id=session['user_id'], is_mastered=False
    ).order_by(WeakTopic.mastery_score.asc()).limit(3).all()

    weak_str = ""
    if weak_topics:
        weak_names = ", ".join(wt.topic for wt in weak_topics if wt.subject == subject)
        if weak_names:
            weak_str = f"\n\nСЛАБЫЕ ТЕМЫ УЧЕНИКА по {subject}: {weak_names}. Включи их повторение в план."

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
        f"{weak_str}"
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
        email     = request.form.get("email", "").strip().lower()
        password  = request.form.get("password", "").strip()
        interests = request.form.get("interests", "").strip()
        class_num = request.form.get("class_number", "8").strip()

        if not email or not password:
            flash("Заполните поля", "danger")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("Email занят", "warning")
            return redirect(url_for("register"))

        user              = User(email=email)
        user.set_password(password)
        user.last_study   = None
        user.streak       = 0
        user.xp           = 0
        user.level        = 1
        user.badges       = ''
        user.interests    = interests[:200] if interests else ''
        user.class_number = int(class_num) if class_num.isdigit() else 8
        user.learning_style = ''

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
            # Если не прошёл онбординг — отправляем туда
            if not getattr(user, 'is_onboarded', True):
                return redirect(url_for("onboarding"))
            return redirect(url_for("welcome"))
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
        if r <= 2:
            try:
                _run_memory_analyze(session['user_id'])
            except Exception as ex:
                logger.error(f"Rate memory analyze error: {ex}")
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


# ====================== TTS ПРОКСИ ======================
@app.route('/api/tts', methods=['POST'])
@login_required
def tts_proxy():
    key = os.environ.get('VOICERSS_API_KEY', '')
    if not key:
        return jsonify({'error': 'VOICERSS_API_KEY не настроен в .env'}), 404

    text = request.json.get('text', '').strip()
    if not text:
        return jsonify({'error': 'Пустой текст'}), 400

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
            data         = resp.read()
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
#  ДОЛГОСРОЧНАЯ ПАМЯТЬ
# ════════════════════════════════════════════════════════

@app.route('/memory')
@login_required
def memory_page():
    user_id = session['user_id']
    user    = db.session.get(User, user_id)

    weak     = WeakTopic.query.filter_by(user_id=user_id, is_mastered=False) \
                              .order_by(WeakTopic.mastery_score.asc()).all()
    mastered = WeakTopic.query.filter_by(user_id=user_id, is_mastered=True) \
                              .order_by(WeakTopic.last_seen.desc()).limit(20).all()
    due      = get_topics_due(user_id)
    notes    = MemoryNote.query.filter_by(user_id=user_id) \
                               .order_by(MemoryNote.updated_at.desc()).limit(10).all()

    return render_template('memory.html',
                           current_user=user,
                           weak_topics=weak,
                           mastered_topics=mastered,
                           due_topics=due,
                           memory_notes=notes)


@app.route('/api/memory/due')
@login_required
def api_memory_due():
    due = get_topics_due(session['user_id'], limit=5)
    return jsonify([t.to_dict() for t in due])


@app.route('/api/memory/topics')
@login_required
def api_memory_topics():
    topics = WeakTopic.query.filter_by(
        user_id=session['user_id']
    ).order_by(WeakTopic.mastery_score.asc()).all()
    return jsonify([t.to_dict() for t in topics])


@app.route('/api/memory/review_start', methods=['POST'])
@login_required
def api_review_start():
    data     = request.get_json() or {}
    topic_id = data.get('topic_id')

    wt = db.session.get(WeakTopic, topic_id)
    if not wt or wt.user_id != session['user_id']:
        return jsonify({'error': 'Тема не найдена'}), 404

    user      = db.session.get(User, session['user_id'])
    class_num = user.class_number or 8
    interests = user.interests    or ''
    days_ago  = (datetime.utcnow() - wt.first_seen).days

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

Тон: как добрый старший друг, не как учитель."""

    prompt = f"Проведи мини-повторение по теме «{wt.topic}» (предмет: {wt.subject})."
    answer = ask_groq(prompt, system=system, max_tokens=600)

    review = ReviewSession(user_id=session['user_id'], weak_topic_id=wt.id)
    db.session.add(review)
    db.session.commit()

    return jsonify({
        'review_id':   review.id,
        'topic':       wt.topic,
        'subject':     wt.subject,
        'error_count': wt.error_count,
        'mastery':     int(wt.mastery_score * 100),
        'content':     answer,
    })


@app.route('/api/memory/review_complete', methods=['POST'])
@login_required
def api_review_complete():
    data      = request.get_json() or {}
    review_id = data.get('review_id')
    score     = data.get('score', 3)

    review = db.session.get(ReviewSession, review_id)
    if not review or review.user_id != session['user_id']:
        return jsonify({'error': 'Не найдено'}), 404

    review.completed = True
    review.score     = score

    quality = round((score - 1) * 5 / 4)
    wt      = db.session.get(WeakTopic, review.weak_topic_id)
    if wt:
        sm2_update(wt, quality)
        user       = db.session.get(User, session['user_id'])
        user.xp    = (user.xp or 0) + (5 * score)
        user.level = user.xp // 100 + 1
        db.session.commit()

    return jsonify({
        'ok':          True,
        'mastery':     int(wt.mastery_score * 100) if wt else 0,
        'is_mastered': wt.is_mastered if wt else False,
        'next_review': wt.next_review.isoformat() if wt else None,
        'xp_gained':   5 * score,
    })


@app.route('/api/memory/add_error', methods=['POST'])
@login_required
def api_add_error():
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
    try:
        _run_memory_analyze(session['user_id'])
        return jsonify({'ok': True})
    except Exception as e:
        logger.error(f"Memory analyze error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/memory/daily_reminder')
@login_required
def api_daily_reminder():
    user_id = session['user_id']
    due     = get_topics_due(user_id, limit=3)

    if not due:
        return jsonify({'has_reminder': False})

    top  = due[0]
    days = (datetime.utcnow() - top.first_seen).days

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
    if not user:
        return jsonify({'ok': False}), 404

    if 'theme' in data:
        user.theme = data['theme']
    if 'interests' in data and data['interests']:
        user.interests = str(data['interests'])[:200]
    if 'class_number' in data and data['class_number']:
        try:
            user.class_number = int(data['class_number'])
        except (ValueError, TypeError):
            pass
    if 'tts_enabled' in data:
        user.tts_enabled = bool(data['tts_enabled'])
    if 'anim_enabled' in data:
        user.anim_enabled = bool(data['anim_enabled'])
    if 'enter_send' in data:
        user.enter_send = bool(data['enter_send'])
    if 'daily_goal' in data:
        try:
            user.daily_goal = int(data['daily_goal'])
        except (ValueError, TypeError):
            pass

    db.session.commit()
    logger.info(f"Settings saved for user={user.id}: {list(data.keys())}")
    return jsonify({'ok': True})


@app.route('/api/settings', methods=['POST'])
@login_required
def api_save_settings():
    data = request.get_json() or {}
    user = User.query.get(session['user_id'])
    if not user.settings:
        user.settings = {}

    user.settings.update(data)  # обновляем только то, что пришло
    db.session.commit()

    return jsonify({'ok': True, 'settings': user.settings})

@app.route('/api/settings/load')
@login_required
def settings_load():
    user = db.session.get(User, session['user_id'])
    if not user:
        return jsonify({}), 404
    return jsonify({
        'theme':        getattr(user, 'theme', 'dark') or 'dark',
        'interests':    user.interests or '',
        'class_number': user.class_number or 8,
        'tts_enabled':  getattr(user, 'tts_enabled', True),
        'anim_enabled': getattr(user, 'anim_enabled', True),
        'enter_send':   getattr(user, 'enter_send', True),
        'daily_goal':   getattr(user, 'daily_goal', 5) or 5,
        'streak':       user.streak or 0,
        'xp':           user.xp or 0,
        'level':        user.level or 1,
    })


# ====================== ОНБОРДИНГ ======================
@app.route('/onboarding')
@login_required
def onboarding():
    user = db.session.get(User, session['user_id'])
    if user and getattr(user, 'is_onboarded', False):
        return redirect(url_for('welcome'))
    return render_template('onboarding.html', current_user=user)


@app.route('/api/onboarding/save', methods=['POST'])
@login_required
def onboarding_save():
    data = request.get_json() or {}
    user = db.session.get(User, session['user_id'])
    if not user:
        return jsonify({'error': 'not found'}), 404

    if data.get('name'):
        user.name = data['name'][:30]
        session['nickname'] = user.name
    if data.get('class_number'):
        user.class_number = max(1, min(11, int(data['class_number'])))
    if data.get('interests'):
        user.interests = ','.join(data['interests'])[:200]
    if data.get('learning_style') and hasattr(user, 'learning_style'):
        user.learning_style = data['learning_style'][:30]
    if data.get('goal') and hasattr(user, 'goal'):
        user.goal = data['goal'][:30]
    if data.get('hard_subjects') and hasattr(user, 'hard_subjects'):
        user.hard_subjects = ','.join(data['hard_subjects'])[:200]
    if data.get('referral') and hasattr(user, 'referral'):
        user.referral = data['referral'][:30]
    if hasattr(user, 'is_onboarded'):
        user.is_onboarded = True

    user.xp    = (user.xp or 0) + 50
    user.level = user.xp // 100 + 1
    db.session.commit()
    return jsonify({'ok': True})


# ====================== ЗАПУСК ======================
if __name__ == "__main__":
    os.makedirs("static/uploads", exist_ok=True)
    os.makedirs("static/avatars", exist_ok=True)
    from duel_server import socketio as _sio
    _sio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)