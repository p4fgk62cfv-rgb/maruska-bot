/* ===========================================================
   Главная — командный центр.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;
  var CATEGORY_TITLES = M.CATEGORY_TITLES, settingsMap = M.settingsMap, needChatScreen = M.needChatScreen;

  // =========================================================
  // ГЛАВНАЯ — командный центр
  // =========================================================

  M.screen("home", function () {
    M.api("/api/admin/dashboard" + M.chatQuery()).then(function (d) {
      M.state.cache.alerts = d.attention.length;

      var chat = M.state.session.chats.filter(function (c) { return String(c.chat_id) === String(M.state.chat); })[0];
      var st = d.status;
      var ok = st.all_ok;

      // Индикатор одной системы: зелёная или красная точка и подпись
      var sys = function (label, item, okText) {
        var good = item && item.ok;
        var detail = good ? (item.ms !== undefined ? item.ms + " мс" : okText || "ок")
          : (item && item.configured === false ? "не настроено" : item && item.errors ? item.errors + " ошиб." : "нет ответа");
        return '<div class="kv" style="padding:6px 0"><span class="k">'
          + '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px;background:var(--' + (good ? "green" : "red") + ')"></span>'
          + label + '</span><span style="color:var(--' + (good ? "muted" : "red") + ')">' + detail + "</span></div>";
      };
      var t = d.today;

      var tile = { messages: "rgba(139,92,246,.22)", coins: "rgba(251,191,36,.2)", active: "rgba(96,165,250,.22)", people: "rgba(192,132,252,.22)" };
      var ALERT_ICONS = { "⚠️": "alert", "👋": "users", "🔑": "lock", "🔥": "flame", "🖼": "image", "🤖": "bot", "✈️": "link", "🗄": "database" };

      var html = '<div class="home-hero">'
        + '<div class="avatar" data-img="/api/admin/bot_photo">М</div>'
        + '<div class="grow"><h1>Маруська 💜</h1><div class="sub">Панель управления · v' + M.version + "</div>"
        + '<div class="group">' + esc(chat ? chat.title : "Все группы") + "</div></div>"
        + '<div class="icon-btn" data-open="search">' + M.icon("search", 19) + "</div>"
        + '<div class="icon-btn" data-open="notifications">' + M.icon("bell", 19)
        + (d.attention.length ? '<span class="count">' + d.attention.length + "</span>" : "") + "</div></div>"
        + M.chatPicker()

        + '<div class="card ' + (ok ? "ok" : "bad") + '"><div class="setting" style="border:0;padding:0">'
        + M.tile(ok ? "shield-check" : "alert", ok ? "green" : "red", 22)
        + '<div class="grow"><div class="t" style="font-size:16px">' + (ok ? "Всё работает" : "Есть проблемы") + "</div>"
        + '<div class="s">' + (ok ? "Все системы отвечают" : "Одна или несколько систем с проблемами — детали ниже") + "</div></div></div>"
        + '<div style="margin-top:10px">'
        + sys("Telegram API", st.telegram) + sys("База данных", st.database)
        + sys("AI (Gemini)", st.ai, "без ошибок") + sys("Картинки", st.images, "без ошибок")
        + sys("Actions", st.actions, st.actions && st.actions.count + " действий")
        + "</div></div>"

        + '<div class="metrics">'
        + M.metric("users", num(d.totals.people), "Участников", t.new_users ? "+" + t.new_users + " сегодня" : "", tile.people)
        + M.metric("zap", num(d.totals.active_today), "Активных сегодня", "", tile.active)
        + M.metric("message", num(t.messages), "Сообщений сегодня", "", tile.messages)
        + M.metric("diamond", num(d.totals.coins), "Алмазов", t.coins ? "+" + num(t.coins) + " сегодня" : "", tile.coins)
        + "</div>";

      if (d.attention.length) {
        html += '<div class="attention"><div class="head">' + M.icon("alert", 20) + "Требует внимания"
          + '<span class="count">' + d.attention.length + "</span></div>"
          + d.attention.map(function (a) {
              return '<div class="row" data-go="' + a.go + '">' + M.icon(ALERT_ICONS[a.icon] || "alert", 18)
                + '<span class="grow">' + esc(a.text) + (a.at ? ' <span style="opacity:.7">· ' + M.ago(a.at) + "</span>" : "") + "</span>"
                + M.icon("chevron", 16) + "</div>";
            }).join("") + "</div>";
      }

      html += '<div class="card"><div class="card-title">Сегодня</div><div class="metrics three">'
        + M.metric("mute", t.mutes, "Мутов") + M.metric("ban", t.bans, "Банов") + M.metric("alert", t.warnings, "Предупр.")
        + M.metric("zap", t.actions, "Actions") + M.metric("game", t.games, "Игр") + M.metric("bot", t.ai_requests, "AI-ответов")
        + M.metric("star", num(t.xp), "Выдано XP") + M.metric("trash", t.deleted, "Удалено") + M.metric("gift", t.gifts, "Подарков")
        + "</div></div>"

        + '<div class="card"><div class="card-title">Быстрые действия</div><div class="btns four">'
        + '<div class="quick" data-open="search"><span class="ic">' + M.icon("user", 22) + "</span>Найти</div>"
        + '<div class="quick" data-go-tab="moderation"><span class="ic">' + M.icon("shield", 22) + "</span>Модерация</div>"
        + '<div class="quick" data-open="economy"><span class="ic">' + M.icon("diamond", 22) + "</span>Экономика</div>"
        + '<div class="quick" data-open="actions"><span class="ic">' + M.icon("zap", 22) + "</span>Actions</div>"
        + '<div class="quick" data-open="broadcasts"><span class="ic">' + M.icon("megaphone", 22) + "</span>Рассылка</div>"
        + '<div class="quick" data-open="analytics"><span class="ic">' + M.icon("chart", 22) + "</span>Аналитика</div>"
        + '<div class="quick" data-open="journal"><span class="ic">' + M.icon("journal", 22) + "</span>Журнал</div>"
        + '<div class="quick" data-go-tab="users"><span class="ic">' + M.icon("users", 22) + "</span>Люди</div>"
        + "</div>"
        + '<div class="dim" style="margin:12px 0 6px">Сразу к человеку</div><div class="btns four" style="grid-template-columns:repeat(5,minmax(0,1fr))">'
        + '<div class="quick" data-quick="mute"><span class="ic">' + M.icon("mute", 20) + "</span>Мут</div>"
        + '<div class="quick" data-quick="warn"><span class="ic">' + M.icon("alert", 20) + "</span>Предупр.</div>"
        + '<div class="quick" data-quick="ban"><span class="ic">' + M.icon("ban", 20) + "</span>Бан</div>"
        + '<div class="quick" data-quick="coins"><span class="ic">' + M.icon("diamond", 20) + "</span>Алмазы</div>"
        + '<div class="quick" data-quick="xp"><span class="ic">' + M.icon("star", 20) + "</span>XP</div>"
        + "</div></div>"

        + '<div class="card"><div class="card-title">Последние события <span class="link" data-open="journal">Все →</span></div>'
        + (d.events.length ? d.events.map(M.eventRow).join("") : '<div class="dim">Пока тихо</div>')
        + "</div>";

      M.app.innerHTML = html;
      M.bind();
      bindGo();
      bindQuick();
    }).catch(M.fail);
  });

  // ---------- быстрые действия: действие → человек → подтверждение ----------

  var QUICK = {
    mute: { title: "Замутить", perm: "moderation", needsRights: true },
    warn: { title: "Предупредить", perm: "moderation" },
    ban: { title: "Забанить", perm: "moderation", needsRights: true, danger: true },
    coins: { title: "Изменить алмазы", perm: "economy", amount: true },
    xp: { title: "Выдать XP", perm: "economy", amount: true }
  };

  function bindQuick() {
    Array.prototype.forEach.call(M.app.querySelectorAll("[data-quick]"), function (el) {
      el.onclick = function () { quickSheet(el.getAttribute("data-quick")); };
    });
  }

  function quickSheet(kind) {
    var q = QUICK[kind];

    if (!M.state.chat) { M.toast("Сначала выбери группу вверху"); return; }
    if (!M.can(q.perm)) { M.toast("Недостаточно прав для этого действия"); return; }
    if (q.needsRights && !(M.state.me.bot_rights || {}).restrict) { M.toast("У Мары нет права ограничивать участников"); return; }

    var bg = document.createElement("div");
    bg.className = "sheet-bg";
    bg.innerHTML = '<div class="sheet"><div class="grip"></div><h3>' + esc(q.title) + "</h3>"
      + (q.amount ? '<input type="number" data-q-amount placeholder="Сколько (минус — списать)" style="margin:8px 0">' : "")
      + (kind === "mute" ? '<select data-q-min style="margin:8px 0"><option value="10">10 минут</option><option value="60" selected>1 час</option><option value="1440">1 день</option><option value="10080">Неделя</option></select>' : "")
      + '<input data-q-search placeholder="Кого: имя, @username или ID" style="margin-bottom:8px">'
      + '<div data-q-list class="dim">Начни вводить имя</div>'
      + '<button class="btn block" data-q-close style="margin-top:10px">Отмена</button></div>';

    document.body.appendChild(bg);

    var close = function () { bg.remove(); };
    bg.querySelector("[data-q-close]").onclick = close;
    bg.onclick = function (e) { if (e.target === bg) close(); };

    var list = bg.querySelector("[data-q-list]");
    var input = bg.querySelector("[data-q-search]");
    var timer;

    input.oninput = function () {
      clearTimeout(timer);
      var text = input.value.trim();
      if (text.length < 2) { list.innerHTML = "Начни вводить имя"; return; }

      timer = setTimeout(function () {
        M.api("/api/admin/search?q=" + encodeURIComponent(text)).then(function (r) {
          list.innerHTML = r.people.slice(0, 5).map(function (p) {
            return '<div class="list-item tap" data-q-pick="' + p.telegram_id + '" data-q-name="' + esc(p.name) + '">'
              + M.avatar(p.telegram_id, p.name, "sm") + '<div class="grow t">' + esc(p.name) + "</div></div>";
          }).join("") || "Никого не нашла";

          M.loadImages(list);

          Array.prototype.forEach.call(list.querySelectorAll("[data-q-pick]"), function (row) {
            row.onclick = function () { run(parseInt(row.getAttribute("data-q-pick"), 10), row.getAttribute("data-q-name")); };
          });
        }).catch(function (e) { list.textContent = e.message; });
      }, 350);
    };

    function run(userId, name) {
      var amountEl = bg.querySelector("[data-q-amount]");
      var amount = amountEl ? parseInt(amountEl.value, 10) : 0;

      if (q.amount && !amount) { M.toast("Введи сумму"); return; }

      // Запрос создаётся только функцией: fetch уходит в момент вызова,
      // поэтому для бана его нельзя собирать до подтверждения
      var send = function () {
        if (kind === "coins" || kind === "xp") {
          return M.post("/api/admin/user", { action: kind, user_id: userId, chat_id: M.state.chat, amount: amount });
        }

        var minutes = kind === "mute" ? parseInt(bg.querySelector("[data-q-min]").value, 10) : undefined;
        return M.post("/api/admin/moderate", { action: kind, chat_id: M.state.chat, user_id: userId, minutes: minutes });
      };

      var go = function () {
        send().then(function () {
          close();
          M.haptic("medium");
          M.toast(q.title + ": " + name + (q.amount ? " " + (amount > 0 ? "+" : "") + amount : ""), q.amount ? function () {
            M.post("/api/admin/undo", { kind: kind, user_id: userId, chat_id: M.state.chat, amount: amount })
              .then(function () { M.toast("Отменено"); });
          } : null);
        }).catch(function (e) { M.toast(e.message); });
      };

      if (q.danger) {
        M.confirm(q.title + " " + name + "?", "Человек вылетит из группы и не вернётся, пока его не разбанят.", "Забанить", true)
          .then(function (yes) { if (yes) go(); });
        return;
      }

      go();
    }
  }

  function bindGo() {
    Array.prototype.forEach.call(M.app.querySelectorAll("[data-go]"), function (el) {
      el.onclick = function () {
        var go = el.getAttribute("data-go");
        if (["moderation", "users"].indexOf(go) >= 0) { switchTab(go); } else { M.open(go); }
      };
    });

    Array.prototype.forEach.call(M.app.querySelectorAll("[data-go-tab]"), function (el) {
      el.onclick = function () { switchTab(el.getAttribute("data-go-tab")); };
    });
  }

  function switchTab(tab) {
    var btn = document.querySelector('#nav [data-tab="' + tab + '"]');
    if (btn) btn.click();
  }

  M.switchTab = switchTab;
})();
