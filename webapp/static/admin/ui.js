/* ===========================================================
   Общие элементы экранов: шапка, метрики, полосы, график,
   строка события, помощники. Грузится до файлов разделов.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num;

  M.each = function (sel, fn) { Array.prototype.forEach.call(M.app.querySelectorAll(sel), fn); };

  M.CATEGORY_TITLES = {
    alcohol: "Алкоголь", drink: "Напитки", food: "Еда", sweet: "Сладкое", fruit: "Фрукты",
    flower: "Цветы", gift: "Подарки", pet: "Животные", pair: "Жесты", call: "Юмор",
    // темы жестов для фильтров
    relations: "Отношения", emotions: "Эмоции", greetings: "Приветствия", leisure: "Досуг", humor: "Юмор"
  };

  // Порядок фильтров как в концепции
  M.THEME_ORDER = ["alcohol", "food", "emotions", "relations", "greetings", "humor", "pet",
                   "drink", "sweet", "fruit", "flower", "gift", "leisure"];

  M.needChatScreen = function (text) {
    M.app.innerHTML = M.backButton() + M.chatPicker(false) + '<div class="center muted">' + text + "</div>";
    M.bind();
  };

  M.settingsMap = function () {
    return M.api("/api/admin/settings" + M.chatQuery()).then(function (d) {
      var map = {};
      d.sections.forEach(function (sec) { sec.items.forEach(function (i) { i.section = sec.name; map[i.key] = i; }); });
      return map;
    });
  };

  // ---------- общие куски ----------

  M.header = function (title, subtitle, icon, tint) {
    var n = M.state.cache.alerts || 0;

    return '<div class="topbar">'
      + (icon ? M.tile(icon, tint, 22) : '<div class="avatar" data-img="/api/admin/bot_photo">М</div>')
      + '<div class="brand"><h1>' + esc(title) + "</h1>"
      + '<div class="sub">' + esc(subtitle || ("Панель управления · v" + M.version)) + "</div></div>"
      + '<div class="icon-btn" data-open="search">' + M.icon("search", 19) + "</div>"
      + '<div class="icon-btn" data-open="notifications">' + M.icon("bell", 19)
      + (n ? '<span class="count">' + n + "</span>" : "") + "</div>"
      + "</div>";
  };

  // Стрелка в строках списков
  M.chev = function () { return '<span class="chev">' + M.icon("chevron", 18) + "</span>"; };

  M.metric = function (icon, value, label, delta, tint) {
    // Имя из набора иконок — контурная иконка, иначе как есть (эмодзи)
    var name = M.icons && (M.icons[icon] ? icon : M.EMOJI && M.EMOJI[icon]);
    var shown = name ? M.icon(name, 18) : icon;

    var raw = String(value).replace(/[\s ,]/g, "");
    var isNum = /^\d+$/.test(raw) && raw.length > 0 && raw.length < 10;
    return '<div class="metric"><div class="ic"' + (tint ? ' style="background:' + tint + '"' : "") + ">"
      + shown + '</div><div class="v"' + (isNum ? ' data-count="' + raw + '"' : "") + ">"
      + value + '</div><div class="l">' + esc(label) + "</div>"
      + (delta ? '<div class="d">' + esc(delta) + "</div>" : "") + "</div>";
  };

  M.bars = function (rows, unit) {
    if (!rows || !rows.length) return '<div class="dim">Пока пусто</div>';

    var top = Math.max.apply(null, rows.map(function (r) { return r.value || r.wins || 0; }).concat([1]));

    return rows.map(function (r) {
      var v = r.value || r.wins || 0;
      return '<div class="bar-row"><div class="top"><span>' + esc(r.name) + "</span><span>"
        + num(v) + (unit || "") + '</span></div><div class="bar"><span style="width:'
        + Math.round(v * 100 / top) + '%"></span></div></div>';
    }).join("");
  };

  M.chart = function (series, field) {
    var w = 320, h = 160, p = 22;
    var vals = series.map(function (s) { return s[field] || 0; });
    var top = Math.max.apply(null, vals.concat([1]));

    var pts = vals.map(function (v, i) {
      return [p + i * (w - p * 2) / Math.max(vals.length - 1, 1), h - p - (v / top) * (h - p * 2)];
    });

    var line = pts.map(function (q, i) { return (i ? "L" : "M") + q[0].toFixed(1) + " " + q[1].toFixed(1); }).join(" ");
    var area = line + " L " + pts[pts.length - 1][0].toFixed(1) + " " + (h - p) + " L " + pts[0][0].toFixed(1) + " " + (h - p) + " Z";

    var labels = series.map(function (s, i) {
      if (series.length > 8 && i % Math.ceil(series.length / 7)) return "";
      return '<text x="' + pts[i][0].toFixed(1) + '" y="' + (h - 5) + '" fill="#6f6596" font-size="9" text-anchor="middle">' + s.day.slice(8) + "</text>";
    }).join("");

    var last = pts[pts.length - 1];

    return '<svg class="chart" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none">'
      + '<defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#8b5cf6" stop-opacity=".5"/><stop offset="100%" stop-color="#8b5cf6" stop-opacity="0"/></linearGradient></defs>'
      + '<path d="' + area + '" fill="url(#cg)"/>'
      + '<path d="' + line + '" fill="none" stroke="#c084fc" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>'
      + '<circle cx="' + last[0].toFixed(1) + '" cy="' + last[1].toFixed(1) + '" r="4" fill="#e9d5ff"/>'
      + labels + '<text x="4" y="12" fill="#6f6596" font-size="9">' + num(top) + "</text></svg>";
  };

  var EVENT_ICONS = {
    moderation: ["shield", "rgba(248,113,113,.18)", "#fca5a5"],
    economy: ["diamond", "rgba(251,191,36,.18)", "#fcd34d"],
    settings: ["settings", "rgba(139,92,246,.2)", "#d8b4fe"],
    broadcast: ["megaphone", "rgba(96,165,250,.18)", "#93c5fd"],
    system: ["database", "rgba(148,163,184,.18)", "#cbd5e1"],
    actions: ["zap", "rgba(192,132,252,.2)", "#e9d5ff"],
    member: ["users", "rgba(52,211,153,.18)", "#6ee7b7"]
  };

  var EVENT_TEXT = {
    violation: "нарушение", mute: "мут", unmute: "размут", ban: "бан", unban: "разбан",
    kick: "выкинут", lock: "чат закрыт", unlock: "чат открыт", ignore: "игнор", unignore: "снят игнор",
    clear_warnings: "сброс предупреждений", coins: "баланс", xp: "опыт", undo: "отмена",
    change: "изменена настройка", role: "назначена роль", created: "рассылка запланирована",
    sent: "рассылка отправлена", toggle: "действие переключено",
    warn: "предупреждение", tempban: "бан на время", vip: "выдан VIP", unvip: "снят VIP",
    karma: "карма", mass: "массовое изменение", shop: "магазин",
    join: "вступил", leave: "вышел", kicked: "исключён",
    memory_clear: "память очищена", autoreply: "автоответ", autoreply_delete: "автоответ удалён",
    add_alias: "добавлено слово", add_phrase: "добавлена фраза", add_image: "добавлена картинка",
    remove_alias: "удалено слово", remove_phrase: "удалена фраза", remove_image: "удалена картинка",
    hide_image: "картинка скрыта", show_image: "картинка возвращена", delete_image: "картинка удалена",
    option: "настройка действия", category: "категория действий"
  };

  M.eventRow = function (e) {
    var who = e.actor_kind === "bot" ? "Мара" : (e.actor_name || "Система");
    var what = EVENT_TEXT[e.action] || e.action;
    var whom = e.target_name ? " → " + e.target_name : "";

    var look = EVENT_ICONS[e.category] || ["new", "var(--card-3)", "var(--muted)"];

    return '<div class="event"><div class="ico" style="background:' + look[1] + ";color:" + look[2] + '">' + M.icon(look[0], 16) + "</div>"
      + '<div class="grow"><div class="t"><b>' + esc(who) + "</b>: " + esc(what) + esc(whom)
      + (e.details ? ' <span class="muted">· ' + esc(e.details) + "</span>" : "") + "</div>"
      + '<div class="s">' + M.time(e.created_at) + "</div></div></div>";
  };

})();
