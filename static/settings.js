/**
 * settings.js — Централизованные настройки SubjectHelper
 * Подключи на КАЖДОЙ странице после themes.js:
 *   <script src="{{ url_for('static', filename='settings.js') }}"></script>
 *
 * Читает localStorage и применяет настройки сразу при загрузке страницы.
 * Экспортирует: window.SH.get(key), window.SH.set(key, val)
 */
(function () {
  'use strict';

  // ── Дефолты ──
  const DEFAULTS = {
    fairik:  true,   // показывать Файрика
    bg:      true,   // анимированный фон
    xp:      true,   // XP-уведомления
    tts:     true,   // кнопка озвучки
    enter:   true,   // Enter отправляет
    anim:    true,   // анимация текста
    remind:  true,   // напоминания Файрика
  };

  // ── Получить значение ──
  function get(key) {
    const saved = localStorage.getItem(`sh_${key}`);
    if (saved === null) return DEFAULTS[key] ?? true;
    return saved === 'true';
  }

  // ── Сохранить значение и применить ──
  function set(key, val) {
    localStorage.setItem(`sh_${key}`, String(val));
    applyOne(key, val);
    // Обновляем чекбокс если он есть на странице
    const el = document.getElementById(`tog-${key}`);
    if (el) el.checked = val;
  }

  // ── Применить одну настройку ──
  function applyOne(key, val) {
    switch (key) {

      case 'fairik':
        // Файрик — скрыть/показать виджет
        ['fairik-widget', 'fk-mini'].forEach(id => {
          const el = document.getElementById(id);
          if (el) el.style.setProperty('display', val ? '' : 'none', 'important');
        });
        break;

      case 'bg':
        // Анимированный фон — canvas формул
        ['formula-canvas'].forEach(id => {
          const el = document.getElementById(id);
          if (el) el.style.setProperty('display', val ? '' : 'none', 'important');
        });
        break;

      case 'xp':
        // XP-тост — помечаем флаг (читается в chat.html при showXP())
        window._SH_xp_enabled = val;
        break;

      case 'tts':
        // Кнопки озвучки — скрыть/показать все .tts-inline
        document.querySelectorAll('.tts-inline, .action-btn.explain-btn:not(.action-btn.step-btn):not(.action-btn.exam-btn)')
          .forEach(btn => {
            if (btn.textContent.includes('Озвучить') || btn.innerHTML.includes('🔊')) {
              btn.style.display = val ? '' : 'none';
            }
          });
        window._SH_tts_enabled = val;
        break;

      case 'enter':
        // Отправка по Enter — патчим textarea в чате
        window._SH_enter_enabled = val;
        break;

      case 'anim':
        // Анимация текста
        window._SH_anim_enabled = val;
        break;

      case 'remind':
        window._SH_remind_enabled = val;
        break;
    }
  }

  // ── Применить все настройки ──
  function applyAll() {
    Object.keys(DEFAULTS).forEach(key => applyOne(key, get(key)));
  }

  // ── Применяем сразу (до DOMContentLoaded для критичных настроек) ──
  // Фон и Файрик применяем сразу — остальное после DOM
  window._SH_xp_enabled     = get('xp');
  window._SH_tts_enabled    = get('tts');
  window._SH_enter_enabled  = get('enter');
  window._SH_anim_enabled   = get('anim');
  window._SH_remind_enabled = get('remind');

  // После DOM — применяем DOM-зависимые настройки
  function onReady() {
    applyAll();

    // Патч Enter в чате
    const textarea = document.getElementById('question');
    if (textarea) {
      // Удаляем старый обработчик (если был) и ставим новый с проверкой настройки
      textarea.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          if (window._SH_enter_enabled) {
            e.preventDefault();
            if (typeof askTutor === 'function') askTutor();
          }
        }
      }, true); // capture=true чтобы перехватить до старого обработчика
    }

    // Наблюдатель — когда добавляются новые кнопки TTS, сразу скрываем если надо
    if (!get('tts')) {
      const obs = new MutationObserver(() => {
        document.querySelectorAll('.tts-inline').forEach(btn => {
          btn.style.display = 'none';
        });
      });
      const chat = document.getElementById('chat');
      if (chat) obs.observe(chat, { childList: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', onReady);
  } else {
    onReady();
  }

  // ── Публичное API ──
  window.SH = { get, set, applyAll, DEFAULTS };

})();