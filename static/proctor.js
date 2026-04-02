/**
 * proctor.js — Прокторинг экзамена + Режим фокуса для SubjectHelper
 *
 * ═══════════════════════════════════════════════════════
 * ПОДКЛЮЧЕНИЕ в chat.html перед </body>:
 *   <script src="{{ url_for('static', filename='proctor.js') }}"></script>
 *
 * ═══════════════════════════════════════════════════════
 * ИСПОЛЬЗОВАНИЕ:
 *
 * // Запуск прокторинга (режим exam):
 *   Proctor.start({ examId: 123, totalQuestions: 10 });
 *
 * // Остановка (экзамен сдан):
 *   Proctor.stop();
 *
 * // Запуск режима фокуса (любой режим):
 *   FocusMode.start();
 *   FocusMode.stop();
 *
 * // Колбэки:
 *   Proctor.onForceEnd = (data) => { /* экзамен завершён досрочно * / }
 * ═══════════════════════════════════════════════════════
 */

(function () {
  'use strict';

  // ══════════════════════════════════════════════════════
  //  СТИЛИ
  // ══════════════════════════════════════════════════════
  const CSS = `
    /* ── Оверлей ── */
    #proctor-overlay {
      position: fixed; inset: 0; z-index: 10000;
      background: rgba(0,0,0,.72); backdrop-filter: blur(6px);
      display: flex; align-items: center; justify-content: center;
      padding: 20px; animation: pOverlayIn .25s ease;
    }
    @keyframes pOverlayIn { from{opacity:0} to{opacity:1} }

    /* ── Карточка предупреждения ── */
    #proctor-card {
      background: #13111f; border-radius: 22px;
      border: 1px solid rgba(255,107,107,.35);
      padding: 28px 26px; max-width: 440px; width: 100%;
      position: relative; overflow: hidden;
      animation: pCardIn .4s cubic-bezier(.34,1.56,.64,1);
    }
    @keyframes pCardIn { from{transform:scale(.88) translateY(16px);opacity:0} to{transform:scale(1) translateY(0);opacity:1} }
    #proctor-card::before {
      content:''; position:absolute; top:0; left:0; right:0; height:3px;
      background: linear-gradient(90deg,#ff6b6b,#ff9d4d);
    }
    #proctor-card.final::before { background: #ff6b6b; }
    #proctor-card.focus { border-color: rgba(162,155,254,.35); }
    #proctor-card.focus::before { background: linear-gradient(90deg,#a29bfe,#4ecdc4); }

    /* ── Шапка ── */
    .pc-head { display:flex; align-items:center; gap:13px; margin-bottom:16px; }
    .pc-emoji { font-size:2.6rem; display:block; }
    .pc-title { font-size:1.05rem; font-weight:700; color:white; margin-bottom:3px; }
    .pc-sub   { font-size:.75rem; color:rgba(255,255,255,.4); font-family:monospace; }
    .pc-title.danger { color:#ff6b6b; }
    .pc-title.focus  { color:#a29bfe; }

    /* ── Текст ── */
    .pc-text {
      font-size:.88rem; color:rgba(255,255,255,.8);
      line-height:1.7; margin-bottom:16px;
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    }
    .pc-text b { color:white; font-weight:700; }
    .pc-text .accent { color:#ff6b6b; font-weight:700; }
    .pc-text .accent-focus { color:#a29bfe; font-weight:700; }

    /* ── Счётчик предупреждений ── */
    .pc-warns {
      display:flex; gap:6px; margin-bottom:16px; align-items:center;
    }
    .pw-dot {
      width:26px; height:26px; border-radius:50%;
      display:flex; align-items:center; justify-content:center;
      font-size:.72rem; font-weight:700;
      transition: all .3s ease;
    }
    .pw-dot.empty { background:rgba(255,255,255,.07); color:rgba(255,255,255,.3); }
    .pw-dot.used  {
      background:rgba(255,107,107,.2); color:#ff6b6b;
      border:1.5px solid rgba(255,107,107,.45);
      box-shadow: 0 0 8px rgba(255,107,107,.3);
    }
    .pw-label { font-size:.72rem; color:rgba(255,107,107,.8); font-family:monospace; margin-left:4px; }

    /* ── Кнопка ── */
    .pc-btn {
      width:100%; padding:13px; border-radius:18px; border:none;
      font-size:.92rem; font-weight:700; cursor:pointer;
      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
      transition:all .2s;
    }
    .pc-btn.danger {
      background:linear-gradient(135deg,#ff6b6b,#ff9d4d);
      color:white; box-shadow:0 4px 18px rgba(255,107,107,.35);
    }
    .pc-btn.danger:hover:not(:disabled) { transform:translateY(-1px); opacity:.92; }
    .pc-btn.danger:disabled { background:rgba(255,255,255,.08); color:rgba(255,255,255,.3); box-shadow:none; cursor:not-allowed; }
    .pc-btn.neutral {
      background:rgba(255,255,255,.07); color:rgba(255,255,255,.6);
      border:1px solid rgba(255,255,255,.1); margin-top:8px;
    }
    .pc-btn.focus-btn {
      background:rgba(162,155,254,.15); color:#a29bfe;
      border:1px solid rgba(162,155,254,.25);
    }
    .pc-btn.focus-btn:hover { background:rgba(162,155,254,.25); }

    /* ── Статус бар ── */
    #proctor-statusbar {
      position: fixed; top: 0; left: 0; right: 0; z-index: 9000;
      background: rgba(10,8,18,.95); border-bottom: 1px solid rgba(255,255,255,.08);
      padding: 8px 20px; display: flex; align-items: center;
      justify-content: space-between; gap: 12px;
      transform: translateY(-100%); transition: transform .3s ease;
    }
    #proctor-statusbar.visible { transform: translateY(0); }
    .psb-left  { display:flex; align-items:center; gap:8px; }
    .psb-dot   { width:7px; height:7px; border-radius:50%; }
    .psb-dot.ok    { background:#4ecdc4; animation:psDotPulse 2s ease-in-out infinite; }
    .psb-dot.warn  { background:#ff9d4d; animation:psDotPulse .8s ease-in-out infinite; }
    .psb-dot.danger{ background:#ff6b6b; animation:psDotPulse .5s ease-in-out infinite; }
    @keyframes psDotPulse { 0%,100%{opacity:.4}50%{opacity:1} }
    .psb-text { font-size:.76rem; color:rgba(255,255,255,.6); font-family:monospace; }
    .psb-warns { display:flex; gap:4px; }
    .psb-w { width:18px; height:18px; border-radius:50%; font-size:.6rem; font-weight:700;
              display:flex; align-items:center; justify-content:center; }
    .psb-w.empty { background:rgba(255,255,255,.07); color:rgba(255,255,255,.2); }
    .psb-w.used  { background:rgba(255,107,107,.2); color:#ff6b6b;
                   border:1px solid rgba(255,107,107,.35); }

    /* ── Финальная статистика ── */
    .pc-stats { display:flex; gap:10px; margin-bottom:18px; }
    .pc-stat {
      flex:1; background:rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.08);
      border-radius:12px; padding:10px; text-align:center;
    }
    .pc-stat-n { font-size:1.5rem; font-weight:700; color:white; font-family:monospace; }
    .pc-stat-l { font-size:.68rem; color:rgba(255,255,255,.4); margin-top:2px; }

    /* ── Фокус: мини-бар ── */
    #focus-minibar {
      position: fixed; top: 12px; right: 12px; z-index: 8500;
      background: rgba(13,11,24,.92); border: 1px solid rgba(162,155,254,.25);
      border-radius: 14px; padding: 8px 14px;
      display: flex; align-items: center; gap: 8px;
      font-size: .74rem; color: rgba(162,155,254,.8);
      font-family: monospace; cursor: pointer;
      transform: translateX(200px); opacity: 0;
      transition: all .35s ease;
    }
    #focus-minibar.visible { transform: translateX(0); opacity: 1; }
    #focus-minibar:hover { border-color: rgba(162,155,254,.5); }
    .fmb-dot { width:6px; height:6px; border-radius:50%; background:#a29bfe;
               animation:psDotPulse 2s ease-in-out infinite; }
  `;

  const styleEl = document.createElement('style');
  styleEl.textContent = CSS;
  document.head.appendChild(styleEl);

  // ══════════════════════════════════════════════════════
  //  ТЕКСТЫ ПРЕДУПРЕЖДЕНИЙ
  // ══════════════════════════════════════════════════════
  const EXAM_WARNINGS = [
    {
      emoji:   '😤',
      title:   'Предупреждение 1 из 3',
      sub:     'Ты покинул вкладку экзамена',
      text:    'Файрик заметил что ты переключился на другую страницу.<br>'
             + 'Во время экзамена это нарушение. Возвращайся и продолжай честно!',
      btnText: 'Понял, возвращаюсь →',
    },
    {
      emoji:   '😠',
      title:   'Предупреждение 2 из 3',
      sub:     'Снова покинул вкладку!',
      text:    'Файрик злится! Это уже второй раз.<br>'
             + '<span class="accent">Следующий выход завершит экзамен досрочно.</span><br>'
             + 'Это последний шанс — сосредоточься!',
      btnText: 'Последний раз, понял! →',
    },
    {
      emoji:   '🤬',
      title:   'ФИНАЛЬНОЕ ПРЕДУПРЕЖДЕНИЕ',
      sub:     'Третье нарушение зафиксировано',
      text:    'Файрик фиксирует нарушение правил экзамена.<br>'
             + '<span class="accent">Экзамен будет завершён досрочно.</span>',
      btnText: 'Экзамен завершается...',
      btnDisabled: true,
    },
  ];

  const FOCUS_WARNINGS = [
    {
      emoji: '🐉', title: 'Отвлёкся?', sub: 'Режим фокуса активен',
      text: 'Файрик заметил что ты ушёл с урока.<br>Ты занимаешься уже <b>{time}</b> — молодец!<br>Возвращайся, мы почти у цели 💪',
    },
    {
      emoji: '😕', title: 'Снова отвлёкся...', sub: 'Уже второй раз',
      text: 'Ты снова ушёл! Файрик немного расстроен.<br>Сосредоточься ещё на <b>{time}</b> — и можно отдохнуть.',
    },
    {
      emoji: '🥺', title: 'Ну пожалуйста...', sub: 'Третий раз',
      text: 'Файрик очень просит вернуться!<br>Ты можешь сосредоточиться. Последнее напоминание от Файрика.',
    },
  ];

  // ══════════════════════════════════════════════════════
  //  УТИЛИТЫ
  // ══════════════════════════════════════════════════════
  function formatTime(sec) {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m > 0 ? `${m} мин ${s} сек` : `${s} сек`;
  }

  function createOverlay() {
    const el = document.createElement('div');
    el.id = 'proctor-overlay';
    return el;
  }

  function removeOverlay() {
    const el = document.getElementById('proctor-overlay');
    if (el) el.remove();
  }

  // ══════════════════════════════════════════════════════
  //  ПРОКТОРИНГ ЭКЗАМЕНА
  // ══════════════════════════════════════════════════════
  const Proctor = {
    active:          false,
    warnCount:       0,
    examId:          null,
    totalQuestions:  10,
    answeredCount:   0,
    startTime:       null,
    onForceEnd:      null,  // callback(data)

    _handlers: {},

    start(opts = {}) {
      this.active         = true;
      this.warnCount      = 0;
      this.examId         = opts.examId || null;
      this.totalQuestions = opts.totalQuestions || 10;
      this.answeredCount  = 0;
      this.startTime      = Date.now();

      this._showStatusBar();
      this._bindEvents();
      console.log('[Proctor] started, examId=', this.examId);
    },

    stop() {
      this.active = false;
      this._unbindEvents();
      this._hideStatusBar();
      removeOverlay();
      console.log('[Proctor] stopped');
    },

    // Внешний вызов — засчитать ответ на вопрос
    answerGiven() {
      this.answeredCount++;
    },

    _showStatusBar() {
      let bar = document.getElementById('proctor-statusbar');
      if (!bar) {
        bar = document.createElement('div');
        bar.id = 'proctor-statusbar';
        bar.innerHTML = `
          <div class="psb-left">
            <div class="psb-dot ok" id="psb-dot"></div>
            <div class="psb-text" id="psb-text">📋 Экзамен · Прокторинг активен</div>
          </div>
          <div class="psb-warns">
            <div class="psb-w empty" id="psb-w1">1</div>
            <div class="psb-w empty" id="psb-w2">2</div>
            <div class="psb-w empty" id="psb-w3">3</div>
          </div>`;
        document.body.appendChild(bar);
      }
      setTimeout(() => bar.classList.add('visible'), 100);
    },

    _hideStatusBar() {
      const bar = document.getElementById('proctor-statusbar');
      if (bar) { bar.classList.remove('visible'); setTimeout(() => bar.remove(), 400); }
    },

    _updateStatusBar(state = 'ok', text = '') {
      const dot  = document.getElementById('psb-dot');
      const txt  = document.getElementById('psb-text');
      if (dot) dot.className = `psb-dot ${state}`;
      if (txt && text) txt.textContent = text;
      // Обновляем точки
      for (let i = 1; i <= 3; i++) {
        const w = document.getElementById(`psb-w${i}`);
        if (w) w.className = `psb-w ${i <= this.warnCount ? 'used' : 'empty'}`;
      }
    },

    _bindEvents() {
      const self = this;

      // Переключение вкладки
      this._handlers.visChange = () => {
        if (document.hidden && self.active) self._onViolation('tab');
      };
      document.addEventListener('visibilitychange', this._handlers.visChange);

      // Потеря фокуса окна
      this._handlers.blur = () => {
        if (self.active) self._onViolation('blur');
      };
      window.addEventListener('blur', this._handlers.blur);

      // Попытка покинуть страницу
      this._handlers.beforeUnload = (e) => {
        if (self.active) {
          e.preventDefault();
          e.returnValue = 'Экзамен идёт! Ты уверен что хочешь выйти?';
          return e.returnValue;
        }
      };
      window.addEventListener('beforeunload', this._handlers.beforeUnload);

      // Попытка открыть DevTools (F12, Ctrl+Shift+I)
      this._handlers.keydown = (e) => {
        if (!self.active) return;
        if (e.key === 'F12') { e.preventDefault(); self._onViolation('devtools'); }
        if (e.ctrlKey && e.shiftKey && ['I','J','C'].includes(e.key)) {
          e.preventDefault(); self._onViolation('devtools');
        }
        // Ctrl+Tab — переключение вкладок
        if (e.ctrlKey && e.key === 'Tab') { e.preventDefault(); self._onViolation('tab'); }
      };
      document.addEventListener('keydown', this._handlers.keydown);
    },

    _unbindEvents() {
      document.removeEventListener('visibilitychange', this._handlers.visChange);
      window.removeEventListener('blur',              this._handlers.blur);
      window.removeEventListener('beforeunload',      this._handlers.beforeUnload);
      document.removeEventListener('keydown',         this._handlers.keydown);
    },

    _onViolation(type) {
      if (!this.active) return;
      this.warnCount++;

      const violationText = {
        tab:      'переключился на другую вкладку',
        blur:     'перешёл в другое окно',
        devtools: 'открыл инструменты разработчика',
      }[type] || 'покинул страницу экзамена';

      console.warn(`[Proctor] violation #${this.warnCount}: ${type}`);

      // Отправляем на сервер
      this._logViolation(type);

      if (this.warnCount >= 3) {
        this._showWarning(2, violationText, true);
      } else {
        this._showWarning(this.warnCount - 1, violationText, false);
      }

      this._updateStatusBar(
        this.warnCount >= 3 ? 'danger' : 'warn',
        `🚨 Нарушение #${this.warnCount} зафиксировано`
      );
    },

    _showWarning(msgIdx, violationText, isFinal) {
      removeOverlay();
      const overlay = createOverlay();
      const msg     = EXAM_WARNINGS[Math.min(msgIdx, EXAM_WARNINGS.length - 1)];

      overlay.innerHTML = `
        <div id="proctor-card" ${isFinal ? 'class="final"' : ''}>
          <div class="pc-head">
            <span class="pc-emoji">${msg.emoji}</span>
            <div>
              <div class="pc-title danger">${msg.title}</div>
              <div class="pc-sub">${violationText}</div>
            </div>
          </div>
          <div class="pc-text">${msg.text}</div>
          <div class="pc-warns">
            ${[1,2,3].map(i => `<div class="pw-dot ${i <= this.warnCount ? 'used' : 'empty'}">${i}</div>`).join('')}
            <span class="pw-label">${isFinal ? 'Предупреждения исчерпаны' : `Осталось: ${3 - this.warnCount}`}</span>
          </div>
          <button class="pc-btn danger" id="pc-dismiss-btn" ${msg.btnDisabled ? 'disabled' : ''}>
            ${msg.btnText}
          </button>
        </div>`;

      document.body.appendChild(overlay);

      if (isFinal) {
        setTimeout(() => { this._forceEnd(); }, 2500);
      } else {
        document.getElementById('pc-dismiss-btn')?.addEventListener('click', () => {
          removeOverlay();
          this._updateStatusBar('ok', '📋 Экзамен · Прокторинг активен');
        });
      }

      // Файрик реагирует
      if (window.Fairik) {
        if (isFinal) Fairik.sad('Экзамен завершён досрочно 😔');
        else         Fairik.say(`⚠️ Предупреждение ${this.warnCount}/3!`, 'shake');
      }
    },

    _forceEnd() {
      this.active = false;
      this._unbindEvents();
      removeOverlay();

      const elapsed = Math.round((Date.now() - this.startTime) / 1000);
      const data    = {
        reason:        'proctor_violations',
        warnings:      3,
        answered:      this.answeredCount,
        total:         this.totalQuestions,
        elapsed_sec:   elapsed,
        exam_id:       this.examId,
      };

      // Показываем финальный экран
      const overlay = createOverlay();
      overlay.innerHTML = `
        <div id="proctor-card" class="final">
          <div class="pc-head">
            <span class="pc-emoji">🛑</span>
            <div>
              <div class="pc-title danger">Экзамен завершён досрочно</div>
              <div class="pc-sub">3 нарушения зафиксированы</div>
            </div>
          </div>
          <div class="pc-text">
            Файрик вынужден завершить экзамен. Результат аннулирован.<br>
            <span class="accent">Экзамен можно пересдать позже.</span>
          </div>
          <div class="pc-stats">
            <div class="pc-stat"><div class="pc-stat-n">3</div><div class="pc-stat-l">нарушения</div></div>
            <div class="pc-stat"><div class="pc-stat-n">${this.answeredCount}</div><div class="pc-stat-l">вопросов</div></div>
            <div class="pc-stat"><div class="pc-stat-n">${formatTime(elapsed)}</div><div class="pc-stat-l">в экзамене</div></div>
          </div>
          <button class="pc-btn neutral" id="pc-to-main">На главную</button>
        </div>`;
      document.body.appendChild(overlay);

      document.getElementById('pc-to-main')?.addEventListener('click', () => {
        window.location.href = '/';
      });

      this._hideStatusBar();

      // Отправляем на сервер
      this._reportForceEnd(data);

      // Вызываем внешний колбэк
      if (typeof this.onForceEnd === 'function') this.onForceEnd(data);
    },

    async _logViolation(type) {
      try {
        await fetch('/api/proctor/violation', {
          method: 'POST', credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ exam_id: this.examId, type, warn_num: this.warnCount }),
        });
      } catch(e) { /* нет сети — не критично */ }
    },

    async _reportForceEnd(data) {
      try {
        await fetch('/api/proctor/force_end', {
          method: 'POST', credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
      } catch(e) { /* нет сети — не критично */ }
    },
  };


  // ══════════════════════════════════════════════════════
  //  РЕЖИМ ФОКУСА
  // ══════════════════════════════════════════════════════
  const FocusMode = {
    active:      false,
    warnCount:   0,
    startTime:   null,
    sessionGoal: 25 * 60,  // 25 минут по умолчанию (Pomodoro)
    _timer:      null,
    _handlers:   {},

    start(opts = {}) {
      this.active      = true;
      this.warnCount   = 0;
      this.startTime   = Date.now();
      this.sessionGoal = (opts.minutes || 25) * 60;

      this._showMinibar();
      this._bindEvents();
      console.log('[FocusMode] started');
    },

    stop() {
      this.active = false;
      this._unbindEvents();
      this._hideMinibar();
      removeOverlay();
      clearInterval(this._timer);
      console.log('[FocusMode] stopped');
    },

    _showMinibar() {
      let bar = document.getElementById('focus-minibar');
      if (!bar) {
        bar = document.createElement('div');
        bar.id = 'focus-minibar';
        bar.title = 'Режим фокуса активен';
        bar.innerHTML = `<div class="fmb-dot"></div><span id="fmb-text">🎯 Фокус · 00:00</span>`;
        bar.addEventListener('click', () => FocusMode.stop());
        document.body.appendChild(bar);
      }
      setTimeout(() => bar.classList.add('visible'), 100);

      // Таймер
      this._timer = setInterval(() => {
        const elapsed = Math.round((Date.now() - this.startTime) / 1000);
        const m = Math.floor(elapsed / 60).toString().padStart(2, '0');
        const s = (elapsed % 60).toString().padStart(2, '0');
        const txt = document.getElementById('fmb-text');
        if (txt) txt.textContent = `🎯 Фокус · ${m}:${s}`;
      }, 1000);
    },

    _hideMinibar() {
      const bar = document.getElementById('focus-minibar');
      if (bar) { bar.classList.remove('visible'); setTimeout(() => bar.remove(), 400); }
    },

    _bindEvents() {
      const self = this;
      let lastBlurTime = 0;

      this._handlers.visChange = () => {
        if (document.hidden && self.active) {
          const now = Date.now();
          if (now - lastBlurTime > 3000) { // дебаунс 3 сек
            lastBlurTime = now;
            setTimeout(() => { if (document.hidden) self._onDistraction(); }, 1500);
          }
        }
      };
      document.addEventListener('visibilitychange', this._handlers.visChange);

      this._handlers.blur = () => {
        if (!self.active) return;
        const now = Date.now();
        if (now - lastBlurTime > 3000) {
          lastBlurTime = now;
          setTimeout(() => { if (!document.hasFocus()) self._onDistraction(); }, 2000);
        }
      };
      window.addEventListener('blur', this._handlers.blur);
    },

    _unbindEvents() {
      document.removeEventListener('visibilitychange', this._handlers.visChange);
      window.removeEventListener('blur', this._handlers.blur);
    },

    _onDistraction() {
      if (!this.active) return;
      this.warnCount++;

      const elapsed     = Math.round((Date.now() - this.startTime) / 1000);
      const remaining   = Math.max(0, this.sessionGoal - elapsed);
      const msgIdx      = Math.min(this.warnCount - 1, FOCUS_WARNINGS.length - 1);
      const msg         = FOCUS_WARNINGS[msgIdx];
      const elapsedStr  = formatTime(elapsed);
      const remainStr   = formatTime(remaining);

      const text = msg.text
        .replace('{time}', elapsedStr)
        .replace('{remaining}', remainStr);

      removeOverlay();
      const overlay = createOverlay();
      overlay.style.background = 'rgba(0,0,0,.55)';
      overlay.innerHTML = `
        <div id="proctor-card" class="focus">
          <div class="pc-head">
            <span class="pc-emoji">${msg.emoji}</span>
            <div>
              <div class="pc-title focus">${msg.title}</div>
              <div class="pc-sub">${msg.sub}</div>
            </div>
          </div>
          <div class="pc-text">${text}</div>
          <button class="pc-btn focus-btn" id="fc-back-btn">Я здесь, продолжаем! →</button>
          <button class="pc-btn neutral" id="fc-stop-btn" style="margin-top:8px">Завершить сессию</button>
        </div>`;

      document.body.appendChild(overlay);

      document.getElementById('fc-back-btn')?.addEventListener('click', () => removeOverlay());
      document.getElementById('fc-stop-btn')?.addEventListener('click', () => {
        removeOverlay(); this.stop();
      });

      if (window.Fairik) {
        Fairik.say(msg.title === 'Отвлёкся?' ? '🎯 Возвращайся!' : '🥺 Пожалуйста, вернись!');
      }
    },
  };


  // ══════════════════════════════════════════════════════
  //  ЭКСПОРТ
  // ══════════════════════════════════════════════════════
  window.Proctor   = Proctor;
  window.FocusMode = FocusMode;

})();