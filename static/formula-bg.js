/**
 * bg.js — анимированный фон SubjectHelper
 * Плавающие частицы + формулы/символы которые появляются и исчезают
 * Подключи в конце <body> на всех страницах
 */

(function () {
  // ── Формулы и символы по всем предметам ─────────────────────────────────
  const SYMBOLS = [
    // Математика
    "x² + y²", "∫f(x)dx", "√(a²+b²)", "π ≈ 3.14",
    "sin²α + cos²α = 1", "lim x→∞", "∑nᵢ", "ax² + bx + c = 0",
    "dy/dx", "log₂n", "n!", "∞",
    // Физика
    "F = ma", "E = mc²", "P = mv", "v = λf",
    "ΔE = hν", "F = kq₁q₂/r²", "U = IR", "W = Fs",
    // Химия
    "H₂O", "CO₂", "NaCl", "H₂SO₄",
    "CH₄", "C₆H₁₂O₆", "NH₃", "O₂",
    // Русский / литература
    "А•Б•В", "∃", "∀x", "∅",
    // Информатика
    "01010", "if/else", "O(n²)", "def f():",
    "True/False", "HTML", "CSS", "</>", "01101",
    // Биология
    "DNA", "ATP", "pH=7", "RNA",
    // Общие символы
    "≠", "≈", "≤", "≥", "∈", "∩", "∪", "→", "⇒",
  ];

  // Цвета — зелёный/голубой/фиолетовый в тон теме
  const COLORS = [
    "rgba(0,255,136,",    // accent green
    "rgba(77,159,255,",   // blue
    "rgba(176,106,255,",  // purple
    "rgba(0,255,204,",    // teal
  ];

  const canvas  = document.createElement("canvas");
  canvas.id     = "bg-canvas";
  canvas.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:0;";
  document.body.prepend(canvas);

  const ctx = canvas.getContext("2d");
  let W, H, items = [];

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener("resize", resize);

  // ── Элемент фона (частица или формула) ──────────────────────────────────
  function makeItem() {
    const isFormula = Math.random() > 0.45;   // 55% формулы, 45% точки
    const color     = COLORS[Math.floor(Math.random() * COLORS.length)];
    const alpha     = Math.random() * 0.18 + 0.04;  // очень прозрачно

    if (isFormula) {
      return {
        type:    "formula",
        text:    SYMBOLS[Math.floor(Math.random() * SYMBOLS.length)],
        x:       Math.random() * W,
        y:       H + 40,
        size:    Math.random() * 10 + 10,       // 10–20px
        speed:   Math.random() * 0.3 + 0.12,
        alpha:   0,
        targetA: alpha,
        fade:    "in",
        color:   color,
        drift:   (Math.random() - 0.5) * 0.3,  // горизонтальный дрейф
        delay:   Math.random() * 8000,
        born:    Date.now(),
      };
    } else {
      return {
        type:    "dot",
        x:       Math.random() * W,
        y:       H + 10,
        r:       Math.random() * 2.5 + 1,
        speed:   Math.random() * 0.5 + 0.2,
        alpha:   0,
        targetA: alpha * 3,
        fade:    "in",
        color:   color,
        drift:   (Math.random() - 0.5) * 0.2,
        delay:   Math.random() * 6000,
        born:    Date.now(),
      };
    }
  }

  // Инициализируем 80 элементов с разными стартовыми позициями
  for (let i = 0; i < 80; i++) {
    const item = makeItem();
    // Распределяем по всей высоте для начала
    item.y     = Math.random() * H;
    item.born  = Date.now() - Math.random() * 30000;
    item.alpha = Math.random() * item.targetA;
    item.fade  = Math.random() > 0.5 ? "in" : "out";
    items.push(item);
  }

  // ── Анимация ─────────────────────────────────────────────────────────────
  function draw() {
    ctx.clearRect(0, 0, W, H);

    const now = Date.now();

    items.forEach((item, idx) => {
      // Пропускаем пока не истёк delay
      if (now - item.born < item.delay) return;

      // Движение вверх + дрейф
      item.y     -= item.speed;
      item.x     += item.drift;

      // Плавное появление / исчезновение
      if (item.fade === "in") {
        item.alpha = Math.min(item.alpha + 0.002, item.targetA);
        if (item.alpha >= item.targetA) item.fade = "hold";
      } else if (item.fade === "hold") {
        // Держим пока не поднялись достаточно
        if (item.y < H * 0.4) item.fade = "out";
      } else {
        item.alpha = Math.max(item.alpha - 0.003, 0);
      }

      // Если вышли за экран или исчезли — перезапускаем
      if (item.y < -60 || item.alpha <= 0 && item.fade === "out") {
        items[idx] = makeItem();
        return;
      }

      ctx.save();
      ctx.globalAlpha = Math.max(0, item.alpha);

      if (item.type === "formula") {
        ctx.font         = `${item.size}px 'JetBrains Mono', monospace`;
        ctx.fillStyle    = item.color + "1)";
        ctx.textBaseline = "middle";
        ctx.fillText(item.text, item.x, item.y);
      } else {
        ctx.beginPath();
        ctx.arc(item.x, item.y, item.r, 0, Math.PI * 2);
        ctx.fillStyle = item.color + "1)";
        ctx.fill();
        // Небольшое свечение вокруг точки
        ctx.shadowBlur  = 8;
        ctx.shadowColor = item.color + "0.8)";
        ctx.fill();
      }

      ctx.restore();
    });

    requestAnimationFrame(draw);
  }

  // Запускаем после загрузки страницы
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", draw);
  } else {
    draw();
  }
})();