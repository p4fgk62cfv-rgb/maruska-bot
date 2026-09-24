/* ===========================================================
   Обновления, логи, система, поиск, уведомления.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;
  var CATEGORY_TITLES = M.CATEGORY_TITLES, settingsMap = M.settingsMap, needChatScreen = M.needChatScreen;

  // =========================================================
  // ОБНОВЛЕНИЯ
  // =========================================================

  function formatDate(iso) {
    var m = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
    var p = iso.split("-");
    return parseInt(p[2], 10) + " " + m[parseInt(p[1], 10) - 1];
  }

  M.screen("changelog", function () {
    M.api("/api/admin/changelog").then(function (d) {
      var all = M.state.cache.allReleases;
      var list = all ? d.releases : d.releases.slice(0, 5);
      var latest = d.releases[0];
      var totals = { new: 0, improved: 0, fixed: 0 };
      d.releases.forEach(function (r) { r.items.forEach(function (i) { totals[i.kind]++; }); });

      M.app.innerHTML = M.backButton()
        + '<div class="hero"><div class="eyebrow">Сейчас работает</div><div class="big">Мара v' + latest.version + "</div>"
        + '<div class="sub">' + esc(latest.title) + " · " + formatDate(latest.date) + "</div>"
        + '<div class="chips" style="margin:12px 0 0"><span class="tag">✨ ' + totals.new + ' новых</span><span class="tag">⚡ ' + totals.improved
        + ' улучшений</span><span class="tag">🔧 ' + totals.fixed + " исправлений</span></div></div>"
        + '<div class="timeline">' + list.map(function (r, i) {
            return '<div class="card release' + (i === 0 ? " current glow" : "") + '">'
              + '<div class="row-gap" style="align-items:center;margin-bottom:6px"><span class="tag' + (i === 0 ? " new" : "") + '">v' + r.version + "</span>"
              + (i === 0 ? '<span class="tag ok">текущая</span>' : "") + '<span class="dim" style="margin-left:auto">' + formatDate(r.date) + "</span></div>"
              + '<div style="font-weight:700;font-size:16px">' + esc(r.title) + '</div><div class="muted" style="font-size:13px;margin:3px 0 10px">' + esc(r.summary) + "</div>"
              + r.items.map(function (it) {
                  var k = d.kinds[it.kind];
                  return '<div class="change"><span class="k ' + it.kind + '">' + k.emoji + " " + esc(k.label) + "</span><span>" + esc(it.text) + "</span></div>";
                }).join("") + "</div>";
          }).join("") + "</div>"
        + (!all && d.releases.length > 5 ? '<div class="center" style="padding:12px;color:var(--accent-2)" data-all>Показать все ' + d.releases.length + " версий ↓</div>" : "");

      M.bind();
      var more = M.app.querySelector("[data-all]");
      if (more) more.onclick = function () { M.state.cache.allReleases = true; M.render(); };

      M.markSeen(latest.version);
    }).catch(M.fail);
  });

  // =========================================================
  // ЛОГИ И СИСТЕМА (владелец)
  // =========================================================

  M.screen("logs", function () {
    var level = M.state.cache.logLevel || "";

    M.api("/api/admin/logs?level=" + level).then(function (d) {
      var chip = function (k, l) { return '<span class="chip' + (level === k ? " on" : "") + '" data-lv="' + k + '">' + l + "</span>"; };

      M.app.innerHTML = M.backButton() + '<div class="chips">' + chip("", "Все") + chip("ERROR", "Ошибки") + chip("WARNING", "Предупреждения") + "</div>"
        + (d.records.length ? d.records.map(function (r) {
            return '<div class="log ' + r.level + '"><span class="dim">' + new Date(r.time * 1000).toTimeString().slice(0, 8) + "</span> " + esc(r.message) + "</div>";
          }).join("") : '<div class="center muted">Пусто</div>');

      M.bind();
      each("[data-lv]", function (el) { el.onclick = function () { M.state.cache.logLevel = el.getAttribute("data-lv"); M.render(); }; });
    }).catch(M.fail);
  });

  M.screen("system", function () {
    M.api("/api/admin/system").then(function (d) {
      var t = { users: "Пользователей", profiles: "Профилей", chats: "Чатов", transactions: "Операций", images: "Картинок", rounds: "Раундов", achievements: "Выдано достижений", inventory: "Вещей" };

      M.app.innerHTML = M.backButton()
        + '<div class="card"><div class="card-title">Состояние</div>'
        + '<div class="kv"><span class="k">Версия</span><span>v' + M.version + "</span></div>"
        + '<div class="kv"><span class="k">Работает</span><span>' + Math.floor(d.uptime / 3600) + " ч " + Math.floor(d.uptime % 3600 / 60) + " мин</span></div>"
        + '<div class="kv"><span class="k">Картинки</span><span>' + (esc(d.providers.join(", ")) || "нет") + "</span></div>"
        + '<div class="kv"><span class="k">Холст крокодила</span><span>' + (d.drawing ? "включён" : "словесный режим") + "</span></div></div>"
        + '<div class="card"><div class="card-title">В базе</div>'
        + Object.keys(d.counts).map(function (k) { return '<div class="kv"><span class="k">' + (t[k] || k) + "</span><span>" + num(d.counts[k]) + "</span></div>"; }).join("") + "</div>";
      M.bind();
    }).catch(M.fail);
  });

  // =========================================================
  // ПОИСК И УВЕДОМЛЕНИЯ
  // =========================================================

  M.screen("search", function () {
    var q = M.state.cache.searchQuery || "";

    var draw = function (d) {
      var html = M.backButton()
        + '<input data-sq placeholder="🔍  Люди, группы, действия, настройки, события" value="' + esc(q) + '" style="margin-bottom:12px" autofocus>';

      if (d) {
        if (d.people.length) html += '<div class="card"><div class="card-title">Люди</div>' + d.people.map(function (p) {
          return '<div class="list-item tap" data-open="profile" data-arg="' + p.telegram_id + '">' + M.avatar(p.telegram_id, p.name, "sm")
            + '<div class="grow"><div class="t">' + esc(p.name) + '</div><div class="s">' + (p.username ? "@" + esc(p.username) : "ID " + p.telegram_id) + "</div></div></div>";
        }).join("") + "</div>";

        if (d.actions.length) html += '<div class="card"><div class="card-title">Действия</div>' + d.actions.map(function (a) {
          return '<div class="list-item tap" data-open="action" data-arg="' + a.key + '"><span style="font-size:20px">' + a.emoji + '</span><div class="grow t">' + esc(a.title) + "</div></div>";
        }).join("") + "</div>";

        if (d.settings.length) html += '<div class="card"><div class="card-title">Настройки</div>' + d.settings.map(function (s) {
          return '<div class="list-item tap" data-open="settings" data-arg="' + esc(s.group) + '"><span style="font-size:20px">' + s.emoji + '</span><div class="grow"><div class="t">' + esc(s.title) + '</div><div class="s">' + esc(s.group) + "</div></div></div>";
        }).join("") + "</div>";

        if (d.groups.length) html += '<div class="card"><div class="card-title">Группы</div>' + d.groups.map(function (g) {
          return '<div class="list-item tap" data-open="group" data-arg="' + g.chat_id + '">'
            + '<div class="avatar sm" data-img="/api/admin/chat_photo?chat_id=' + g.chat_id + '">' + esc(g.title.slice(0, 1)) + "</div>"
            + '<div class="grow"><div class="t">' + esc(g.title) + '</div><div class="s">' + g.members + " участников</div></div></div>";
        }).join("") + "</div>";

        if (d.events.length) html += '<div class="card"><div class="card-title">События <span class="link" data-events-all>Все в журнале →</span></div>'
          + d.events.map(M.eventRow).join("") + "</div>";

        if (!d.people.length && !d.actions.length && !d.settings.length && !d.groups.length && !d.events.length) {
          html += '<div class="center muted">Ничего не нашла</div>';
        }
      }

      M.app.innerHTML = html;
      M.bind();

      var allEvents = M.app.querySelector("[data-events-all]");
      if (allEvents) allEvents.onclick = function () {
        M.state.cache.jf = { category: "", q: q, who: "", from: "", to: "", user: "", userName: "" };
        M.open("journal");
      };

      var input = M.app.querySelector("[data-sq]"), timer;
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
      input.oninput = function () {
        clearTimeout(timer);
        timer = setTimeout(function () { M.state.cache.searchQuery = input.value.trim(); M.render(); }, 350);
      };
    };

    if (q.length >= 2) M.api("/api/admin/search?q=" + encodeURIComponent(q)).then(draw).catch(M.fail);
    else draw(null);
  });

  M.screen("notifications", function () {
    M.api("/api/admin/notifications" + M.chatQuery()).then(function (d) {
      M.state.cache.alerts = d.items.length;

      var LEVELS = { danger: ["Критично", "red"], warn: ["Внимание", "gold"], info: ["Инфо", "blue"] };
      var FIX = { moderation: "Открыть модерацию", users: "К участникам", groups: "К группам", logs: "Открыть логи", system: "Открыть систему" };

      M.app.innerHTML = M.backButton()
        + (d.items.length ? d.items.map(function (a) {
            var lv = LEVELS[a.level] || LEVELS.info;
            return '<div class="card" style="border-left:3px solid var(--' + (lv[1] === "gold" ? "gold" : lv[1] === "red" ? "red" : "blue") + ')">'
              + '<div class="row-gap" style="align-items:center">' + M.glyph(a.icon, lv[1])
              + '<div class="grow"><div class="dim" style="font-weight:700">' + lv[0] + "</div>"
              + '<div class="t" style="font-weight:600">' + esc(a.text) + "</div>"
              + ((a.at || a.object) ? '<div class="dim">' + (a.object ? esc(a.object) : "") + (a.at && a.object ? " · " : "") + (a.at ? "последний раз " + M.ago(a.at) : "") + "</div>" : "")
              + "</div></div>"
              + '<button class="btn block" style="margin-top:10px" data-fix="' + a.go + '">' + esc(FIX[a.go] || "Разобраться") + "</button></div>";
          }).join("") : '<div class="center"><div style="color:var(--green)">' + M.icon("check", 42) + '</div><div class="muted" style="margin-top:8px">Всё спокойно</div></div>');

      each("[data-fix]", function (el) {
        el.onclick = function () {
          var go = el.getAttribute("data-fix");
          if (go === "moderation" || go === "users") { M.state.stack = []; M.switchTab(go); }
          else M.open(go);
        };
      });

      M.bind();
    }).catch(M.fail);
  });
})();
