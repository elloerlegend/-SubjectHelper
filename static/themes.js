/**
 * themes.js — Система тем для SubjectHelper
 * Подключи ПЕРВЫМ скриптом на каждой странице (до fairik.js):
 *   <script src="{{ url_for('static', filename='themes.js') }}"></script>
 */

(function () {
  'use strict';

  const THEMES = {

    dark: {
      name: 'Тёмная', emoji: '🌑', desc: 'Классика',
      body: '#0d0d1a', color: '#e8e8f0',
      inputs: '#1a1a2e', inputColor: '#e8e8f0', placeholder: '#6a6a88',
      vars: {
        '--bg':'#0d0d1a','--bg2':'#12121f',
        '--surface':'#1a1a2e','--surface2':'#222238',
        '--border':'rgba(255,255,255,0.08)','--border2':'rgba(255,255,255,0.15)',
        '--text':'#e8e8f0','--text2':'#b0b0c8','--text3':'#6a6a88',
        '--accent':'#00ff88','--accent2':'#00cc6a','--accent3':'#00ffaa',
        '--blue':'#4fc3f7','--purple':'#a78bfa',
        '--warning':'#ffd54f','--danger':'#ef5350',
      },
    },

    light: {
      name: 'Светлая', emoji: '☀️', desc: 'Чистота',
      body: '#f4f6fb', color: '#1a1a2e',
      inputs: '#ffffff', inputColor: '#1a1a2e', placeholder: '#8888aa',
      vars: {
        '--bg':'#f4f6fb','--bg2':'#eef0f8',
        '--surface':'#ffffff','--surface2':'#f0f2f9',
        '--border':'rgba(0,0,0,0.08)','--border2':'rgba(0,0,0,0.15)',
        '--text':'#1a1a2e','--text2':'#3d3d5c','--text3':'#8888aa',
        '--accent':'#00a85a','--accent2':'#008a4a','--accent3':'#00cc6a',
        '--blue':'#1976d2','--purple':'#7c3aed',
        '--warning':'#f59e0b','--danger':'#dc2626',
      },
    },

    ocean: {
      name: 'Океан', emoji: '🌊', desc: 'Глубина',
      body: '#020b18', color: '#cce8ff',
      inputs: '#062035', inputColor: '#cce8ff', placeholder: '#3a7aaa',
      vars: {
        '--bg':'#020b18','--bg2':'#041525',
        '--surface':'#062035','--surface2':'#0a2d4a',
        '--border':'rgba(0,180,255,0.12)','--border2':'rgba(0,180,255,0.22)',
        '--text':'#cce8ff','--text2':'#88bfe8','--text3':'#3a7aaa',
        '--accent':'#00d4ff','--accent2':'#00aadd','--accent3':'#40e0ff',
        '--blue':'#60cfff','--purple':'#7cb8ff',
        '--warning':'#ffcc44','--danger':'#ff6060',
      },
    },

    sunset: {
      name: 'Закат', emoji: '🌅', desc: 'Тепло',
      body: '#1a0a08', color: '#ffe8d8',
      inputs: '#2e1410', inputColor: '#ffe8d8', placeholder: '#aa6650',
      vars: {
        '--bg':'#1a0a08','--bg2':'#240e0a',
        '--surface':'#2e1410','--surface2':'#3d1c18',
        '--border':'rgba(255,120,60,0.12)','--border2':'rgba(255,120,60,0.22)',
        '--text':'#ffe8d8','--text2':'#ffb899','--text3':'#aa6650',
        '--accent':'#ff7c3a','--accent2':'#e86420','--accent3':'#ff9a60',
        '--blue':'#ffc060','--purple':'#ff88aa',
        '--warning':'#ffdd44','--danger':'#ff4444',
      },
    },

    forest: {
      name: 'Лес', emoji: '🌿', desc: 'Природа',
      body: '#060f08', color: '#d0f0d8',
      inputs: '#0f1f12', inputColor: '#d0f0d8', placeholder: '#4a7a52',
      vars: {
        '--bg':'#060f08','--bg2':'#0a160c',
        '--surface':'#0f1f12','--surface2':'#162a1a',
        '--border':'rgba(60,200,80,0.12)','--border2':'rgba(60,200,80,0.22)',
        '--text':'#d0f0d8','--text2':'#8ec89a','--text3':'#4a7a52',
        '--accent':'#44dd66','--accent2':'#30b850','--accent3':'#66ee88',
        '--blue':'#60d8a0','--purple':'#88e8a0',
        '--warning':'#ccee44','--danger':'#ee5555',
      },
    },

    galaxy: {
      name: 'Галактика', emoji: '🌌', desc: 'Космос',
      body: '#04020f', color: '#e8e0ff',
      inputs: '#0e0828', inputColor: '#e8e0ff', placeholder: '#6a58b0',
      vars: {
        '--bg':'#04020f','--bg2':'#08041a',
        '--surface':'#0e0828','--surface2':'#150d38',
        '--border':'rgba(167,139,250,0.14)','--border2':'rgba(167,139,250,0.25)',
        '--text':'#e8e0ff','--text2':'#b8a8f0','--text3':'#6a58b0',
        '--accent':'#a78bfa','--accent2':'#8b6ee8','--accent3':'#c4a8ff',
        '--blue':'#60a8ff','--purple':'#e088ff',
        '--warning':'#ffd060','--danger':'#ff6080',
      },
    },

    rose: {
      name: 'Розовая', emoji: '🌸', desc: 'Нежность',
      body: '#1a0812', color: '#ffe0f0',
      inputs: '#2e1020', inputColor: '#ffe0f0', placeholder: '#aa6080',
      vars: {
        '--bg':'#1a0812','--bg2':'#240c18',
        '--surface':'#2e1020','--surface2':'#3d162c',
        '--border':'rgba(255,100,160,0.12)','--border2':'rgba(255,100,160,0.22)',
        '--text':'#ffe0f0','--text2':'#ffb0cc','--text3':'#aa6080',
        '--accent':'#ff6eb0','--accent2':'#e84d9a','--accent3':'#ff90c8',
        '--blue':'#ff80d0','--purple':'#cc88ff',
        '--warning':'#ffcc60','--danger':'#ff4466',
      },
    },

    midnight: {
      name: 'Полночь', emoji: '🌙', desc: 'Глубокий мрак',
      body: '#000008', color: '#d0d0f8',
      inputs: '#060618', inputColor: '#d0d0f8', placeholder: '#404080',
      vars: {
        '--bg':'#000008','--bg2':'#020210',
        '--surface':'#060618','--surface2':'#0a0a22',
        '--border':'rgba(100,100,220,0.12)','--border2':'rgba(100,100,220,0.22)',
        '--text':'#d0d0f8','--text2':'#9090cc','--text3':'#404080',
        '--accent':'#6060ff','--accent2':'#4040ee','--accent3':'#8888ff',
        '--blue':'#4090ff','--purple':'#9060ff',
        '--warning':'#ffcc44','--danger':'#ff4455',
      },
    },

  };

  const STORAGE_KEY = 'sh_theme';
  const DEFAULT     = 'dark';

  // ── Глобальный CSS сброс — инжектируется один раз ──
  function injectBaseCSS() {
    if (document.getElementById('sh-theme-base')) return;
    const s = document.createElement('style');
    s.id = 'sh-theme-base';
    s.textContent = `
      html { background-color: var(--bg) !important; color: var(--text) !important; }
      body { background-color: var(--bg) !important; color: var(--text) !important; }

      /* ══ ПОЛЯ ВВОДА — полный сброс браузерных стилей ══ */
      textarea,
      input[type="text"],
      input[type="email"],
      input[type="password"],
      input[type="search"],
      input[type="number"],
      select {
        background-color: var(--surface) !important;
        color: var(--text) !important;
        border-color: var(--border2) !important;
        caret-color: var(--accent) !important;
        outline: none !important;
        box-shadow: none !important;
        -webkit-appearance: none !important;
        -moz-appearance: none !important;
      }
      textarea:focus,
      input:focus,
      select:focus {
        outline: none !important;
        box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 30%, transparent) !important;
        border-color: var(--accent) !important;
      }
      textarea:hover,
      input:hover {
        border-color: var(--border2) !important;
        outline: none !important;
      }
      textarea::placeholder,
      input::placeholder {
        color: var(--text3) !important;
        opacity: 1 !important;
      }

      /* ══ ОБЁРТКА ПОЛЯ ВВОДА В ЧАТЕ ══ */
      .input-wrapper,
      .input-wrapper *,
      #inputContainer {
        background-color: var(--surface) !important;
        border-color: var(--border2) !important;
        outline: none !important;
        box-shadow: none !important;
      }
      #question, #question:focus, #question:hover {
        background: transparent !important;
        color: var(--text) !important;
        outline: none !important;
        box-shadow: none !important;
        border: none !important;
      }

      /* ══ ШАПКА ══ */
      header {
        background-color: var(--bg) !important;
        border-bottom: 1px solid var(--border) !important;
      }

      /* ══ СООБЩЕНИЯ ЧАТА ══ */
      .message.ai { background: var(--surface) !important; color: var(--text) !important; }
      .message.user > div { background: var(--surface2) !important; color: var(--text) !important; }

      /* ══ ЭКЗАМЕННЫЙ TEXTAREA ══ */
      .exam-input,
      .exam-input:focus {
        background: var(--surface) !important;
        color: var(--text) !important;
        border-color: var(--border2) !important;
        outline: none !important;
        box-shadow: none !important;
      }

      /* ══ УБИРАЕМ АВТОЗАПОЛНЕНИЕ БРАУЗЕРА (жёлтый/белый фон) ══ */
      input:-webkit-autofill,
      input:-webkit-autofill:hover,
      input:-webkit-autofill:focus,
      textarea:-webkit-autofill {
        -webkit-box-shadow: 0 0 0 1000px var(--surface) inset !important;
        -webkit-text-fill-color: var(--text) !important;
        caret-color: var(--text) !important;
      }

      /* Карточки */
      .mode-card, .class-card, .subject-card, .interest-card,
      .chat-item, .settings-card, .lobby-box, .duel-code-box,
      .question-card, .quiz-card, .exam-card,
      .answer-btn, .skin-card, .mode-grid > div {
        background: var(--surface) !important;
        border-color: var(--border) !important;
        color: var(--text) !important;
      }

      /* Dropdown */
      .dropdown-menu {
        background: var(--surface) !important;
        border-color: var(--border2) !important;
      }
      .dropdown-menu a { color: var(--text2) !important; }
      .dropdown-menu a:hover {
        color: var(--accent) !important;
        background: var(--surface2) !important;
      }

      /* Модалки */
      .modal-box { background: var(--surface) !important; border-color: var(--border2) !important; }
      .modal-input { background: var(--surface) !important; color: var(--text) !important; }

      /* Фильтры и поиск */
      #searchInput, #subjectFilter { background: var(--surface) !important; color: var(--text) !important; }

      /* Скроллбар */
      ::-webkit-scrollbar { width: 5px; }
      ::-webkit-scrollbar-track { background: var(--bg); }
      ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 3px; }
      ::-webkit-scrollbar-thumb:hover { background: var(--text3); }
    `;
    document.head.appendChild(s);
  }

  // ── Применение темы ──
  function apply(id) {
    const theme = THEMES[id];
    if (!theme) return;

    const root = document.documentElement;

    // 1. CSS-переменные на :root
    Object.entries(theme.vars).forEach(([k, v]) => root.style.setProperty(k, v));

    // 2. Принудительный bg на html и body
    root.style.backgroundColor = theme.body;
    root.style.color           = theme.color;
    if (document.body) {
      document.body.style.backgroundColor = theme.body;
      document.body.style.color           = theme.color;
    }

    // 3. Сохраняем
    localStorage.setItem(STORAGE_KEY, id);
    root.setAttribute('data-theme', id);

    // 4. Обновляем кнопки на странице настроек
    document.querySelectorAll('.theme-btn[data-theme]').forEach(b => {
      b.classList.toggle('active', b.dataset.theme === id);
    });

    // 5. Прозрачность анимированного фона
    const canvas = document.getElementById('formula-canvas');
    if (canvas) canvas.style.opacity = id === 'light' ? '0.3' : '0.65';

    // 6. Принудительно убираем outline/box-shadow у всех полей ввода
    //    (перебивает браузерный дефолт и chat.css)
    if (document.body) {
      const t = theme;
      const sel = 'textarea, input, select, .input-wrapper, #inputContainer';
      document.querySelectorAll(sel).forEach(el => {
        el.style.outline    = 'none';
        el.style.boxShadow  = 'none';
      });
      // Особо — textarea#question в чате
      const q = document.getElementById('question');
      if (q) {
        q.style.background = 'transparent';
        q.style.outline    = 'none';
        q.style.boxShadow  = 'none';
        q.style.border     = 'none';
        q.style.color      = t.color;
      }
      // .input-wrapper получает цвет темы
      document.querySelectorAll('.input-wrapper').forEach(el => {
        el.style.background = t.inputs;
      });
      // #inputContainer border
      const ic = document.getElementById('inputContainer');
      if (ic) {
        ic.style.borderColor = theme.vars['--border2'];
        ic.style.background  = t.inputs;
        ic.style.outline     = 'none';
        ic.style.boxShadow   = 'none';
      }
    }
  }

  function current() {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT;
  }

  // ── Init: применяем ДО рендера чтобы не было вспышки ──
  injectBaseCSS();
  apply(current());

  // Повторно после DOMContentLoaded (body уже точно существует)
  const applyOnReady = () => apply(current());
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyOnReady);
  } else {
    applyOnReady();
  }


  // ── Восстанавливаем размер шрифта при загрузке ──
  (function restoreFontSize() {
    const idx   = parseInt(localStorage.getItem('sh_fs_idx') || '2');
    const sizes = ['12px','14px','16px','18px','20px'];
    const size  = sizes[Math.max(0, Math.min(4, idx))];
    document.documentElement.style.fontSize = size;
    if (document.body) document.body.style.fontSize = size;
    // После DOMContentLoaded тоже применяем (body точно есть)
    document.addEventListener('DOMContentLoaded', () => {
      document.body.style.fontSize = size;
    });
  })();

  // ── Публичное API ──
  window.Themes = {
    apply,
    current,
    list: () => Object.entries(THEMES).map(([id, t]) => ({
      id, name: t.name, emoji: t.emoji, desc: t.desc,
    })),
  };

})();