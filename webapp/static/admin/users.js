/* ===========================================================
   Участники: список с фильтрами и профиль.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;
  var CATEGORY_TITLES = M.CATEGORY_TITLES, settingsMap = M.settingsMap, needChatScreen = M.needChatScreen;

  // =========================================================
  // ЛЮДИ
  // =========================================================

  var FILTERS = [
    ["all", "Все"], ["active", "Активные"], ["new", "Новые"], ["vip", "⭐ VIP"],
    ["violators", "⚠️ Нарушители"], ["admins", "👑 Админы"],
    ["inactive30", "Неактивные 30д"], ["inactive90", "90д"], ["ignored", "В игноре"], ["left", "Вышли"]
  ];

  var SORTS = [
    ["activity", "По активности"], ["messages", "По сообщениям"], ["xp", "По опыту"],
    ["coins", "По алмазам"], ["karma", "По карме"], ["level", "По уровню"],
    ["warnings", "По нарушениям"], ["joined", "По дате вступления"]
  ];

  M.screen("users", function () {
    var c = M.state.cache;
    var filter = c.userFilter || "all";
    var sort = c.userSort || "activity";
    var query = c.userQuery || "";
    var shown = c.userShown || 40;

    var load = function (offset) {
      return M.api("/api/admin/users" + M.chatQuery() + "&q=" + encodeURIComponent(query)
        + "&filter=" + filter + "&sort=" + sort + "&offset=" + offset);
    };

    // Первая страница + догрузка тем, кто уже нажимал «ещё»
    var pages = [];
    for (var off = 0; off < shown; off += 40) pages.push(load(off));

    Promise.all(pages).then(function (res) {
      var total = res[0].total;
      var inChat = res[0].chat_total;
      // Ботам Telegram не отдаёт полный список участников — только число
      var known = filter === "all" && !query && inChat && inChat > total;
      var people = [].concat.apply([], res.map(function (r) { return r.users; }));

      var right = function (p) {
        if (sort === "xp") return '<span class="tag xp">✨ ' + num(p.xp) + "</span>";
        if (sort === "karma") return '<span class="tag karma">❤️ ' + p.karma + "</span>";
        if (sort === "messages") return '<span class="tag">💬 ' + num(p.messages) + "</span>";
        if (sort === "warnings") return '<span class="tag bad">⚠️ ' + p.warnings + "</span>";
        if (sort === "joined") return '<span class="tag">' + (p.joined ? M.time(p.joined).slice(0, 5) : "—") + "</span>";
        return '<span class="tag coins">💎 ' + num(p.coins) + "</span>";
      };

      var html = M.header("Участники", "Управление пользователями", "users", "pink") + M.chatPicker()
        + '<input data-search placeholder="🔍  Имя, @username или ID" value="' + esc(query) + '" style="margin-bottom:10px">'
        + '<div class="chips">' + FILTERS.map(function (f) {
            return '<span class="chip' + (filter === f[0] ? " on" : "") + '" data-filter="' + f[0] + '">' + f[1] + "</span>";
          }).join("") + "</div>"
        + '<div class="row-gap" style="align-items:center;margin-bottom:10px"><span class="dim grow">Найдено: ' + num(total) + (known ? " из " + num(inChat) + " в группе" : "") + "</span>"
        + '<select data-sort style="width:auto">' + SORTS.map(function (o) {
            return '<option value="' + o[0] + '"' + (sort === o[0] ? " selected" : "") + ">" + o[1] + "</option>";
          }).join("") + "</select></div>"
        + (known ? '<div class="card dim" style="font-size:13px;margin-bottom:10px">ℹ️ Telegram не показывает ботам тех, кто ни разу не писал в группе. '
          + "Они появятся здесь, как только напишут сообщение, зайдут в группу заново или станут админами.</div>" : "");

      html += people.length ? people.map(function (p) {
        return '<div class="list-item tap" data-open="profile" data-arg="' + p.telegram_id + '">'
          + M.avatar(p.telegram_id, p.name)
          + '<div class="grow"><div class="t">' + esc(p.name)
          + (p.vip ? ' <span class="tag xp">VIP</span>' : "")
          + (p.admin ? ' <span class="tag">👑</span>' : "")
          + (p.blocked ? ' <span class="tag bad">игнор</span>' : "")
          + (p.warnings ? ' <span class="tag bad">⚠️ ' + p.warnings + "</span>" : "") + "</div>"
          + '<div class="s">' + (p.username ? "@" + esc(p.username) + " · " : "") + "Ур. " + p.level + " · " + (p.last_seen ? M.ago(p.last_seen) : "ещё не писал(а)") + "</div></div>"
          + right(p) + M.chev() + '</div>';
      }).join("") : '<div class="center muted">Никого не нашла</div>';

      if (people.length < total) html += '<button class="btn block" data-more>Показать ещё (' + (total - people.length) + ")</button>";

      M.app.innerHTML = html;
      M.bind();

      Array.prototype.forEach.call(M.app.querySelectorAll("[data-filter]"), function (el) {
        el.onclick = function () { c.userFilter = el.getAttribute("data-filter"); c.userShown = 40; M.render(); };
      });

      M.app.querySelector("[data-sort]").onchange = function (e) { c.userSort = e.target.value; c.userShown = 40; M.render(); };

      var more = M.app.querySelector("[data-more]");
      if (more) more.onclick = function () { c.userShown = shown + 40; M.render(); };

      var input = M.app.querySelector("[data-search]"), timer;
      input.oninput = function () {
        clearTimeout(timer);
        timer = setTimeout(function () { c.userQuery = input.value.trim(); c.userShown = 40; M.render(); }, 400);
      };
    }).catch(M.fail);
  });

  // ---------- профиль ----------

  var STATUS = {
    creator: ["👑", "Создатель группы"], administrator: ["🛡", "Администратор"], member: ["🟢", "Участник"],
    restricted: ["🔇", "Ограничен"], left: ["🚪", "Вышел из группы"], kicked: ["⛔", "Забанен"]
  };

  var HISTORY_ICON = {
    join: "👋", leave: "🚪", kicked: "⛔", violation: "⚠️", warn: "⚠️", mute: "🔇", unmute: "🔊",
    ban: "⛔", tempban: "⏳", unban: "✅", kick: "👢", ignore: "🙈", unignore: "👂", vip: "⭐", unvip: "☆",
    xp: "✨", karma: "❤️", undo: "↩️", clear_warnings: "🧹"
  };

  var HISTORY_TEXT = {
    join: "Вступил в группу", leave: "Вышел из группы", kicked: "Исключён", violation: "Нарушение",
    warn: "Предупреждение", mute: "Мут", unmute: "Размут", ban: "Бан", tempban: "Бан на время", unban: "Разбан",
    kick: "Выкинут", ignore: "Игнор Мары", unignore: "Снят игнор", vip: "Выдан VIP", unvip: "Снят VIP",
    xp: "Опыт изменён", karma: "Карма изменена", undo: "Отмена изменения", clear_warnings: "Предупреждения сброшены",
    daily_bonus: "Ежедневный бонус", game_win: "Победа в игре", game_host: "Ведущий в игре", purchase: "Покупка",
    gift: "Подарок", admin: "Изменение от админа", achievement: "Достижение"
  };

  function historyRow(h) {
    var icon, title;

    if (h.type === "money") {
      icon = h.amount > 0 ? "💎" : "🛍";
      title = (HISTORY_TEXT[h.action] || h.details || "Алмазы") + ' <b style="color:' + (h.amount > 0 ? "var(--green)" : "var(--red)") + '">'
        + (h.amount > 0 ? "+" : "") + h.amount + "</b>";
    } else if (h.type === "achievement") {
      icon = "🏆";
      title = "Получил достижение";
    } else {
      icon = HISTORY_ICON[h.action] || "•";
      title = esc(HISTORY_TEXT[h.action] || h.action);
    }

    var sub = [];
    if (h.details && h.type !== "money") sub.push(esc(h.details));
    if (h.type === "money" && h.details) sub.push(esc(h.details));
    if (h.actor) sub.push("от " + esc(h.actor));

    return '<div class="event"><div class="ico">' + icon + '</div><div class="grow"><div class="t">' + title + "</div>"
      + '<div class="s">' + M.time(h.at) + (sub.length ? " · " + sub.join(" · ") : "") + "</div></div></div>";
  }

  M.screen("profile", function (userId) {
    M.api("/api/admin/user?user_id=" + userId + (M.state.chat ? "&chat_id=" + M.state.chat : "")).then(function (c) {
      var m = c.member, pr = c.progress;
      var R = 50, L = 2 * Math.PI * R;
      var st = STATUS[c.status] || null;
      var online = M.ago(m.last_seen) === "онлайн";

      var html = M.backButton()

        + '<div class="card glow profile-hero">'
        + '<div class="level-ring"><svg viewBox="0 0 108 108"><circle cx="54" cy="54" r="' + R + '" stroke="#251b44" stroke-width="6" fill="none"/>'
        + '<circle cx="54" cy="54" r="' + R + '" stroke="url(#rg)" stroke-width="6" fill="none" stroke-linecap="round" stroke-dasharray="' + L.toFixed(1) + '" stroke-dashoffset="' + (L * (1 - pr.percent / 100)).toFixed(1) + '"/>'
        + '<defs><linearGradient id="rg"><stop offset="0%" stop-color="#8b5cf6"/><stop offset="100%" stop-color="#e9d5ff"/></linearGradient></defs></svg>'
        + '<div class="avatar" data-img="/api/admin/avatar?user_id=' + c.telegram_id + '">' + esc(c.name.slice(0, 1)) + "</div>"
        + (online ? '<span style="position:absolute;right:10px;bottom:10px;width:16px;height:16px;border-radius:50%;background:var(--green);box-shadow:0 0 0 3px var(--card)"></span>' : "")
        + "</div>"
        + "<h2>" + esc(c.name) + (m.vip ? ' <span class="tag xp">VIP</span>' : "") + "</h2>"
        + '<div class="dim">' + (c.username ? "@" + esc(c.username) + " · " : "") + "ID " + c.telegram_id + "</div>"
        + (st ? '<div class="dim" style="margin-top:4px">' + st[0] + " " + st[1] + "</div>" : "")

        + '<div style="margin:14px auto 0;max-width:300px;text-align:left">'
        + '<div class="row-gap" style="justify-content:space-between;font-size:12px;margin-bottom:5px">'
        + '<span class="level-badge" style="margin:0">Уровень ' + pr.level + " · " + esc(pr.title) + "</span>"
        + '<span class="muted">' + num(pr.into_level) + " / " + num(pr.need) + "</span></div>"
        + '<div class="bar"><span style="width:' + pr.percent + '%"></span></div></div></div>'

        + '<div class="metrics three">'
        + M.metric("💎", num(c.coins), "Алмазы", "", "rgba(192,132,252,.2)")
        + M.metric("✨", num(c.xp), "XP", "", "rgba(251,191,36,.18)")
        + M.metric("❤️", (c.karma > 0 ? "+" : "") + c.karma, "Карма", "", "rgba(248,113,113,.18)")
        + M.metric("💬", num(m.group_messages || c.messages), "Сообщений")
        + M.metric("⚡", num(m.actions), "Actions")
        + M.metric("🎮", num(m.games || c.games_played), "Игр")
        + M.metric("🤖", num(m.ai_requests), "AI-запросов")
        + M.metric("⚠️", m.warnings, "Предупр. сейчас", "", m.warnings ? "rgba(248,113,113,.18)" : "")
        + M.metric("🔇", m.mutes + " / " + m.bans, "Мутов / банов")
        + "</div>"

        + '<div class="card">'
        + '<div class="kv"><span class="k">В группе с</span><span>' + (m.joined ? M.time(m.joined).slice(0, 5) + "." + m.joined.slice(0, 4) : "—") + "</span></div>"
        + '<div class="kv"><span class="k">Последняя активность</span><span>' + M.ago(m.last_seen) + "</span></div>"
        + '<div class="kv"><span class="k">Всего нарушений</span><span>' + m.violations + "</span></div>"
        + '<div class="kv"><span class="k">Выиграно игр</span><span>' + c.games_won + "</span></div>"
        + "</div>";

      if (m.achievements.length) {
        html += '<div class="card"><div class="card-title">Достижения (' + m.achievements.length + ")</div>"
          + m.achievements.map(function (a) { return '<span class="tag" style="margin:0 4px 6px 0">' + a.emoji + " " + esc(a.title) + "</span>"; }).join("")
          + "</div>";
      }

      if (M.can("economy")) {
        html += '<div class="card"><div class="card-title">Алмазы, опыт, карма</div>'
          + '<input type="number" data-amount placeholder="Сколько (можно с минусом)" style="margin-bottom:8px">'
          + '<div class="btns" style="grid-template-columns:repeat(3,minmax(0,1fr))"><button class="btn" data-eco="coins">💎 Баланс</button><button class="btn" data-eco="xp">✨ XP</button><button class="btn" data-eco="karma">❤️ Карма</button></div></div>';
      }

      if (M.can("moderation")) {
        html += '<div class="card"><div class="card-title">Модерация</div>';

        if (!M.state.chat) {
          html += '<div class="dim" style="margin-bottom:8px">В какой группе?</div><select data-card-chat><option value="">— выбери группу —</option>'
            + M.state.session.chats.map(function (ch) { return '<option value="' + ch.chat_id + '">' + esc(ch.title) + "</option>"; }).join("")
            + "</select>";
        } else {
          var canRestrict = !!(M.state.me.bot_rights || {}).restrict;

          html += '<div class="setting" style="padding-top:0"><div class="ico">⭐</div><div class="grow"><div class="t">VIP</div><div class="s">Отметка для фильтра и рассылок</div></div>'
            + '<div class="switch' + (m.vip ? " on" : "") + '" data-vip></div></div>'
            + '<button class="btn block" data-warn style="margin-bottom:8px">⚠️ Предупредить</button>';

          if (canRestrict) {
            html += '<div class="dim" style="margin-bottom:6px">Срок мута и временного бана</div>'
              + '<div class="chips" data-mute-time>'
              + [[10, "10 мин"], [60, "1 час"], [1440, "1 день"], [10080, "Неделя"]].map(function (r, i) {
                  return '<span class="chip' + (i === 1 ? " on" : "") + '" data-min="' + r[0] + '">' + r[1] + "</span>";
                }).join("") + "</div>"
              + '<div class="btns"><button class="btn" data-mod="mute">🔇 Мут</button><button class="btn" data-mod="unmute">🔊 Размут</button>'
              + '<button class="btn" data-mod="tempban">⏳ Бан на срок</button><button class="btn" data-mod="kick">👢 Выкинуть</button>'
              + '<button class="btn" data-mod="unban">✅ Разбанить</button><button class="btn danger" data-mod="ban">⛔ Бан навсегда</button></div>';
          } else {
            html += '<div class="alert warn"><span class="ico">🔑</span><span class="grow">Мут и бан недоступны: у Мары нет прав ограничивать участников в этой группе.</span></div>';
          }

          html += '<div class="btns" style="margin-top:8px"><button class="btn" data-ign="block">🙈 Игнор</button>'
            + '<button class="btn" data-clear-warn>🧹 Сбросить предупр.</button></div>';
        }

        html += "</div>";
      }

      html += '<div class="card"><div class="card-title">История</div>'
        + (c.history_all.length ? c.history_all.slice(0, 30).map(historyRow).join("") : '<div class="dim">Событий пока нет</div>')
        + "</div>";

      M.app.innerHTML = html;
      M.bind();
      bindProfile(c);
    }).catch(M.fail);
  });

  function bindProfile(c) {
    var minutes = 60;
    var reload = function () { M.render(); };

    Array.prototype.forEach.call(M.app.querySelectorAll("[data-min]"), function (el) {
      el.onclick = function () {
        minutes = parseInt(el.getAttribute("data-min"), 10);
        Array.prototype.forEach.call(M.app.querySelectorAll("[data-min]"), function (o) { o.classList.toggle("on", o === el); });
      };
    });

    Array.prototype.forEach.call(M.app.querySelectorAll("[data-eco]"), function (btn) {
      btn.onclick = function () {
        var input = M.app.querySelector("[data-amount]");
        var amount = parseInt(input.value, 10);
        if (!amount) { M.toast("Введи число"); return; }

        var kind = btn.getAttribute("data-eco");

        M.post("/api/admin/user", { action: kind, user_id: c.telegram_id, chat_id: M.state.chat, amount: amount })
          .then(function () {
            M.haptic();
            M.toast({ coins: "Баланс ", xp: "Опыт ", karma: "Карма " }[kind] + (amount > 0 ? "+" : "") + amount, function () {
              M.post("/api/admin/undo", { kind: kind, user_id: c.telegram_id, chat_id: M.state.chat, amount: amount })
                .then(function () { M.toast("Отменено"); reload(); })
                .catch(function (e) { M.toast(e.message); });
            });
            reload();
          })
          .catch(function (e) { M.toast(e.message); });
      };
    });

    var labels = { mute: "Замутить", unmute: "Размутить", kick: "Выкинуть", ban: "Забанить", unban: "Разбанить", tempban: "Забанить на срок" };

    var vip = M.app.querySelector("[data-vip]");
    if (vip) vip.onclick = function () {
      var next = !vip.classList.contains("on");
      vip.classList.toggle("on", next);
      M.post("/api/admin/user", { action: "vip", user_id: c.telegram_id, chat_id: M.state.chat, value: next })
        .then(function () { M.toast(next ? "VIP выдан" : "VIP снят"); })
        .catch(function (e) { vip.classList.toggle("on", !next); M.toast(e.message); });
    };

    var warnBtn = M.app.querySelector("[data-warn]");
    if (warnBtn) warnBtn.onclick = function () {
      M.post("/api/admin/moderate", { action: "warn", chat_id: M.state.chat, user_id: c.telegram_id })
        .then(function (r) {
          M.haptic("medium");
          M.toast(r.result === "warn" ? "Предупреждение выдано" : "Лимит предупреждений — сработало наказание");
          M.render();
        })
        .catch(function (e) { M.toast(e.message); });
    };

    Array.prototype.forEach.call(M.app.querySelectorAll("[data-mod]"), function (btn) {
      btn.onclick = function () {
        var action = btn.getAttribute("data-mod");
        var dangerous = action === "ban" || action === "kick" || action === "tempban";

        var go = function () {
          M.post("/api/admin/moderate", { action: action, chat_id: M.state.chat, user_id: c.telegram_id, minutes: minutes })
            .then(function () {
              M.haptic("medium");
              M.toast("Готово: " + labels[action].toLowerCase(), action === "mute" ? function () {
                M.post("/api/admin/moderate", { action: "unmute", chat_id: M.state.chat, user_id: c.telegram_id })
                  .then(function () { M.toast("Мут снят"); });
              } : null);
            })
            .catch(function (e) { M.toast(e.message); });
        };

        if (dangerous) {
          M.confirm(labels[action] + " " + c.name + "?", {
              ban: "Человек вылетит из группы и не сможет вернуться, пока его не разбанят.",
              tempban: "Человек вылетит из группы и сможет вернуться, когда срок закончится.",
              kick: "Человек вылетит из группы, но сможет вернуться по ссылке."
            }[action], labels[action], true)
            .then(function (yes) { if (yes) go(); });
        } else { go(); }
      };
    });

    var ign = M.app.querySelector("[data-ign]");
    if (ign) ign.onclick = function () {
      M.post("/api/admin/user", { action: "block", user_id: c.telegram_id, chat_id: M.state.chat })
        .then(function () {
          M.toast("Мара его не слышит", function () {
            M.post("/api/admin/user", { action: "unblock", user_id: c.telegram_id, chat_id: M.state.chat })
              .then(function () { M.toast("Снова слышит"); });
          });
        }).catch(function (e) { M.toast(e.message); });
    };

    var clr = M.app.querySelector("[data-clear-warn]");
    if (clr) clr.onclick = function () {
      M.post("/api/admin/warnings/clear", { chat_id: M.state.chat, user_id: c.telegram_id })
        .then(function () { M.toast("Предупреждения сброшены"); })
        .catch(function (e) { M.toast(e.message); });
    };

    var pick = M.app.querySelector("[data-card-chat]");
    if (pick) pick.onchange = function () { if (pick.value) M.setChat(pick.value); };
  }
})();
