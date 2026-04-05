"""
oauth_routes.py — Социальная авторизация для SubjectHelper
Подключить в main.py:  from oauth_routes import init_oauth, oauth_bp
                       init_oauth(app)
                       app.register_blueprint(oauth_bp)
"""

import os
import secrets
from datetime import datetime, timedelta

from authlib.integrations.flask_client import OAuth
from flask import (Blueprint, flash, redirect, render_template,
                   request, session, url_for)

from models import SocialAccount, User, db

# ─────────────────────────────────────────────────────────
#  Blueprint и OAuth-клиент
# ─────────────────────────────────────────────────────────
oauth_bp = OAuth_instance = None


def init_oauth(app):
    """Вызвать после create_app(), до регистрации blueprint."""
    global OAuth_instance

    oauth = OAuth(app)

    # ── GOOGLE ──────────────────────────────────────────
    oauth.register(
        name='google',
        client_id=app.config['GOOGLE_CLIENT_ID'],
        client_secret=app.config['GOOGLE_CLIENT_SECRET'],
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile',
            'prompt': 'select_account',   # всегда показывать выбор аккаунта
        },
    )

    # ── ЯНДЕКС ──────────────────────────────────────────
    oauth.register(
        name='yandex',
        client_id=app.config['YANDEX_CLIENT_ID'],
        client_secret=app.config['YANDEX_CLIENT_SECRET'],
        authorize_url='https://oauth.yandex.ru/authorize',
        access_token_url='https://oauth.yandex.ru/token',
        userinfo_endpoint='https://login.yandex.ru/info?format=json',
        client_kwargs={'scope': 'login:email login:avatar login:info'},
    )

    # ── VK ──────────────────────────────────────────────
    # VK использует OAuth 2.0 с нестандартным userinfo
    oauth.register(
        name='vk',
        client_id=app.config['VK_CLIENT_ID'],
        client_secret=app.config['VK_CLIENT_SECRET'],
        authorize_url='https://oauth.vk.com/authorize',
        access_token_url='https://oauth.vk.com/access_token',
        client_kwargs={
            'scope': 'email',
            'response_type': 'code',
        },
    )

    # ── MAIL.RU ─────────────────────────────────────────
    oauth.register(
        name='mailru',
        client_id=app.config.get('MAILRU_CLIENT_ID', ''),
        client_secret=app.config.get('MAILRU_CLIENT_SECRET', ''),
        authorize_url='https://oauth.mail.ru/login',
        access_token_url='https://oauth.mail.ru/token',
        userinfo_endpoint='https://oauth.mail.ru/userinfo',
        client_kwargs={'scope': 'userinfo'},
    )

    OAuth_instance = oauth
    return oauth


# ─────────────────────────────────────────────────────────
#  Blueprint
# ─────────────────────────────────────────────────────────
oauth_bp = Blueprint('oauth', __name__, url_prefix='/auth')


# ─────────────────────────────────────────────────────────
#  Хелперы
# ─────────────────────────────────────────────────────────

def _login_user(user: User):
    """Устанавливает сессию после успешной OAuth-авторизации."""
    session['user_id']  = user.id
    session['nickname'] = user.name or 'Пользователь'
    session.permanent   = True          # сессия живёт 31 день (настроить в app.config)


def _find_or_create_user(
    provider: str,
    provider_user_id: str,
    email: str | None,
    name: str | None,
    avatar: str | None,
    access_token: str | None = None,
    refresh_token: str | None = None,
    token_expires: datetime | None = None,
) -> tuple[User, bool]:
    """
    Ищет или создаёт пользователя по следующей логике:
    1. Ищем SocialAccount → нашли → возвращаем связанного User
    2. Ищем User по email → нашли → привязываем соцсеть (merge)
    3. Создаём нового User + SocialAccount

    Returns: (user, is_new_user)
    """
    # ── Шаг 1: Есть ли уже привязанный аккаунт? ──
    social = SocialAccount.query.filter_by(
        provider=provider, provider_user_id=str(provider_user_id)
    ).first()

    if social:
        # Обновляем данные профиля и токены
        social.provider_email  = email
        social.provider_name   = name
        social.provider_avatar = avatar
        social.access_token    = access_token
        social.refresh_token   = refresh_token
        social.token_expires   = token_expires
        social.updated_at      = datetime.utcnow()
        db.session.commit()
        return social.user, False

    # ── Шаг 2: Слияние по email ──
    user = None
    if email:
        user = User.query.filter_by(email=email.lower()).first()

    is_new = user is None

    if is_new:
        # ── Шаг 3: Создаём нового User ──
        user = User(
            email         = email.lower() if email else None,
            password_hash = None,   # OAuth-пользователь без пароля
            name          = _truncate_name(name),
            avatar        = avatar,
            streak        = 0,
            xp            = 0,
            level         = 1,
            badges        = '',
            class_number  = 8,       # дефолт, уточнится в онбординге
            is_onboarded  = False,
        )
        db.session.add(user)
        db.session.flush()  # получаем user.id до commit

    else:
        # Merge: обновляем аватар и имя только если у юзера их нет
        if not user.avatar and avatar:
            user.avatar = avatar
        if not user.name and name:
            user.name = _truncate_name(name)

    # Привязываем соцсеть
    social = SocialAccount(
        user_id          = user.id,
        provider         = provider,
        provider_user_id = str(provider_user_id),
        provider_email   = email,
        provider_name    = name,
        provider_avatar  = avatar,
        access_token     = access_token,
        refresh_token    = refresh_token,
        token_expires    = token_expires,
    )
    db.session.add(social)
    db.session.commit()

    return user, is_new


def _truncate_name(name: str | None) -> str | None:
    """Обрезает имя до 20 символов (поле User.name)."""
    if not name:
        return None
    # Берём только первое слово (имя без фамилии) если длинно
    parts = name.strip().split()
    result = parts[0] if parts else name
    return result[:20]


def _get_token_expires(token_data: dict) -> datetime | None:
    """Вычисляет время истечения токена из expires_in."""
    expires_in = token_data.get('expires_in')
    if expires_in:
        return datetime.utcnow() + timedelta(seconds=int(expires_in))
    return None


# ─────────────────────────────────────────────────────────
#  GOOGLE
# ─────────────────────────────────────────────────────────

@oauth_bp.route('/google')
def google_login():
    redirect_uri = url_for('oauth.google_callback', _external=True)
    # state генерируется Authlib автоматически и проверяется в callback
    return OAuth_instance.google.authorize_redirect(redirect_uri)


@oauth_bp.route('/google/callback')
def google_callback():
    try:
        token = OAuth_instance.google.authorize_access_token()
    except Exception as e:
        flash(f'Ошибка авторизации Google: {e}', 'danger')
        return redirect(url_for('login'))

    userinfo = token.get('userinfo') or OAuth_instance.google.userinfo()

    user, is_new = _find_or_create_user(
        provider         = 'google',
        provider_user_id = userinfo['sub'],
        email            = userinfo.get('email'),
        name             = userinfo.get('given_name') or userinfo.get('name'),
        avatar           = userinfo.get('picture'),
        access_token     = token.get('access_token'),
        refresh_token    = token.get('refresh_token'),
        token_expires    = _get_token_expires(token),
    )

    _login_user(user)

    if is_new or not user.is_onboarded:
        flash('Добро пожаловать в SubjectHelper! 🐉', 'success')
        return redirect(url_for('onboarding'))

    flash(f'Привет, {user.name or "друг"}!', 'success')
    return redirect(url_for('welcome'))


# ─────────────────────────────────────────────────────────
#  ЯНДЕКС
# ─────────────────────────────────────────────────────────

@oauth_bp.route('/yandex')
def yandex_login():
    redirect_uri = url_for('oauth.yandex_callback', _external=True)
    return OAuth_instance.yandex.authorize_redirect(redirect_uri)


@oauth_bp.route('/yandex/callback')
def yandex_callback():
    try:
        token = OAuth_instance.yandex.authorize_access_token()
    except Exception as e:
        flash(f'Ошибка авторизации Яндекс: {e}', 'danger')
        return redirect(url_for('login'))

    # Яндекс возвращает userinfo через отдельный запрос
    resp = OAuth_instance.yandex.get(
        'https://login.yandex.ru/info?format=json',
        token=token
    )
    info = resp.json()

    # Аватар Яндекса
    avatar = None
    if info.get('default_avatar_id'):
        avatar = f"https://avatars.yandex.net/get-yapic/{info['default_avatar_id']}/islands-200"

    email = info.get('default_email') or (info.get('emails') or [None])[0]
    name  = info.get('first_name') or info.get('real_name') or info.get('login')

    user, is_new = _find_or_create_user(
        provider         = 'yandex',
        provider_user_id = str(info['id']),
        email            = email,
        name             = name,
        avatar           = avatar,
        access_token     = token.get('access_token'),
        refresh_token    = token.get('refresh_token'),
        token_expires    = _get_token_expires(token),
    )

    _login_user(user)

    if is_new or not user.is_onboarded:
        flash('Добро пожаловать в SubjectHelper! 🐉', 'success')
        return redirect(url_for('onboarding'))

    flash(f'Привет, {user.name or "друг"}!', 'success')
    return redirect(url_for('welcome'))


# ─────────────────────────────────────────────────────────
#  VK
# ─────────────────────────────────────────────────────────

@oauth_bp.route('/vk')
def vk_login():
    redirect_uri = url_for('oauth.vk_callback', _external=True)
    # VK не поддерживает PKCE — используем state вручную
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state
    return OAuth_instance.vk.authorize_redirect(
        redirect_uri,
        state=state,
        display='page',
        v='5.199',
    )


@oauth_bp.route('/vk/callback')
def vk_callback():
    # Проверяем state вручную (VK иногда не передаёт его корректно)
    returned_state = request.args.get('state', '')
    expected_state = session.pop('oauth_state', '')
    if returned_state != expected_state:
        flash('Ошибка безопасности (state mismatch). Попробуй снова.', 'danger')
        return redirect(url_for('login'))

    try:
        redirect_uri = url_for('oauth.vk_callback', _external=True)
        token = OAuth_instance.vk.authorize_access_token(redirect_uri=redirect_uri)
    except Exception as e:
        flash(f'Ошибка авторизации VK: {e}', 'danger')
        return redirect(url_for('login'))

    # VK возвращает email прямо в токене (не в userinfo)
    email   = token.get('email')
    user_id = str(token.get('user_id', ''))

    # Получаем профиль через API VK
    name = avatar = None
    try:
        api_resp = OAuth_instance.vk.get(
            'https://api.vk.com/method/users.get',
            token=token,
            params={
                'user_ids': user_id,
                'fields': 'photo_200,first_name',
                'v': '5.199',
            }
        )
        vk_data = api_resp.json().get('response', [{}])[0]
        name    = vk_data.get('first_name')
        avatar  = vk_data.get('photo_200')
    except Exception:
        pass  # Профиль необязателен — продолжаем без него

    user, is_new = _find_or_create_user(
        provider         = 'vk',
        provider_user_id = user_id,
        email            = email,
        name             = name,
        avatar           = avatar,
        access_token     = token.get('access_token'),
        token_expires    = _get_token_expires(token),
    )

    _login_user(user)

    if is_new or not user.is_onboarded:
        flash('Добро пожаловать в SubjectHelper! 🐉', 'success')
        return redirect(url_for('onboarding'))

    flash(f'Привет, {user.name or "друг"}!', 'success')
    return redirect(url_for('welcome'))


# ─────────────────────────────────────────────────────────
#  MAIL.RU
# ─────────────────────────────────────────────────────────

@oauth_bp.route('/mailru')
def mailru_login():
    redirect_uri = url_for('oauth.mailru_callback', _external=True)
    return OAuth_instance.mailru.authorize_redirect(redirect_uri)


@oauth_bp.route('/mailru/callback')
def mailru_callback():
    try:
        token = OAuth_instance.mailru.authorize_access_token()
    except Exception as e:
        flash(f'Ошибка авторизации Mail.ru: {e}', 'danger')
        return redirect(url_for('login'))

    resp = OAuth_instance.mailru.get('https://oauth.mail.ru/userinfo', token=token)
    info = resp.json()

    user, is_new = _find_or_create_user(
        provider         = 'mailru',
        provider_user_id = str(info.get('id', '')),
        email            = info.get('email'),
        name             = info.get('first_name'),
        avatar           = info.get('image'),
        access_token     = token.get('access_token'),
        token_expires    = _get_token_expires(token),
    )

    _login_user(user)

    if is_new or not user.is_onboarded:
        flash('Добро пожаловать в SubjectHelper! 🐉', 'success')
        return redirect(url_for('onboarding'))

    flash(f'Привет, {user.name or "друг"}!', 'success')
    return redirect(url_for('welcome'))