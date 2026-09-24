/* ===========================================================
   Контурные иконки панели — как на макете.

   Свой набор в коде, без внешних шрифтов: в Telegram на слабом
   интернете шрифты иконок мигают или не грузятся вовсе.
   Все иконки 24×24, линия 2px, цвет — от текста (currentColor).

   Использование:  M.icon("shield")  или  M.icon("shield", 18)
   В разметке:     <span data-icon="home"></span> — заполнится сам.
   =========================================================== */

(function () {
  var M = window.Mara;

  var P = {
    home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20h5v-6h4v6h5V9.5"/>',
    shield: '<path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6l-8-3z"/>',
    "shield-check": '<path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6l-8-3z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.3-6 6.5-6s5.9 2.4 6.5 6"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8"/><path d="M18 14.3c2 .8 3.2 2.9 3.5 5.7"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c.8-4.2 4-7 8-7s7.2 2.8 8 7"/>',
    sparkles: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="m6.3 6.3 2.1 2.1M15.6 15.6l2.1 2.1M6.3 17.7l2.1-2.1M15.6 8.4l2.1-2.1"/>',
    bot: '<rect x="4" y="8" width="16" height="12" rx="3"/><path d="M12 4v4"/><circle cx="12" cy="3" r="1"/><circle cx="9" cy="14" r="1.2"/><circle cx="15" cy="14" r="1.2"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    bell: '<path d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4l2-2z"/><path d="M10 21a2 2 0 0 0 4 0"/>',
    back: '<path d="M15 5 8 12l7 7"/>',
    chevron: '<path d="m9 5 7 7-7 7"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    trend: '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    diamond: '<path d="M6 3h12l4 6-10 12L2 9l4-6z"/><path d="M2 9h20M9 3 7 9l5 12 5-12-2-6"/>',
    star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9L12 3z"/>',
    heart: '<path d="M12 20s-7.5-4.6-9.2-9.3C1.6 7.4 3.6 4 7 4c2 0 3.4 1.1 5 3 1.6-1.9 3-3 5-3 3.4 0 5.4 3.4 4.2 6.7C19.5 15.4 12 20 12 20z"/>',
    trophy: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>',
    bag: '<path d="M5 8h14l-1 13H6L5 8z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>',
    megaphone: '<path d="M3 11v2a1 1 0 0 0 1 1h3l7 5V5L7 10H4a1 1 0 0 0-1 1z"/><path d="M18 9a4 4 0 0 1 0 6"/>',
    journal: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h4"/>',
    crown: '<path d="m3 8 4.5 4L12 5l4.5 7L21 8l-2 11H5L3 8z"/>',
    message: '<path d="M4 5h16v11H9l-5 4V5z"/>',
    game: '<rect x="2" y="7" width="20" height="11" rx="5"/><path d="M7 10.5v4M5 12.5h4"/><circle cx="15.5" cy="11.5" r="1"/><circle cx="18" cy="14" r="1"/>',
    zap: '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>',
    brain: '<path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 1V5a3 3 0 0 0-3-1z"/><path d="M15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-6 1"/>',
    flame: '<path d="M12 21a6 6 0 0 0 6-6c0-4-3-6-4-10-2 2-3 4-3 6-1-1-2-2-2-4-2 2-3 5-3 8a6 6 0 0 0 6 6z"/>',
    mask: '<path d="M3 5h18v6a9 9 0 0 1-18 0V5z"/><path d="M8 10h.01M16 10h.01M9 15c1.5 1 4.5 1 6 0"/>',
    wave: '<path d="M7 11V6a1.5 1.5 0 0 1 3 0v5M10 10V4.5a1.5 1.5 0 0 1 3 0V10M13 10V5.5a1.5 1.5 0 0 1 3 0V12M16 9.5a1.5 1.5 0 0 1 3 0V14a7 7 0 0 1-12.6 4.2L4 15a1.6 1.6 0 0 1 2.6-2L7 13.5"/>',
    lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    unlock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.5-2"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    ban: '<circle cx="12" cy="12" r="9"/><path d="m5.6 5.6 12.8 12.8"/>',
    mute: '<path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="m17 9 4 6M21 9l-4 6"/>',
    alert: '<path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4M12 17h.01"/>',
    check: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    edit: '<path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="m14 6 4 4"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    refresh: '<path d="M20 11a8 8 0 0 0-14.9-3.5L4 9M4 13a8 8 0 0 0 14.9 3.5L20 15"/><path d="M4 4v5h5M20 20v-5h-5"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    file: '<path d="M6 3h8l4 4v14H6V3z"/><path d="M14 3v4h4M9 13h6M9 17h6"/>',
    group: '<path d="M4 5h16v11H9l-5 4V5z"/><path d="M8 10h8M8 13h5"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    repeat: '<path d="m17 2 4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 0 1-3 3H3"/>',
    wind: '<path d="M3 8h11a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 16h7"/>',
    new: '<path d="M12 3v3M12 18v3M3 12h3M18 12h3"/><circle cx="12" cy="12" r="4"/>',
    gift: '<rect x="3" y="8" width="18" height="4"/><path d="M5 12v9h14v-9M12 8v13M12 8S10 3 7.5 4.5 9 8 12 8zM12 8s2-5 4.5-3.5S15 8 12 8z"/>'
  };

  M.icons = P;

  M.icon = function (name, size) {
    var body = P[name];
    if (!body) return "";
    var s = size || 20;
    return '<svg class="i" width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
      + 'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + body + "</svg>";
  };

  // Иконка в цветной плашке — как у разделов на макете
  var TINTS = {
    purple: "linear-gradient(135deg,#8b5cf6,#c084fc)",
    blue: "linear-gradient(135deg,#3b82f6,#60a5fa)",
    green: "linear-gradient(135deg,#10b981,#34d399)",
    gold: "linear-gradient(135deg,#f59e0b,#fbbf24)",
    red: "linear-gradient(135deg,#ef4444,#f87171)",
    pink: "linear-gradient(135deg,#db2777,#f472b6)"
  };

  M.tile = function (name, tint, size) {
    return '<span class="ic-tile" style="background:' + (TINTS[tint] || TINTS.purple) + '">' + M.icon(name, size || 20) + "</span>";
  };

  // Эмодзи, которые встречаются в метриках и строках разделов,
  // показываем контурными иконками — как на макете. Остальные
  // эмодзи (в тегах, чипах, настройках) остаются как есть.
  M.EMOJI = {
    "💎": "diamond", "✨": "star", "⭐": "star", "❤️": "heart", "💬": "message", "⚡": "zap",
    "🎮": "game", "🎲": "game", "🤖": "bot", "⚠️": "alert", "🔇": "mute", "⛔": "ban",
    "👥": "users", "👤": "user", "👋": "wave", "🏆": "trophy", "🛍": "bag", "📊": "chart",
    "📈": "trend", "📉": "trend", "🖼": "image", "🔥": "flame", "📅": "calendar", "🗓": "calendar",
    "🧠": "brain", "🧩": "brain", "🎭": "mask", "🛡": "shield", "⚙️": "settings", "📣": "megaphone",
    "📋": "journal", "👑": "crown", "🗄": "database", "🧾": "file", "🆕": "new", "🔗": "link",
    "🔁": "repeat", "🌊": "wind", "⏱": "clock", "🏁": "check", "👍": "heart", "🔒": "lock",
    "🔓": "unlock", "🗑": "trash", "🎁": "gift"
  };

  // Имя иконки или эмодзи → цветная плашка; неизвестное — как есть
  M.glyph = function (value, tint, size) {
    var name = P[value] ? value : M.EMOJI[value];
    return name ? M.tile(name, tint, size || 19) : '<span style="font-size:22px;width:38px;text-align:center">' + value + "</span>";
  };

  M.fillIcons = function (root) {
    Array.prototype.forEach.call((root || document).querySelectorAll("[data-icon]"), function (el) {
      el.innerHTML = M.icon(el.getAttribute("data-icon"), parseInt(el.getAttribute("data-size") || "22", 10));
      el.removeAttribute("data-icon");
    });
  };

  M.fillIcons(document);
})();
