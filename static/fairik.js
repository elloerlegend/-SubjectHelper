/**
 * fairik.js v3 — Живой маскот-дракончик для SubjectHelper
 *
 * API:
 *   Fairik.happy(msg)      — правильный ответ
 *   Fairik.sad(msg)        — ошибка
 *   Fairik.celebrate()     — победа / level up
 *   Fairik.streak(n)       — стрик N дней
 *   Fairik.addXP(n)        — начислить XP
 *   Fairik.setLevel(n)     — установить уровень
 *   Fairik.say(text, anim) — произвольная фраза
 *   Fairik.think()         — думает (пока ИИ печатает)
 *   Fairik.doneThinking()  — перестаёт думать
 */
(function () {
  'use strict';

  // ═══════════════════════════════════════
  //  УРОВНИ
  // ═══════════════════════════════════════
  const LEVELS = [
    null,
    { name:'Малыш',   glow:'#4ecdc4', hue:0,   crown:false },
    { name:'Ученик',  glow:'#a29bfe', hue:195, crown:false },
    { name:'Знаток',  glow:'#f9ca24', hue:312, crown:false },
    { name:'Мастер',  glow:'#fd79a8', hue:278, crown:false },
    { name:'Легенда', glow:'#ffd700', hue:30,  crown:true  },
  ];
  const XP_PER_LEVEL = [0,0,200,500,1000,2000];

  // ═══════════════════════════════════════
  //  ФРАЗЫ — богатая база
  // ═══════════════════════════════════════
  const P = {
    happy: [
      'Вот это да! Ты молодец! 🎉',
      'Правильно! Я так и знал! ⭐',
      'ОГОНЬ! Продолжай в том же духе! 🔥',
      'Ты умница! Горжусь тобой! 💪',
      'Точно в цель! 🎯',
      'Браво! Так держать! 🏆',
      'Я верил в тебя! Отлично! ✨',
      'Вот это мозги! 🧠',
    ],
    sad: [
      'Не беда! Ошибки — это опыт 💪',
      'Почти! Давай разберём вместе? 🤝',
      'Ничего страшного, попробуем ещё! 🔄',
      'Ты справишься, я уверен! 🐉',
      'Ошибся? Значит учишься! 📚',
      'Не сдавайся! Следующий раз — твой! ⚡',
      'Файрик верит в тебя! Давай снова! 🌟',
    ],
    thinking: [
      'Хмм, интересный вопрос... 🤔',
      'Дайте-ка подумаю... 💭',
      'О, сложно! Сейчас разберём! 🧩',
      'Мои нейроны работают! ⚡',
    ],
    idle: [
      'Эй, задай вопрос! Мне скучно 😄',
      'Я готов помочь! Что изучаем? 📚',
      'Не стесняйся, спрашивай! 🐉',
      'Давно не занимались... 🌙',
      'Новые знания ждут тебя! 🚀',
      'Файрик всегда рядом! 😊',
    ],
    streak: [
      n => `🔥 ${n} дней подряд! Ты машина!`,
      n => `Стрик ${n} дней! Невероятно! 💥`,
      n => `${n} дней без пропусков! 🏆`,
    ],
    levelup: [
      '🎉 НОВЫЙ УРОВЕНЬ! Ты растёшь!',
      '⬆️ Уровень повышен! Ты крутой!',
      '🏆 Эволюция Файрика! И твоя тоже!',
    ],
    greeting: [
      name => `Привет, ${name}! Готов учиться? 🐉`,
      name => `С возвращением, ${name}! 😊`,
      name => `${name}! Я соскучился! 🌟`,
      () => 'Привет! Рад тебя видеть! 🐉',
    ],
    night: [
      '😴 Уже поздно, но ты молодец!',
      '🌙 Последнее задание — и спать!',
      '😴 Поздно учишься! Уважаю!',
    ],
    morning: [
      '☀️ Доброе утро! Начнём день с учёбы?',
      '🌅 Утро — лучшее время учиться!',
    ],
    xp: [
      n => `+${n} XP ⭐ Растём!`,
      n => `+${n} XP! Копим опыт 📈`,
    ],
    encourage: [
      'Ты можешь, я знаю! 💪',
      'Не сдавайся! 🔥',
      'Трудно? Значит растёшь! 🌱',
      'Каждый шаг важен! 👣',
    ],
    quiz_start: [
      'Проверим знания! Я верю в тебя! 🎯',
      'Квиз начинается! Давай! ⚡',
      'Покажи что умеешь! 🏆',
    ],
    correct_streak: [
      n => `${n} правильных подряд! 🔥`,
      n => `Серия из ${n}! Не останавливайся! 🚀`,
    ],
  };
  const rand = arr => arr[Math.floor(Math.random() * arr.length)];

  // ═══════════════════════════════════════
  //  SVG ДРАКОНЧИК
  // ═══════════════════════════════════════
  const SVG = `<svg id="fk-svg" width="110" height="130" viewBox="0 0 240 270"
     xmlns="http://www.w3.org/2000/svg"
     style="cursor:pointer;display:block;">
  <defs>
    <radialGradient id="fkBd" cx="38%" cy="30%" r="62%">
      <stop offset="0%" stop-color="#b2ede8"/><stop offset="35%" stop-color="#5ec4bb"/>
      <stop offset="70%" stop-color="#2a9d8f"/><stop offset="100%" stop-color="#1a6b60"/>
    </radialGradient>
    <radialGradient id="fkBl" cx="50%" cy="25%" r="55%">
      <stop offset="0%" stop-color="#f2fffe"/><stop offset="50%" stop-color="#caf2ee"/>
      <stop offset="100%" stop-color="#8dd8d0"/>
    </radialGradient>
    <radialGradient id="fkHd" cx="36%" cy="28%" r="60%">
      <stop offset="0%" stop-color="#b8ece7"/><stop offset="40%" stop-color="#4db8ae"/>
      <stop offset="100%" stop-color="#1f7a70"/>
    </radialGradient>
    <radialGradient id="fkEy" cx="30%" cy="25%" r="58%">
      <stop offset="0%" stop-color="#80d4f8"/><stop offset="30%" stop-color="#2196f3"/>
      <stop offset="65%" stop-color="#0d3b8a"/><stop offset="100%" stop-color="#050f2a"/>
    </radialGradient>
    <linearGradient id="fkWm" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#5eccc3" stop-opacity=".75"/>
      <stop offset="100%" stop-color="#145a52" stop-opacity=".45"/>
    </linearGradient>
    <linearGradient id="fkHr" x1="0%" y1="100%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="#1a9d8f"/><stop offset="100%" stop-color="#e8f8f6"/>
    </linearGradient>
    <radialGradient id="fkFr" cx="10%" cy="50%" r="80%">
      <stop offset="0%" stop-color="#fff9c4"/><stop offset="30%" stop-color="#ffcc02"/>
      <stop offset="60%" stop-color="#ff6d00"/><stop offset="100%" stop-color="#b71c1c"/>
    </radialGradient>
    <linearGradient id="fkCr" x1="0%" y1="100%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="#f57f17"/><stop offset="50%" stop-color="#ffd54f"/>
      <stop offset="100%" stop-color="#fff9c4"/>
    </linearGradient>
    <filter id="fkSf"><feGaussianBlur stdDeviation="1.2"/></filter>
    <filter id="fkSft"><feGaussianBlur stdDeviation="4"/></filter>
  </defs>
  <ellipse cx="120" cy="264" rx="55" ry="7" fill="rgba(0,0,0,.3)" filter="url(#fkSft)"/>
  <g id="fk-tail" style="transform-origin:90px 195px">
    <path d="M90 193 Q60 207 44 226 Q36 238 46 242 Q57 237 65 226 Q78 214 92 200Z" fill="url(#fkBd)"/>
    <path d="M46 242 Q35 238 38 230 Q44 234 46 242Z" fill="#5eccc3"/>
    <path d="M46 242 Q57 238 54 230 Q48 236 46 242Z" fill="#4ab8ae"/>
  </g>
  <g id="fk-wing-l" style="transform-origin:65px 125px">
    <line x1="65" y1="123" x2="16" y2="76" stroke="#1a6b5e" stroke-width="3.2" stroke-linecap="round"/>
    <line x1="65" y1="123" x2="20" y2="115" stroke="#1a6b5e" stroke-width="2.6" stroke-linecap="round"/>
    <line x1="65" y1="123" x2="12" y2="148" stroke="#1a6b5e" stroke-width="2.6" stroke-linecap="round"/>
    <line x1="65" y1="123" x2="26" y2="166" stroke="#1a6b5e" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M65 123 L16 76 L20 115 Z" fill="url(#fkWm)"/>
    <path d="M65 123 L20 115 L12 148 Z" fill="url(#fkWm)" opacity=".92"/>
    <path d="M65 123 L12 148 L26 166 Z" fill="url(#fkWm)" opacity=".84"/>
  </g>
  <g id="fk-wing-r" style="transform-origin:175px 125px">
    <line x1="175" y1="123" x2="224" y2="76" stroke="#1a6b5e" stroke-width="3.2" stroke-linecap="round"/>
    <line x1="175" y1="123" x2="220" y2="115" stroke="#1a6b5e" stroke-width="2.6" stroke-linecap="round"/>
    <line x1="175" y1="123" x2="228" y2="148" stroke="#1a6b5e" stroke-width="2.6" stroke-linecap="round"/>
    <line x1="175" y1="123" x2="214" y2="166" stroke="#1a6b5e" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M175 123 L224 76 L220 115 Z" fill="url(#fkWm)"/>
    <path d="M175 123 L220 115 L228 148 Z" fill="url(#fkWm)" opacity=".92"/>
    <path d="M175 123 L228 148 L214 166 Z" fill="url(#fkWm)" opacity=".84"/>
  </g>
  <ellipse cx="120" cy="178" rx="50" ry="62" fill="url(#fkBd)"/>
  <g opacity=".4" fill="none" stroke="#1a6b60" stroke-width="1.1">
    <path d="M88 149 Q94 143 100 149"/><path d="M112 143 Q118 137 124 143"/>
    <path d="M136 149 Q142 143 148 149"/>
  </g>
  <ellipse cx="120" cy="183" rx="30" ry="46" fill="url(#fkBl)" opacity=".9"/>
  <ellipse cx="74" cy="156" rx="20" ry="17" fill="url(#fkBd)"/>
  <ellipse cx="166" cy="156" rx="20" ry="17" fill="url(#fkBd)"/>
  <path d="M94 136 Q120 120 146 136 Q141 146 120 148 Q99 146 94 136Z" fill="url(#fkBd)"/>
  <path d="M110 125 Q108 113 113 107 Q116 116 114 125Z" fill="#4ecdc4"/>
  <path d="M120 123 Q119 111 124 105 Q127 114 125 123Z" fill="#4ecdc4"/>
  <path d="M130 125 Q130 113 135 108 Q137 117 135 125Z" fill="#4ecdc4"/>
  <path d="M120 52 C138 54 158 62 164 78 C170 94 162 108 154 116 C146 122 134 126 120 128
           C106 126 94 122 86 116 C78 108 70 94 76 78 C82 62 102 54 120 52Z" fill="url(#fkHd)"/>
  <path d="M90 60 Q84 36 90 22 Q95 32 96 48 Q96 56 90 60Z" fill="url(#fkHr)"/>
  <path d="M150 60 Q156 36 150 22 Q145 32 144 48 Q144 56 150 60Z" fill="url(#fkHr)"/>
  <path d="M104 50 Q103 41 106 37 Q108 43 106 50Z" fill="#4ecdc4" opacity=".85"/>
  <path d="M120 45 Q120 36 124 31 Q126 38 124 45Z" fill="#5eccc3"/>
  <path d="M136 50 Q138 41 141 38 Q142 44 140 50Z" fill="#3db5aa" opacity=".8"/>
  <path d="M120 108 C108 108 96 112 92 120 C89 127 94 134 102 138
           C108 141 114 142 120 142 C126 142 132 141 138 138
           C146 134 151 127 148 120 C144 112 132 108 120 108Z" fill="url(#fkHd)"/>
  <ellipse cx="111" cy="122" rx="4.5" ry="3.5" fill="rgba(20,90,84,.75)"/>
  <ellipse cx="129" cy="122" rx="4.5" ry="3.5" fill="rgba(20,90,84,.75)"/>
  <ellipse cx="94" cy="95" rx="17" ry="18" fill="white"/>
  <ellipse cx="146" cy="95" rx="17" ry="18" fill="white"/>
  <circle cx="94" cy="96" r="13" fill="url(#fkEy)"/>
  <circle cx="146" cy="96" r="13" fill="url(#fkEy)"/>
  <g id="fk-blink-l" style="transform-origin:94px 96px">
    <ellipse id="fk-pupil-l" cx="94" cy="97" rx="7.5" ry="8.5" fill="#04080f"/>
  </g>
  <g id="fk-blink-r" style="transform-origin:146px 96px">
    <ellipse id="fk-pupil-r" cx="146" cy="97" rx="7.5" ry="8.5" fill="#04080f"/>
  </g>
  <circle cx="98" cy="89" r="5.5" fill="white" opacity=".88"/>
  <circle cx="150" cy="89" r="5.5" fill="white" opacity=".88"/>
  <circle cx="90" cy="92" r="2.5" fill="white" opacity=".5"/>
  <circle cx="142" cy="92" r="2.5" fill="white" opacity=".5"/>
  <g id="fk-brows">
    <path id="fk-brow-l" d="M78 90 Q94 82 110 90" stroke="#1a6b60" stroke-width="2.4" fill="none" stroke-linecap="round"/>
    <path id="fk-brow-r" d="M130 90 Q146 82 162 90" stroke="#1a6b60" stroke-width="2.4" fill="none" stroke-linecap="round"/>
  </g>
  <ellipse cx="76" cy="106" rx="12" ry="8" fill="rgba(255,150,150,.28)" filter="url(#fkSf)"/>
  <ellipse cx="164" cy="106" rx="12" ry="8" fill="rgba(255,150,150,.28)" filter="url(#fkSf)"/>
  <g id="fk-mouth">
    <path id="fk-mouth-path" d="M105 136 Q120 144 135 136" stroke="#1a6b60" stroke-width="2.2" fill="none" stroke-linecap="round"/>
    <path d="M110 138 L111 144 L114 138" fill="white" opacity=".95"/>
    <path d="M117 140 L118 147 L121 140" fill="white" opacity=".95"/>
    <path d="M123 140 L124 147 L127 140" fill="white" opacity=".95"/>
  </g>
  <ellipse cx="68" cy="194" rx="14" ry="19" fill="url(#fkBd)" transform="rotate(-18,68,194)"/>
  <ellipse cx="172" cy="194" rx="14" ry="19" fill="url(#fkBd)" transform="rotate(18,172,194)"/>
  <ellipse cx="90" cy="244" rx="22" ry="13" fill="url(#fkBd)"/>
  <ellipse cx="150" cy="244" rx="22" ry="13" fill="url(#fkBd)"/>
  <g id="fk-fire" opacity="0">
    <path d="M120 126 Q98 118 88 132 Q98 124 120 136 Q142 124 152 132 Q142 118 120 126Z" fill="url(#fkFr)"/>
  </g>
  <g id="fk-sweat" opacity="0">
    <ellipse cx="165" cy="72" rx="5" ry="7" fill="#60cfff" opacity=".8"/>
    <ellipse cx="163" cy="78" rx="3" ry="4" fill="#60cfff" opacity=".6"/>
  </g>
  <g id="fk-stars" opacity="0">
    <text x="60" y="50" font-size="16" fill="#ffd700">★</text>
    <text x="165" y="60" font-size="12" fill="#ffd700">★</text>
    <text x="110" y="30" font-size="20" fill="#ffd700">★</text>
  </g>
  <g id="fk-zzz" opacity="0">
    <text x="155" y="55" font-size="14" fill="#a29bfe" font-weight="bold">z</text>
    <text x="168" y="42" font-size="11" fill="#a29bfe" font-weight="bold">z</text>
    <text x="178" y="32" font-size="8" fill="#a29bfe" font-weight="bold">z</text>
  </g>
  <g id="fk-think-dots" opacity="0">
    <circle cx="155" cy="50" r="4" fill="#b2ede8"/>
    <circle cx="167" cy="38" r="5.5" fill="#b2ede8"/>
    <circle cx="181" cy="24" r="7" fill="#b2ede8"/>
  </g>
  <g id="fk-crown" style="display:none">
    <path d="M88 56 L92 34 L106 50 L120 30 L134 50 L148 34 L152 56Z"
          fill="url(#fkCr)" stroke="#e65100" stroke-width="1.3" stroke-linejoin="round"/>
    <circle cx="106" cy="44" r="4.5" fill="#e53935" opacity=".92"/>
    <circle cx="120" cy="37" r="5.5" fill="#1e88e5" opacity=".92"/>
    <circle cx="134" cy="44" r="4.5" fill="#43a047" opacity=".92"/>
  </g>
</svg>`;

  // ═══════════════════════════════════════
  //  CSS
  // ═══════════════════════════════════════
  const CSS = `
  @keyframes fkFloat {
    0%,100%{transform:translateY(0) rotate(0)}
    25%{transform:translateY(-10px) rotate(-1.5deg)}
    75%{transform:translateY(-5px) rotate(1deg)}
  }
  @keyframes fkBounce {
    0%{transform:translateY(0) scaleY(1) scaleX(1)}
    15%{transform:translateY(-32px) scaleY(1.06) scaleX(.95)}
    35%{transform:translateY(-14px) scaleY(.94) scaleX(1.05)}
    55%{transform:translateY(-22px) scaleY(1.04) scaleX(.97)}
    75%{transform:translateY(-8px) scaleY(.97) scaleX(1.02)}
    100%{transform:translateY(0) scaleY(1) scaleX(1)}
  }
  @keyframes fkShake {
    0%,100%{transform:translateX(0) rotate(0)}
    15%{transform:translateX(-9px) rotate(-4deg)}
    30%{transform:translateX(9px) rotate(4deg)}
    45%{transform:translateX(-6px) rotate(-2deg)}
    60%{transform:translateX(6px) rotate(2deg)}
    75%{transform:translateX(-3px) rotate(-1deg)}
  }
  @keyframes fkWiggle {
    0%,100%{transform:rotate(0)}
    20%{transform:rotate(-14deg)}
    40%{transform:rotate(12deg)}
    60%{transform:rotate(-8deg)}
    80%{transform:rotate(6deg)}
  }
  @keyframes fkSpin {
    0%{transform:rotate(0) scale(1)}
    30%{transform:rotate(180deg) scale(1.15)}
    60%{transform:rotate(320deg) scale(0.9)}
    100%{transform:rotate(360deg) scale(1)}
  }
  @keyframes fkFly {
    0%{transform:translateY(0) translateX(0) rotate(0)}
    20%{transform:translateY(-40px) translateX(15px) rotate(8deg)}
    40%{transform:translateY(-25px) translateX(-10px) rotate(-5deg)}
    60%{transform:translateY(-50px) translateX(8px) rotate(10deg)}
    80%{transform:translateY(-20px) translateX(-5px) rotate(-3deg)}
    100%{transform:translateY(0) translateX(0) rotate(0)}
  }
  @keyframes fkNod {
    0%,100%{transform:rotate(0)}
    25%{transform:rotate(-8deg) translateY(-4px)}
    50%{transform:rotate(0) translateY(0)}
    75%{transform:rotate(-5deg) translateY(-2px)}
  }
  @keyframes fkSad {
    0%,100%{transform:translateY(0)}
    20%{transform:translateY(4px) rotate(3deg)}
    40%{transform:translateY(8px) rotate(-2deg)}
    60%{transform:translateY(5px) rotate(2deg)}
    80%{transform:translateY(2px)}
  }
  @keyframes fkTail {
    0%,100%{transform:rotate(0)}
    30%{transform:rotate(26deg)}
    70%{transform:rotate(-15deg)}
  }
  @keyframes fkWingL {
    0%,100%{transform:scaleX(1) rotate(0)}
    50%{transform:scaleX(.7) rotate(-10deg)}
  }
  @keyframes fkWingR {
    0%,100%{transform:scaleX(-1) rotate(0)}
    50%{transform:scaleX(-.7) rotate(10deg)}
  }
  @keyframes fkBlink {
    0%,82%,100%{transform:scaleY(1)}
    88%{transform:scaleY(.06)}
  }
  @keyframes fkGlow {
    0%,100%{opacity:.45;transform:scaleX(1)}
    50%{opacity:.8;transform:scaleX(1.25)}
  }
  @keyframes fkParticle {
    0%{transform:scale(0) rotate(0) translateY(0);opacity:1}
    100%{transform:scale(2.2) rotate(240deg) translateY(-72px);opacity:0}
  }
  @keyframes fkStarPop {
    0%{opacity:0;transform:scale(0)}
    40%{opacity:1;transform:scale(1.3)}
    70%{transform:scale(.9)}
    100%{opacity:1;transform:scale(1)}
  }
  @keyframes fkThinkBob {
    0%,100%{transform:translateY(0)}
    50%{transform:translateY(-3px)}
  }
  @keyframes fkSweatDrop {
    0%{transform:translateY(0);opacity:.8}
    100%{transform:translateY(20px);opacity:0}
  }
  @keyframes fkHeartbeat {
    0%,100%{transform:scale(1)}
    14%{transform:scale(1.08)}
    28%{transform:scale(1)}
    42%{transform:scale(1.05)}
  }
  @keyframes fkBubbleIn {
    0%{opacity:0;transform:translateY(8px) scale(.9)}
    100%{opacity:1;transform:translateY(0) scale(1)}
  }
  @keyframes fkZzz {
    0%{opacity:0;transform:translateY(0)}
    20%{opacity:1}
    80%{opacity:.6}
    100%{opacity:0;transform:translateY(-18px)}
  }

  #fairik-widget {
    position:fixed; z-index:9999;
    display:flex; flex-direction:column; align-items:flex-end; gap:6px;
    user-select:none; font-family:'JetBrains Mono',monospace;
    transition: none;
    pointer-events: auto;
  }
  #fairik-widget.fk-flying {
    pointer-events: none;
  }
  #fairik-widget.fk-moving {
    transition: left 1.8s cubic-bezier(0.25,0.46,0.45,0.94),
                bottom 1.8s cubic-bezier(0.25,0.46,0.45,0.94);
  }
  #fk-bubble {
    background:rgba(255,255,255,.97); color:#1a1a2e;
    padding:9px 15px; border-radius:18px 18px 18px 4px;
    font-size:12px; font-weight:600; line-height:1.45;
    max-width:210px; box-shadow:0 8px 28px rgba(0,0,0,.28);
    opacity:0; transform:translateY(6px) scale(.94);
    transition:opacity .3s ease,transform .3s ease;
    pointer-events:none; position:relative;
  }
  #fk-bubble.show{opacity:1;transform:translateY(0) scale(1)}
  #fk-bubble::before{
    content:''; position:absolute; bottom:-8px; right:16px;
    border:5px solid transparent; border-top-color:rgba(255,255,255,.97);
  }
  #fk-body{position:relative;display:flex;flex-direction:column;align-items:center;cursor:pointer}
  #fk-close{
    position:absolute; top:-6px; right:-6px;
    width:18px; height:18px; border-radius:50%;
    background:rgba(0,0,0,.5); color:rgba(255,255,255,.6);
    border:none; cursor:pointer; font-size:9px;
    display:flex; align-items:center; justify-content:center;
    opacity:0; transition:opacity .2s;
    font-family:inherit; line-height:1;
  }
  #fk-body:hover #fk-close { opacity:1; }
  #fk-close:hover { background:rgba(220,50,50,.7); color:#fff; }
  #fk-mini{
    position:fixed;bottom:22px;right:22px;z-index:9999;
    width:54px;height:54px;border-radius:50%;
    background:rgba(18,16,42,.92);border:2px solid rgba(78,205,196,.4);
    cursor:pointer;display:none;align-items:center;justify-content:center;
    font-size:28px;box-shadow:0 4px 22px rgba(0,0,0,.38);
    transition:transform .2s,box-shadow .2s;
  }
  #fk-mini:hover{transform:scale(1.1);box-shadow:0 6px 28px rgba(78,205,196,.35)}
  .fk-p{position:fixed;pointer-events:none;z-index:10000;animation:fkParticle 1.1s ease forwards}
  #fk-emotion-overlay{
    position:absolute;top:-8px;right:-12px;font-size:18px;
    opacity:0;transition:opacity .3s;pointer-events:none;
  }
  `;

  // ═══════════════════════════════════════
  //  ФИЗИКА — состояние
  // ═══════════════════════════════════════
  const STORAGE_KEY = 'fk_v3';
  let state = { xp:0, level:1, streak:0, minimized:false, name:'Ученик', correctStreak:0 };
  function loadState() { try { Object.assign(state, JSON.parse(localStorage.getItem(STORAGE_KEY)||'{}')); } catch(e){} }
  function saveState() { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch(e){} }
  function xpToLevel(xp) { for(let i=XP_PER_LEVEL.length-1;i>=1;i--) if(xp>=XP_PER_LEVEL[i]) return i; return 1; }
  function xpPct() { const l=state.level,lo=XP_PER_LEVEL[l]||0,hi=XP_PER_LEVEL[l+1]||lo+500; return Math.min(100,Math.round((state.xp-lo)/(hi-lo)*100)); }

  // ═══════════════════════════════════════
  //  ФИЗИКА — анимационный движок
  // ═══════════════════════════════════════
  // ── Позиции обитания (% от viewport) ──
  const SPOTS = [
    { right: 22, bottom: 22,  name: 'corner-br' },  // правый нижний (дом)
    { right: 22, bottom: 45,  name: 'corner-br-up' },
    { left: 22,  bottom: 22,  name: 'corner-bl' },   // левый нижний
    { left: 22,  bottom: 45,  name: 'corner-bl-up' },
    { right: 22, bottom: 70,  name: 'mid-right' },   // правая середина
    { left: 22,  bottom: 70,  name: 'mid-left' },    // левая середина
  ];
  let currentSpot = 0; // индекс текущего места

  let phys = {
    tailAngle: 0, tailV: 0,
    wingPhase: 0,
    mode: 'float',
    lastFrame: 0,
    // Позиция
    x: null, y: null,     // текущая позиция (px от left/bottom)
    tx: null, ty: null,   // целевая позиция
    isFlying: false,
    flyProgress: 0,
    flyDuration: 0,
    flyStartX: 0, flyStartY: 0,
    flyStartTime: 0,
    // Дрейф (лёгкое покачивание на месте)
    driftX: 0, driftY: 0,
    driftPhase: 0,
  };

  function getSpotPx(spot) {
    const W = window.innerWidth, H = window.innerHeight;
    const w = 140, h = 160; // размер виджета
    const x = spot.left  !== undefined ? spot.left  : W - spot.right  - w;
    const y = spot.bottom !== undefined ? spot.bottom : spot.bottom;
    return { x: Math.max(8, Math.min(W-w-8, x)), y: Math.max(8, y) };
  }

  function applyPosition(x, y) {
    if (!el.widget) return;
    el.widget.style.left   = x + 'px';
    el.widget.style.bottom = y + 'px';
    el.widget.style.right  = 'unset';
    el.widget.style.top    = 'unset';
  }

  let animFrame = null;
  let el = {};
  let bubbleTimer = null, idleTimer = null;
  let isThinking = false;
  let currentEmotion = 'neutral'; // neutral|happy|sad|excited|sleepy|thinking

  // ── Easing ──
  function easeInOutCubic(t) { return t<.5 ? 4*t*t*t : 1-Math.pow(-2*t+2,3)/2; }
  function easeOutBack(t) { const c1=1.70158,c3=c1+1; return 1+c3*Math.pow(t-1,3)+c1*Math.pow(t-1,2); }

  function physLoop(ts) {
    animFrame = requestAnimationFrame(physLoop);
    const dt = Math.min((ts - phys.lastFrame) / 1000, 0.05);
    phys.lastFrame = ts;

    // ── Инициализация позиции при первом кадре ──
    if (phys.x === null) {
      const W = window.innerWidth;
      phys.x = W - 160;
      phys.y = 22;
      applyPosition(phys.x, phys.y);
    }

    // ── Полёт к цели ──
    if (phys.isFlying && phys.tx !== null) {
      const elapsed = ts - phys.flyStartTime;
      const t = Math.min(1, elapsed / phys.flyDuration);
      const ease = easeInOutCubic(t);

      phys.x = phys.flyStartX + (phys.tx - phys.flyStartX) * ease;
      phys.y = phys.flyStartY + (phys.ty - phys.flyStartY) * ease;

      // Дуга — подъём в середине пути
      const arc = Math.sin(t * Math.PI) * 60;
      const displayY = phys.y + arc;

      // Наклон по направлению
      const dx = phys.tx - phys.flyStartX;
      const tilt = dx > 0 ? Math.min(18, dx * 0.04) : Math.max(-18, dx * 0.04);
      const body = document.getElementById('fk-body');
      if (body) body.style.transform = `rotate(${tilt * Math.sin(t * Math.PI)}deg)`;

      applyPosition(phys.x, displayY);

      if (t >= 1) {
        phys.isFlying = false;
        phys.x = phys.tx; phys.y = phys.ty;
        applyPosition(phys.x, phys.y);
        if (el.widget) el.widget.classList.remove('fk-flying');
        const body2 = document.getElementById('fk-body');
        if (body2) body2.style.transform = '';
        setEmotion('happy');
        bubble('Вот я где! 🐉', 2000);
        setTimeout(() => setEmotion('neutral'), 2200);
      }
    } else {
      // ── Дрейф на месте (плавное покачивание) ──
      phys.driftPhase += dt * 0.8;
      phys.driftX = Math.sin(phys.driftPhase * 0.7) * 3;
      phys.driftY = Math.sin(phys.driftPhase) * 4;
      applyPosition(phys.x + phys.driftX, phys.y + phys.driftY);
    }

    // ── Хвост ──
    phys.tailAngle += phys.tailV * dt;
    phys.tailV += (-phys.tailAngle * 8 - phys.tailV * 1.5) * dt * 6;
    phys.tailV += (Math.sin(ts * 0.002) * 0.3) * dt * 10;
    if (phys.isFlying) phys.tailV += 2 * dt * 20; // хвост машет активнее в полёте
    const tail = document.getElementById('fk-tail');
    if (tail) tail.style.transform = `rotate(${phys.tailAngle}deg)`;

    // ── Крылья — активнее в полёте ──
    phys.wingPhase = ts * 0.003;
    const wAmp = phys.isFlying ? 0.45 : 0.15;
    const wSpeed = phys.isFlying ? 3.5 : 1;
    const wl = document.getElementById('fk-wing-l');
    const wr = document.getElementById('fk-wing-r');
    const wPhase = ts * 0.003 * wSpeed;
    if (wl) wl.style.transform = `scaleX(${1 - Math.abs(Math.sin(wPhase)) * wAmp}) rotate(${Math.sin(wPhase) * (phys.isFlying?-18:-5)}deg)`;
    if (wr) wr.style.transform = `scaleX(${-(1 - Math.abs(Math.sin(wPhase)) * wAmp)}) rotate(${Math.sin(wPhase) * (phys.isFlying?18:5)}deg)`;

    // ── Моргание ──
    const blinkT = (ts * 0.001) % 5;
    const blinkScale = blinkT > 4.2 && blinkT < 4.6 ? Math.max(0.06, 1 - (blinkT-4.2)/0.2) : 1;
    ['fk-blink-l','fk-blink-r'].forEach(id => {
      const b = document.getElementById(id);
      if (b) b.style.transform = `scaleY(${blinkScale})`;
    });

    updateBrows();
  }

  // ── Полёт в конкретное место ──
  function flyTo(spotIdx, onDone) {
    if (phys.isFlying) return;
    const spot = SPOTS[spotIdx % SPOTS.length];
    const pos  = getSpotPx(spot);
    currentSpot = spotIdx % SPOTS.length;

    phys.isFlying   = true;
    phys.flyStartX  = phys.x + phys.driftX;
    phys.flyStartY  = phys.y + phys.driftY;
    phys.tx         = pos.x;
    phys.ty         = pos.y;
    phys.flyDuration = 1200 + Math.abs(pos.x - phys.x) * 0.8;
    phys.flyStartTime = performance.now();

    if (el.widget) el.widget.classList.add('fk-flying');
    setEmotion('excited');

    // Активные крылья
    phys.tailV += 8;
    if (onDone) setTimeout(onDone, phys.flyDuration + 200);
  }

  // ── Авто-перемещение ──
  let wanderTimer = null;
  function scheduleWander() {
    clearTimeout(wanderTimer);
    // Случайно от 45 до 120 секунд
    const delay = 45000 + Math.random() * 75000;
    wanderTimer = setTimeout(() => {
      if (!state.minimized && !phys.isFlying) {
        const wanderPhrases = [
          'Летим! 🐉', 'Меняю позицию! ✨',
          'Хочу посмотреть отсюда! 🌟',
          'Мне там лучше видно! 👀',
          'Немного полетаем? 🐉',
        ];
        // Выбираем случайный спот (не текущий)
        let next = Math.floor(Math.random() * SPOTS.length);
        if (next === currentSpot) next = (next + 1) % SPOTS.length;
        bubble(wanderPhrases[Math.floor(Math.random() * wanderPhrases.length)], 2500);
        setTimeout(() => flyTo(next), 800);
      }
      scheduleWander();
    }, delay);
  }

  function updateBrows() {
    const bl = document.getElementById('fk-brow-l');
    const br = document.getElementById('fk-brow-r');
    if (!bl || !br) return;
    const em = {
      neutral:  { l:'M78 90 Q94 82 110 90',  r:'M130 90 Q146 82 162 90' },
      happy:    { l:'M78 86 Q94 80 110 86',  r:'M130 86 Q146 80 162 86' },
      sad:      { l:'M78 86 Q94 94 110 88',  r:'M130 88 Q146 94 162 86' },
      excited:  { l:'M76 84 Q94 76 110 84',  r:'M130 84 Q146 76 164 84' },
      angry:    { l:'M78 88 Q94 96 110 92',  r:'M130 92 Q146 96 162 88' },
      thinking: { l:'M78 90 Q94 84 107 87',  r:'M133 87 Q146 84 162 90' },
      sleepy:   { l:'M80 92 Q94 88 108 92',  r:'M132 92 Q146 88 160 92' },
    };
    const paths = em[currentEmotion] || em.neutral;
    bl.setAttribute('d', paths.l);
    br.setAttribute('d', paths.r);
  }

  function setEmotion(name) {
    currentEmotion = name;
    const svg = document.getElementById('fk-svg');
    if (!svg) return;

    // Рот
    const mouthPaths = {
      neutral:  'M105 136 Q120 144 135 136',
      happy:    'M103 134 Q120 148 137 134',
      sad:      'M105 144 Q120 136 135 144',
      excited:  'M100 132 Q120 150 140 132',
      thinking: 'M108 139 Q120 142 132 139',
      sleepy:   'M107 140 Q120 143 133 140',
      angry:    'M106 140 Q120 137 134 140',
    };
    const mp = document.getElementById('fk-mouth-path');
    if (mp) mp.setAttribute('d', mouthPaths[name] || mouthPaths.neutral);

    // Румянец
    const blush = svg.querySelectorAll('ellipse[filter]');
    blush.forEach(b => { b.style.opacity = (name==='happy'||name==='excited') ? '0.5' : name==='sad' ? '0.15' : '0.28'; });

    // Специальные элементы
    const stars = document.getElementById('fk-stars');
    const sweat = document.getElementById('fk-sweat');
    const zzz   = document.getElementById('fk-zzz');
    const think = document.getElementById('fk-think-dots');
    if (stars) stars.style.opacity = name==='excited' ? '1' : '0';
    if (sweat) sweat.style.opacity = name==='thinking'||name==='angry' ? '0.9' : '0';
    if (zzz)   { zzz.style.opacity = name==='sleepy' ? '1' : '0'; if(name==='sleepy') animZzz(zzz); }
    if (think) { think.style.opacity = name==='thinking' ? '1' : '0'; }

    updateBrows();
  }

  function animZzz(g) {
    if (!g || currentEmotion !== 'sleepy') return;
    let op = 0, dir = 1;
    const iv = setInterval(() => {
      if (currentEmotion !== 'sleepy') { clearInterval(iv); return; }
      op += dir * 0.05;
      if (op > 1) { op = 1; dir = -1; }
      if (op < 0) { op = 0; dir = 1; }
      g.style.opacity = op;
    }, 40);
  }

  // ═══════════════════════════════════════
  //  PLAY ANIMATION on SVG wrapper
  // ═══════════════════════════════════════
  let animTimeout = null;
  function playAnim(name, dur = 900) {
    const body = document.getElementById('fk-body');
    if (!body) return;
    clearTimeout(animTimeout);

    const map = {
      bounce:  'fkBounce .8s ease forwards',
      shake:   'fkShake .5s ease 2 forwards',
      wiggle:  'fkWiggle .5s ease 2 forwards',
      spin:    'fkSpin .7s ease forwards',
      fly:     'fkFly 1.6s ease forwards',
      nod:     'fkNod .6s ease 3 forwards',
      sad:     'fkSad .6s ease forwards',
      heartbeat: 'fkHeartbeat .5s ease 3 forwards',
    };
    body.style.animation = 'none';
    void body.offsetWidth;
    body.style.animation = map[name] || map.bounce;
    animTimeout = setTimeout(() => { if (body) body.style.animation = ''; }, dur + 100);
  }

  // ═══════════════════════════════════════
  //  PARTICLES
  // ═══════════════════════════════════════
  function particles(emojis, count = 6) {
    const svg = document.getElementById('fk-svg');
    if (!svg) return;
    const r = svg.getBoundingClientRect();
    for (let i = 0; i < count; i++) {
      const p = document.createElement('div');
      p.className = 'fk-p';
      p.style.fontSize = (12 + Math.random() * 14) + 'px';
      p.style.left = (r.left + 10 + Math.random() * (r.width - 20)) + 'px';
      p.style.top  = (r.top  + 5  + Math.random() * (r.height - 10)) + 'px';
      p.style.animationDelay = (Math.random() * 0.4) + 's';
      p.textContent = emojis[Math.floor(Math.random() * emojis.length)];
      document.body.appendChild(p);
      setTimeout(() => p.remove(), 1600);
    }
  }

  // ═══════════════════════════════════════
  //  BUBBLE
  // ═══════════════════════════════════════
  function bubble(text, dur = 3800) {
    clearTimeout(bubbleTimer);
    el.bubble.textContent = text;
    el.bubble.classList.add('show');
    bubbleTimer = setTimeout(() => el.bubble.classList.remove('show'), dur);
  }

  // ═══════════════════════════════════════
  //  IDLE LOGIC — умная система
  // ═══════════════════════════════════════
  let idleCount = 0;
  function resetIdle() {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      idleCount++;
      const h = new Date().getHours();
      if (state.minimized) { resetIdle(); return; }
      if (h >= 22 || h < 6) {
        setEmotion('sleepy');
        bubble(rand(P.night));
      } else if (idleCount % 2 === 0 && !phys.isFlying) {
        // Каждые 2 idle — летит на новое место
        let next = Math.floor(Math.random() * SPOTS.length);
        if (next === currentSpot) next = (next + 1) % SPOTS.length;
        bubble(rand(P.idle), 2500);
        setTimeout(() => flyTo(next), 1000);
      } else {
        setEmotion('neutral');
        bubble(rand(P.idle));
      }
      setTimeout(() => { if(currentEmotion !== 'sleepy') setEmotion('neutral'); }, 4000);
      resetIdle();
    }, 120_000);
  }

  // ═══════════════════════════════════════
  //  BUILD DOM
  // ═══════════════════════════════════════
  function build() {
    const style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    el.mini = document.createElement('div');
    el.mini.id = 'fk-mini';
    el.mini.innerHTML = '🐉';
    el.mini.addEventListener('click', () => API.show());
    document.body.appendChild(el.mini);

    el.widget = document.createElement('div');
    el.widget.id = 'fairik-widget';

    el.bubble = document.createElement('div');
    el.bubble.id = 'fk-bubble';

    el.body = document.createElement('div');
    el.body.id = 'fk-body';
    el.body.innerHTML = SVG;

    el.closeBtn = document.createElement('button');
    el.closeBtn.id = 'fk-close';
    el.closeBtn.textContent = '✕';
    el.closeBtn.title = 'Скрыть Файрика';
    el.closeBtn.addEventListener('click', e => { e.stopPropagation(); API.hide(); });
    el.body.appendChild(el.closeBtn);

    // Клик по Файрику
    el.body.addEventListener('click', (e) => {
      if (e.detail >= 2) return; // обработаем в dblclick
      const h = new Date().getHours();
      if (h >= 22 || h < 6) {
        setEmotion('sleepy'); playAnim('nod'); bubble(rand(P.night));
      } else {
        // Иногда при клике летит
        if (Math.random() < 0.3 && !phys.isFlying) {
          let next = Math.floor(Math.random() * SPOTS.length);
          if (next === currentSpot) next = (next + 1) % SPOTS.length;
          bubble('Смотри как я умею! ✨', 2000);
          setTimeout(() => flyTo(next), 600);
        } else {
          const anims = ['bounce','wiggle','nod'];
          playAnim(rand(anims));
          setEmotion('happy');
          bubble(rand(P.idle));
          setTimeout(() => setEmotion('neutral'), 2000);
        }
      }
    });

    // Двойной клик — летит домой
    el.body.addEventListener('dblclick', () => {
      if (!phys.isFlying) {
        if (currentSpot === 0) {
          // Уже дома — fire!
          const fire = document.getElementById('fk-fire');
          if (fire) {
            setEmotion('excited'); fire.style.opacity = '1';
            playAnim('wiggle'); particles(['🔥','💥','⚡'], 8);
            bubble('ФАЙРИК РАСКОЧЕГАРИЛСЯ! 🔥');
            setTimeout(() => { fire.style.opacity = '0'; setEmotion('neutral'); }, 1200);
          }
        } else {
          flyTo(0);
          bubble('Летим домой! 🏠', 1800);
        }
      }
      return;
    });

    // Тройной клик — огонь!
    el.body.addEventListener('click', (ee) => {
      if (ee.detail !== 3) return;
      const fire = document.getElementById('fk-fire');
      if (fire) {
        setEmotion('excited');
        fire.style.opacity = '1';
        fire.style.transition = 'opacity .15s';
        playAnim('wiggle');
        particles(['🔥','💥','⚡'], 8);
        bubble('ФАЙРИК РАСКОЧЕГАРИЛСЯ! 🔥');
        setTimeout(() => { fire.style.opacity = '0'; setEmotion('neutral'); }, 1200);
      }
    });

    el.widget.appendChild(el.bubble);
    el.widget.appendChild(el.body);
    document.body.appendChild(el.widget);

    // Слежение глазами
    document.addEventListener('mousemove', e => {
      const svg = document.getElementById('fk-svg');
      if (!svg) return;
      const r = svg.getBoundingClientRect();
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      const dx = Math.max(-5, Math.min(5, (e.clientX - cx) / 28));
      const dy = Math.max(-4, Math.min(4, (e.clientY - cy) / 32));
      [['fk-pupil-l',94,97],['fk-pupil-r',146,97]].forEach(([id,bx,by]) => {
        const p = document.getElementById(id);
        if (p) { p.setAttribute('cx', bx + dx * 0.55); p.setAttribute('cy', by + dy * 0.45); }
      });
    });
  }

  // ═══════════════════════════════════════
  //  RENDER
  // ═══════════════════════════════════════
  function render() {
    const cfg = LEVELS[Math.min(state.level, LEVELS.length-1)] || LEVELS[1];
    const svg = document.getElementById('fk-svg');
    if (!svg) return;
    const skinCss = (window._fairikSkinCss || '');
    const baseFilter = `drop-shadow(0 10px 22px ${cfg.glow}44) drop-shadow(0 3px 8px rgba(0,0,0,.5))`;
    svg.style.filter = skinCss ? `${skinCss} ${baseFilter}` : baseFilter;
    // glow/info bar removed
    const crown = document.getElementById('fk-crown');
    if (crown) crown.style.display = cfg.crown ? 'block' : 'none';
    // xp bar removed
  }

  // ═══════════════════════════════════════
  //  ПУБЛИЧНОЕ API
  // ═══════════════════════════════════════
  const API = {

    say(text, animName = null) {
      bubble(text);
      if (animName) playAnim(animName);
      resetIdle();
    },

    happy(msg) {
      state.correctStreak = (state.correctStreak || 0) + 1;
      setEmotion('happy');
      playAnim('bounce');
      particles(['⭐','✨','🎉','🌟'], 8);
      const text = msg || (state.correctStreak >= 3
        ? rand(P.correct_streak)(state.correctStreak)
        : rand(P.happy));
      bubble(text, 3500);
      setTimeout(() => setEmotion('neutral'), 3000);
      resetIdle();
    },

    sad(msg) {
      state.correctStreak = 0;
      setEmotion('sad');
      playAnim('shake', 1000);
      particles(['💪','🔄','📚'], 4);
      bubble(msg || rand(P.sad), 4000);
      setTimeout(() => setEmotion('neutral'), 4000);
      resetIdle();
    },

    celebrate() {
      setEmotion('excited');
      particles(['🎉','⭐','✨','🌟','🔥','🏆'], 14);
      bubble(rand(P.levelup), 4500);
      // Летит на случайное место и возвращается
      if (!phys.isFlying) {
        const next = (currentSpot + 2) % SPOTS.length;
        flyTo(next, () => {
          setTimeout(() => flyTo(0), 2000); // возврат домой
        });
      } else {
        playAnim('spin', 700);
      }
      setTimeout(() => setEmotion('neutral'), 5000);
    },

    streak(days) {
      setEmotion('excited');
      playAnim('spin', 700);
      particles(['🔥','💥','⚡','🌟'], 9);
      const fn = rand(P.streak);
      bubble(fn(days), 4000);
      setTimeout(() => setEmotion('neutral'), 3500);
    },

    addXP(amount = 10) {
      const prev = state.level;
      state.xp = (state.xp || 0) + amount;
      state.level = xpToLevel(state.xp);
      saveState();
      if (state.level > prev) {
        this.celebrate();
        setTimeout(() => render(), 800);
      } else {
        setEmotion('happy');
        playAnim('nod', 600);
        bubble(rand(P.xp)(amount));
        particles(['⭐'], 4);
        setTimeout(() => setEmotion('neutral'), 2000);
        render();
      }
    },

    setLevel(n) {
      state.level = Math.max(1, Math.min(5, n));
      state.xp = XP_PER_LEVEL[state.level];
      saveState(); render();
    },

    think() {
      isThinking = true;
      setEmotion('thinking');
      playAnim('nod', 1200);
      bubble(rand(P.thinking), 5000);
    },

    doneThinking() {
      isThinking = false;
      setEmotion('neutral');
      el.bubble.classList.remove('show');
    },

    fire() {
      const f = document.getElementById('fk-fire');
      if (f) {
        setEmotion('excited');
        f.style.opacity = '1';
        playAnim('wiggle');
        particles(['🔥','💥'], 6);
        bubble('Горим учёбой! 🔥');
        setTimeout(() => { f.style.opacity = '0'; setEmotion('neutral'); }, 1300);
      }
    },

    quizStart() {
      setEmotion('excited');
      playAnim('bounce');
      bubble(rand(P.quiz_start));
      particles(['🎯','⚡'], 5);
      setTimeout(() => setEmotion('neutral'), 2500);
    },

    encourage() {
      setEmotion('happy');
      playAnim('nod');
      bubble(rand(P.encourage));
      setTimeout(() => setEmotion('neutral'), 2500);
    },

    hide() {
      state.minimized = true; saveState();
      el.widget.style.display = 'none';
      el.mini.style.display = 'flex';
    },

    show() {
      state.minimized = false; saveState();
      el.widget.style.display = 'flex';
      el.mini.style.display = 'none';
      // Инициализируем позицию если ещё нет
      if (phys.x === null) {
        phys.x = window.innerWidth - 160;
        phys.y = 22;
        applyPosition(phys.x, phys.y);
      }
      setEmotion('happy');
      playAnim('bounce');
      const greetFn = rand(P.greeting);
      bubble(greetFn(state.name));
      setTimeout(() => setEmotion('neutral'), 3000);
    },

    async sync() {
      try {
        const res = await fetch('/api/fairik', { credentials:'include' });
        if (!res.ok) return;
        const d = await res.json();
        const prev = state.level;
        state.xp     = d.xp     ?? state.xp;
        state.level  = d.level  ?? state.level;
        state.streak = d.streak ?? state.streak;
        state.name   = d.name   ?? state.name;
        if (d.skin_css !== undefined) window._fairikSkinCss = d.skin_css;
        saveState(); render();
        const h = new Date().getHours();
        if (h >= 22 || h < 6) {
          setEmotion('sleepy'); bubble(rand(P.night));
        } else if (h >= 6 && h < 10) {
          setEmotion('happy'); playAnim('bounce'); bubble(rand(P.morning));
        } else if ((d.streak || 0) >= 3) {
          setEmotion('excited'); playAnim('bounce');
          const fn = rand(P.streak); bubble(fn(d.streak));
        } else {
          setEmotion('happy'); playAnim('nod');
          const greetFn = rand(P.greeting); bubble(greetFn(state.name));
        }
        setTimeout(() => setEmotion('neutral'), 4000);

        // Напоминание о повторении
        try {
          const rem = await fetch('/api/memory/daily_reminder', {credentials:'include'});
          const rd  = await rem.json();
          if (rd.has_reminder) {
            setTimeout(() => {
              setEmotion('thinking');
              bubble(rd.message, 5000);
              setTimeout(() => setEmotion('neutral'), 5500);
            }, 5000);
          }
        } catch(e) {}

      } catch(e) {}
    },
  };

  // ═══════════════════════════════════════
  //  INIT
  // ═══════════════════════════════════════
  function init() {
    loadState();
    build();
    render();
    if (state.minimized) {
      el.widget.style.display = 'none';
      el.mini.style.display = 'flex';
    }
    // Запуск физики
    phys.lastFrame = performance.now();
    physLoop(phys.lastFrame);
    API.sync();
    resetIdle();
    scheduleWander();
    window.Fairik = API;
    // Публичный метод для полёта
    API.flyTo = (idx) => flyTo(idx !== undefined ? idx : Math.floor(Math.random() * SPOTS.length));
    API.goHome = () => flyTo(0);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();