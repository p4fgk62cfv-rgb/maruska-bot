/* ===========================================================
   🃏 Арена (онлайн-дурак): игроки, деньги, столы, турниры, сезоны,
   магазин, модерация, рассылка. Только для владельца бота.
   Запросы идут через /api/admin/arena/* → внутренний API арены.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;

  var A = function (path) { return M.api("/api/admin/arena/" + path); };
  var AP = function (path, body) { return M.post("/api/admin/arena/" + path, body || {}); };

  var CUR = { CREDITS: "🪙 кредиты", COINS: "🟡 монеты", DIAMONDS: "💎 алмазы" };
  var CUR_SHORT = { CREDITS: "кр.", COINS: "мон.", DIAMONDS: "алм." };
  var TX = {
    SIGNUP_BONUS: "Бонус за регистрацию", DAILY_BONUS: "Ежедневные кредиты", GAME_STAKE: "Ставка", GAME_PAYOUT: "Выигрыш",
    GAME_REFUND: "Возврат ставки", PURCHASE: "Покупка", PURCHASE_REFUND: "Возврат за предмет", TOURNAMENT_FEE: "Взнос за турнир",
    TOURNAMENT_PRIZE: "Приз турнира", TOURNAMENT_REFUND: "Возврат взноса", ACHIEVEMENT_REWARD: "Достижение", EXCHANGE: "Обмен",
    ADMIN: "Правка админа", MODERATION: "Изъятие модератором"
  };
  var REPORT = { CHEATING: "жульничает", COLLUSION: "сговор", INSULT: "имя/фото", OTHER: "другое" };
  var T_STATUS = { ANNOUNCED: "анонс", REGISTRATION: "регистрация", RUNNING: "идёт", FINISHED: "завершён", CANCELLED: "отменён" };
  var KIND = { CARD_BACK: "Рубашка", TABLE: "Стол", FRAME: "Рамка", CROWN: "Корона", EFFECT: "Эффект", EMOJI: "Смайлы", AVATAR: "Аватар" };

  function short(n) {
    var a = Math.abs(n);
    if (a >= 1e6) return (n / 1e6).toFixed(2).replace(/\.?0+$/, "") + "M";
    if (a >= 1e4) return (n / 1e3).toFixed(1).replace(".0", "") + "K";
    return num(n);
  }

  function arenaAvatar(p) {
    var url = p.photoUrl || "";
    return '<div class="avatar">' + (url ? '<img src="' + esc(url) + '" alt="" referrerpolicy="no-referrer">' : esc((p.name || "?").slice(0, 1).toUpperCase())) + "</div>";
  }

  function when(iso) { return iso ? M.time(iso.replace("Z", "")) : "—"; }

  function fail(e) { M.toast(e.message || "Не получилось"); }

  // Небольшая форма в выезжающей панели: поля → Promise со значениями или null.
  function form(title, fields, okLabel, danger) {
    return new Promise(function (resolve) {
      var bg = document.createElement("div");
      bg.className = "sheet-bg";
      bg.innerHTML = '<div class="sheet"><div class="grip"></div><h3>' + esc(title) + "</h3>"
        + fields.map(function (f) {
            var label = f.label ? '<div class="dim" style="margin:10px 0 4px">' + esc(f.label) + "</div>" : "";
            if (f.type === "chips") {
              return label + '<div class="chips" data-f="' + f.name + '">' + f.options.map(function (o, i) {
                return '<span class="chip' + (String(o[0]) === String(f.value != null ? f.value : f.options[0][0]) ? " on" : "") + '" data-v="' + esc(o[0]) + '">' + esc(o[1]) + "</span>";
              }).join("") + "</div>";
            }
            if (f.type === "textarea") return label + '<textarea data-f="' + f.name + '" placeholder="' + esc(f.placeholder || "") + '">' + esc(f.value || "") + "</textarea>";
            return label + '<input data-f="' + f.name + '" type="' + (f.type || "text") + '" value="' + esc(f.value == null ? "" : f.value) + '" placeholder="' + esc(f.placeholder || "") + '">';
          }).join("")
        + '<div class="btns" style="margin-top:16px"><button class="btn" data-no>Отмена</button><button class="btn ' + (danger ? "danger" : "primary") + '" data-yes>' + esc(okLabel || "Готово") + "</button></div></div>";
      document.body.appendChild(bg);

      Array.prototype.forEach.call(bg.querySelectorAll(".chips"), function (group) {
        Array.prototype.forEach.call(group.querySelectorAll(".chip"), function (chip) {
          chip.onclick = function () {
            Array.prototype.forEach.call(group.querySelectorAll(".chip"), function (c) { c.classList.toggle("on", c === chip); });
          };
        });
      });

      function close(v) { bg.remove(); resolve(v); }
      bg.querySelector("[data-no]").onclick = function () { close(null); };
      bg.onclick = function (e) { if (e.target === bg) close(null); };
      bg.querySelector("[data-yes]").onclick = function () {
        var out = {};
        fields.forEach(function (f) {
          var el = bg.querySelector('[data-f="' + f.name + '"]');
          if (f.type === "chips") { var on = el.querySelector(".chip.on"); out[f.name] = on ? on.getAttribute("data-v") : null; }
          else out[f.name] = el.value;
        });
        M.haptic("medium");
        close(out);
      };
    });
  }

  // =========================================================
  // Хаб
  // =========================================================

  var MENU = [
    ["arena_players", "users", "Игроки", "Поиск, балансы, баны, премиум"],
    ["arena_live", "game", "Столы сейчас", "Ожидающие и идущие партии"],
    ["arena_moderation", "shield", "Модерация", "Жалобы и подозрительные пары"],
    ["arena_tournaments", "trophy", "Турниры", "Создать, отменить"],
    ["arena_seasons", "calendar", "Сезоны", "Рейтинг по сезонам"],
    ["arena_shop", "bag", "Магазин", "Рубашки, рамки, цены"],
    ["arena_broadcast", "megaphone", "Рассылка игрокам", "Сообщение от бота в личку"],
    ["arena_settings", "settings", "Правила экономики", "Бонусы, комиссия, цены подсказок"]
  ];

  M.screen("arena", function () {
    A("overview").then(function (d) {
      var html = M.backButton()
        + '<div class="metrics three">'
        + M.metric("🟢", num(d.online), "Онлайн") + M.metric("🃏", num(d.gamesRunning), "Идёт партий") + M.metric("⏳", num(d.roomsWaiting), "Ждут игроков")
        + "</div>"
        + '<div class="metrics three">'
        + M.metric("👥", num(d.players), "Игроков") + M.metric("✨", num(d.newToday), "Новых сегодня") + M.metric("📅", num(d.active7), "Активны 7 дн")
        + "</div>"
        + '<div class="metrics three">'
        + M.metric("🎮", num(d.gamesToday), "Партий сегодня") + M.metric("🪙", short(d.stakedToday), "Ставок сегодня") + M.metric("🏦", short(d.rakeToday), "Комиссия сегодня")
        + "</div>"
        + (d.bans || d.reports7 || d.outbox
          ? '<div class="card"><div class="kv"><span class="k">Забанено сейчас</span><span>' + num(d.bans) + "</span></div>"
            + '<div class="kv"><span class="k">Жалоб за неделю</span><span>' + num(d.reports7) + "</span></div>"
            + '<div class="kv"><span class="k">Сообщений бота в очереди</span><span>' + num(d.outbox) + "</span></div></div>"
          : "")
        + (d.topWinners.length
          ? '<div class="card"><div class="card-title">🏆 Больше всех выиграли сегодня</div>' + d.topWinners.map(function (w) {
              return '<div class="list-item tap" data-open="arena_player" data-arg="' + esc(w.telegramId) + '"><div class="grow"><div class="t">' + esc(w.name) + '</div></div><span class="tag ok">+' + short(w.net) + "</span>" + M.chev() + "</div>";
            }).join("") + "</div>"
          : "")
        + '<div class="card">' + MENU.map(function (m) {
            return '<div class="list-item tap" data-open="' + m[0] + '">' + M.tile(m[1], "green", 18) + '<div class="grow"><div class="t">' + m[2] + '</div><div class="s">' + m[3] + "</div></div>" + M.chev() + "</div>";
          }).join("") + "</div>";
      M.app.innerHTML = html;
      M.bind();
    }).catch(M.fail);
  });

  // =========================================================
  // Игроки
  // =========================================================

  M.screen("arena_players", function () {
    var q = M.state.cache.arenaQuery || "";
    M.app.innerHTML = M.backButton()
      + '<div class="card"><input data-q placeholder="Имя, @username или Telegram ID" value="' + esc(q) + '"></div><div data-list></div>';
    M.bind();

    var list = M.app.querySelector("[data-list]");
    var input = M.app.querySelector("[data-q]");
    var timer = null;

    function load() {
      M.state.cache.arenaQuery = input.value;
      list.innerHTML = '<div class="dim">Ищу…</div>';
      A("players?q=" + encodeURIComponent(input.value.trim()) + "&limit=40").then(function (rows) {
        list.innerHTML = rows.length ? '<div class="card">' + rows.map(function (p) {
          return '<div class="list-item tap" data-open="arena_player" data-arg="' + esc(p.telegramId) + '">' + arenaAvatar(p)
            + '<div class="grow"><div class="t">' + esc(p.name) + (p.banned ? ' <span class="tag bad">бан</span>' : "") + "</div>"
            + '<div class="s">' + (p.username ? "@" + esc(p.username) + " · " : "") + "🪙 " + short(p.credits) + " · игр " + num(p.games) + " · " + M.ago(p.lastSeenAt.replace("Z", "")) + "</div></div>" + M.chev() + "</div>";
          }).join("") + "</div>" : '<div class="center muted">Никого не нашли</div>';
        M.bind();
      }).catch(function (e) { list.innerHTML = '<div class="center muted">' + esc(e.message) + "</div>"; });
    }

    input.oninput = function () { clearTimeout(timer); timer = setTimeout(load, 350); };
    load();
  });

  M.screen("arena_player", function (tg) {
    Promise.all([A("players/" + tg), M.state.cache.arenaItems ? Promise.resolve(M.state.cache.arenaItems) : A("items")]).then(function (res) {
      var p = res[0], items = res[1];
      M.state.cache.arenaItems = items;
      var st = p.stats, w = p.wallet;
      var banned = p.ban && p.ban.active;
      var premium = p.premiumUntil && new Date(p.premiumUntil) > new Date();

      var html = M.backButton()
        + '<div class="card glow"><div class="list-item">' + arenaAvatar(p) + '<div class="grow"><div class="t">' + esc(p.name)
        + (banned ? ' <span class="tag bad">бан</span>' : "") + (premium ? ' <span class="tag coins">премиум</span>' : "") + "</div>"
        + '<div class="s">' + (p.username ? "@" + esc(p.username) + " · " : "") + "ID " + esc(p.telegramId)
        + (p.nickname ? " · в Telegram: " + esc(p.telegramName) : "") + "</div>"
        + '<div class="s">' + (p.online ? "🟢 в сети" : "был " + M.ago(p.lastSeenAt.replace("Z", ""))) + (p.at ? (p.at.kind === "game" ? " · играет" : " · за столом") : "") + " · с " + when(p.createdAt) + "</div></div></div></div>"

        + '<div class="metrics three">' + M.metric("🪙", short(w.CREDITS || 0), "Кредиты") + M.metric("🟡", num(w.COINS || 0), "Монеты") + M.metric("💎", num(w.DIAMONDS || 0), "Алмазы") + "</div>"

        + '<div class="card"><div class="card-title">Статистика</div>'
        + '<div class="kv"><span class="k">Рейтинг</span><span>' + num(st.rating) + " · " + esc(st.league) + " лига, ур. " + st.level + "</span></div>"
        + '<div class="kv"><span class="k">Партии</span><span>' + num(st.games) + " · побед " + num(st.wins) + " · поражений " + num(st.losses) + "</span></div>"
        + '<div class="kv"><span class="k">Выиграно всего</span><span>🪙 ' + num(st.winnings) + "</span></div>"
        + '<div class="kv"><span class="k">Серия / лучшая</span><span>' + st.streak + " / " + st.bestStreak + "</span></div>"
        + '<div class="kv"><span class="k">Пойман на шулерстве</span><span>' + st.caughtCheating + "</span></div>"
        + (Object.keys(p.reports).length ? '<div class="kv"><span class="k">Жалобы</span><span>' + Object.keys(p.reports).map(function (k) { return REPORT[k] + " " + p.reports[k]; }).join(", ") + "</span></div>" : "")
        + (banned ? '<div class="kv"><span class="k">Бан</span><span>' + (p.ban.until ? "до " + when(p.ban.until) : "навсегда") + " · " + esc(p.ban.reason || "") + "</span></div>" : "")
        + (premium ? '<div class="kv"><span class="k">Премиум до</span><span>' + when(p.premiumUntil) + "</span></div>" : "")
        + "</div>"

        + '<div class="card"><div class="card-title">Действия</div>'
        + '<button class="btn primary block" data-act="wallet">💰 Начислить или списать</button>'
        + '<div class="row-gap" style="margin-top:8px"><button class="btn block" data-act="premium">⭐ Премиум</button><button class="btn block" data-act="item">🎁 Выдать предмет</button></div>'
        + '<div class="row-gap" style="margin-top:8px"><button class="btn block" data-act="nickname"' + (p.nickname ? "" : " disabled") + '>✏️ Сбросить имя</button><button class="btn block" data-act="avatar"' + (p.customAvatar ? "" : " disabled") + '>🖼 Сбросить фото</button></div>'
        + '<div class="row-gap" style="margin-top:8px">' + (banned ? '<button class="btn block" data-act="unban">🔓 Разбанить</button>' : '<button class="btn danger block" data-act="ban">⛔ Забанить</button>')
        + '<button class="btn danger block" data-act="clawback">↩️ Изъять выигрыш</button></div>'
        + (p.at && p.at.kind === "game" ? '<button class="btn danger block" data-act="abort" style="margin-top:8px">🛑 Отменить его партию (ставки вернутся)</button>' : "")
        + "</div>"

        + (p.items.length ? '<div class="card"><div class="card-title">Предметы</div>' + p.items.map(function (i) {
            return '<div class="kv"><span class="k">' + (KIND[i.kind] || i.kind) + " · " + esc(i.name) + (i.equipped ? ' <span class="tag ok">надет</span>' : "") + '</span><span><span class="dim">' + esc(i.source) + '</span> <button class="btn danger" data-take="' + esc(i.key) + '" style="padding:2px 8px">✕</button></span></div>';
          }).join("") + "</div>" : "")

        + (p.games.length ? '<div class="card"><div class="card-title">Последние партии</div>' + p.games.map(function (g) {
            var net = g.net == null ? '<span class="dim">' + (g.status === "PLAYING" ? "идёт" : g.status === "ABORTED" ? "отменена" : "—") + "</span>" : '<span class="tag ' + (g.net >= 0 ? "ok" : "bad") + '">' + (g.net >= 0 ? "+" : "") + short(g.net) + "</span>";
            return '<div class="kv"><span class="k">' + when(g.startedAt) + " · ставка " + short(g.stake) + " · " + g.players + " игр.</span>" + net + "</div>";
          }).join("") + "</div>" : "")

        + (p.transactions.length ? '<div class="card"><div class="card-title">Операции</div>' + p.transactions.map(function (t) {
            return '<div class="kv"><span class="k">' + when(t.at) + " · " + esc(TX[t.type] || t.type) + '</span><span class="tag ' + (t.amount >= 0 ? "ok" : "bad") + '">' + (t.amount >= 0 ? "+" : "") + num(t.amount) + " " + CUR_SHORT[t.currency] + "</span></div>";
          }).join("") + "</div>" : "");

      M.app.innerHTML = html;
      M.bind();

      var done = function (text) { return function () { M.toast(text); M.render(); }; };
      var act = function (name, fn) { var b = M.app.querySelector('[data-act="' + name + '"]'); if (b) b.onclick = fn; };

      act("wallet", function () {
        form("Баланс: " + p.name, [
          { name: "currency", type: "chips", label: "Валюта", options: [["CREDITS", CUR.CREDITS], ["COINS", CUR.COINS], ["DIAMONDS", CUR.DIAMONDS]] },
          { name: "amount", type: "number", label: "Сколько (минус — списать)", placeholder: "например 5000 или -1000" },
          { name: "reason", label: "Причина (увидите в журнале)", placeholder: "компенсация за сбой" }
        ], "Применить").then(function (v) {
          if (!v) return;
          var amount = parseInt(v.amount, 10);
          if (!amount) return M.toast("Укажите сумму");
          if (!v.reason || v.reason.length < 2) return M.toast("Укажите причину");
          AP("players/" + tg + "/wallet", { currency: v.currency, amount: amount, reason: v.reason }).then(function (r) { M.toast("Готово, на счёте " + num(r.balance)); M.render(); }).catch(fail);
        });
      });

      act("premium", function () {
        form("Премиум", [{ name: "days", type: "chips", label: "Добавить", options: [["7", "7 дней"], ["30", "30 дней"], ["90", "90 дней"], ["365", "год"], ["0", "Снять"]], value: "30" }], "Готово").then(function (v) {
          if (!v) return;
          AP("players/" + tg + "/premium", { days: parseInt(v.days, 10) }).then(done(v.days === "0" ? "Премиум снят" : "Премиум продлён")).catch(fail);
        });
      });

      act("item", function () {
        var owned = p.items.map(function (i) { return i.key; });
        var options = items.filter(function (i) { return owned.indexOf(i.key) < 0 && i.price > 0; }).map(function (i) { return [i.key, (KIND[i.kind] || i.kind) + ": " + i.name]; });
        if (!options.length) return M.toast("У игрока уже есть всё");
        form("Выдать предмет", [{ name: "key", type: "chips", label: "Что выдать", options: options }], "Выдать").then(function (v) {
          if (!v || !v.key) return;
          AP("players/" + tg + "/items", { key: v.key }).then(done("Выдано")).catch(fail);
        });
      });

      M.each("[data-take]", function (b) {
        b.onclick = function () {
          M.confirm("Забрать предмет?", "Предмет пропадёт у игрока, деньги не вернутся.", "Забрать", true).then(function (yes) {
            if (yes) AP("players/" + tg + "/items", { key: b.getAttribute("data-take"), take: true }).then(done("Забрали")).catch(fail);
          });
        };
      });

      act("nickname", function () {
        M.confirm("Сбросить имя?", "Вернётся имя из Telegram: " + p.telegramName, "Сбросить", true).then(function (yes) {
          if (yes) AP("players/" + tg + "/reset", { what: "nickname" }).then(done("Имя сброшено")).catch(fail);
        });
      });
      act("avatar", function () {
        M.confirm("Сбросить фото?", "Вернётся фото из Telegram.", "Сбросить", true).then(function (yes) {
          if (yes) AP("players/" + tg + "/reset", { what: "avatar" }).then(done("Фото сброшено")).catch(fail);
        });
      });

      act("ban", function () {
        form("Забанить " + p.name, [
          { name: "days", type: "chips", label: "Срок", options: [["1", "1 день"], ["7", "7 дней"], ["30", "30 дней"], ["0", "Навсегда"]], value: "7" },
          { name: "reason", label: "Причина", placeholder: "сговор, оскорбления…" }
        ], "Забанить", true).then(function (v) {
          if (!v) return;
          if (!v.reason) return M.toast("Укажите причину");
          var days = parseInt(v.days, 10);
          AP("moderation/ban", { telegramId: tg, days: days || null, reason: v.reason }).then(done("Забанен, выкинут из игры")).catch(fail);
        });
      });
      act("unban", function () { AP("moderation/unban", { telegramId: tg }).then(done("Разбанен")).catch(fail); });

      act("clawback", function () {
        form("Изъять выигрыш", [
          { name: "currency", type: "chips", label: "Валюта", options: [["CREDITS", CUR.CREDITS], ["COINS", CUR.COINS]] },
          { name: "amount", type: "number", label: "Сколько изъять", placeholder: "например 50000" },
          { name: "reason", label: "Причина", placeholder: "перелив кредитов через проигрыш" }
        ], "Изъять", true).then(function (v) {
          if (!v) return;
          var amount = parseInt(v.amount, 10);
          if (!(amount > 0) || !v.reason) return M.toast("Укажите сумму и причину");
          AP("moderation/clawback", { telegramId: tg, currency: v.currency, amount: amount, reason: v.reason }).then(function (r) { M.toast("Изъято " + num(r.taken)); M.render(); }).catch(fail);
        });
      });

      act("abort", function () {
        M.confirm("Отменить партию?", "Все ставки вернутся игрокам, партия закончится.", "Отменить партию", true).then(function (yes) {
          if (yes) AP("games/" + p.at.id + "/abort").then(done("Партия отменена")).catch(fail);
        });
      });
    }).catch(M.fail);
  });

  // =========================================================
  // Столы сейчас
  // =========================================================

  M.screen("arena_live", function () {
    A("live").then(function (d) {
      var html = M.backButton() + '<button class="btn block" data-refresh style="margin-bottom:12px">🔄 Обновить</button>'
        + '<div class="card"><div class="card-title">🃏 Идут партии · ' + d.games.length + "</div>"
        + (d.games.length ? d.games.map(function (g) {
            return '<div class="list-item"><div class="grow"><div class="t">Ставка ' + short(g.stake) + " · ход " + g.moves + " · в колоде " + g.deck + "</div>"
              + '<div class="s">' + g.players.map(function (x) { return esc(x.name) + " (" + x.cards + ")" + (x.connected ? "" : " 📵"); }).join(", ") + "</div>"
              + '<div class="s">с ' + when(g.startedAt) + "</div></div>"
              + '<button class="btn danger" data-abort="' + g.gameId + '">Отменить</button></div>';
          }).join("") : '<div class="dim">Сейчас никто не играет</div>') + "</div>"
        + '<div class="card"><div class="card-title">⏳ Ждут игроков · ' + d.rooms.length + "</div>"
        + (d.rooms.length ? d.rooms.map(function (r) {
            return '<div class="list-item"><div class="grow"><div class="t">' + esc(r.rules) + (r.isPrivate ? " 🔒" : "") + (r.tournament ? " 🏆 " + esc(r.tournament) : "") + "</div>"
              + '<div class="s">' + r.seats.length + "/" + r.players + ": " + r.seats.map(function (s) { return esc(s.name) + (s.ready ? " ✅" : ""); }).join(", ") + " · код " + r.id + "</div></div>"
              + (r.tournament ? "" : '<button class="btn danger" data-close="' + r.id + '">Закрыть</button>') + "</div>";
          }).join("") : '<div class="dim">Пустых столов нет</div>') + "</div>";
      M.app.innerHTML = html;
      M.bind();
      M.app.querySelector("[data-refresh]").onclick = function () { M.render(); };
      M.each("[data-abort]", function (b) {
        b.onclick = function () {
          M.confirm("Отменить партию?", "Все ставки вернутся игрокам.", "Отменить", true).then(function (yes) {
            if (yes) AP("games/" + b.getAttribute("data-abort") + "/abort").then(function () { M.toast("Отменена"); M.render(); }).catch(fail);
          });
        };
      });
      M.each("[data-close]", function (b) {
        b.onclick = function () {
          M.confirm("Закрыть стол?", "Игроки выйдут в лобби, ставки ещё не списывались.", "Закрыть", true).then(function (yes) {
            if (yes) AP("rooms/" + b.getAttribute("data-close") + "/close").then(function () { M.toast("Закрыт"); M.render(); }).catch(fail);
          });
        };
      });
    }).catch(M.fail);
  });

  // =========================================================
  // Модерация: жалобы и подозрительные пары
  // =========================================================

  M.screen("arena_moderation", function () {
    Promise.all([A("moderation/reports?days=14"), A("integrity/suspicious?days=14")]).then(function (res) {
      var reports = res[0], pairs = res[1];
      var html = M.backButton()
        + '<div class="card"><div class="card-title">🚩 Жалобы за 2 недели</div>'
        + (reports.length ? reports.map(function (r) {
            return '<div class="list-item tap" data-open="arena_player" data-arg="' + esc(r.telegramId) + '"><div class="grow"><div class="t">' + esc(r.name) + '</div><div class="s">'
              + Object.keys(r.reasons).map(function (k) { return REPORT[k] + " × " + r.reasons[k]; }).join(", ") + '</div></div><span class="tag bad">' + r.reporters + " чел.</span>" + M.chev() + "</div>";
          }).join("") : '<div class="dim">Жалоб нет</div>') + "</div>"
        + '<div class="card"><div class="card-title">🕵️ Подозрительные пары</div><div class="dim" style="margin-bottom:6px">Кредиты стабильно текут от одного к другому — возможен перелив через проигрыш.</div>'
        + (pairs.length ? pairs.map(function (x) {
            return '<div class="list-item"><div class="grow"><div class="t">' + esc(x.loser.name) + " → " + esc(x.winner.name) + '</div><div class="s">' + num(x.games) + " парт., проиграл ему " + num(x.lostToWinner) + (x.gaveUp ? ", сдался " + num(x.gaveUp) : "") + " · перетекло 🪙 " + num(x.credits) + "</div></div>"
              + '<button class="btn" data-open="arena_player" data-arg="' + esc(x.winner.telegramId) + '">Получатель</button></div>';
          }).join("") : '<div class="dim">Ничего подозрительного</div>') + "</div>";
      M.app.innerHTML = html;
      M.bind();
    }).catch(M.fail);
  });

  // =========================================================
  // Турниры
  // =========================================================

  M.screen("arena_tournaments", function () {
    A("tournaments").then(function (rows) {
      var html = M.backButton() + '<button class="btn primary block" data-new style="margin-bottom:12px">➕ Новый турнир</button>'
        + '<div class="card">' + (rows.length ? rows.map(function (t) {
            var cancellable = t.status === "ANNOUNCED" || t.status === "REGISTRATION";
            return '<div class="list-item"><div class="grow"><div class="t">' + esc(t.title) + ' <span class="tag">' + (T_STATUS[t.status] || t.status) + "</span></div>"
              + '<div class="s">' + when(t.startsAt) + " · " + t.registered + "/" + t.maxPlayers + " · взнос " + (t.entryFee ? num(t.entryFee) + " " + CUR_SHORT[t.currency] : "бесплатно") + " · фонд " + num(t.prizePool) + "</div></div>"
              + (cancellable ? '<button class="btn danger" data-cancel="' + t.id + '">Отменить</button>' : "") + "</div>";
          }).join("") : '<div class="dim">Турниров ещё не было</div>') + "</div>";
      M.app.innerHTML = html;
      M.bind();

      M.app.querySelector("[data-new]").onclick = function () {
        var start = new Date(Date.now() + 3600000);
        start.setMinutes(0, 0, 0);
        var local = new Date(start.getTime() - start.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
        form("Новый турнир", [
          { name: "title", label: "Название", placeholder: "Вечерний кубок" },
          { name: "entryFee", type: "number", label: "Взнос в кредитах (0 — бесплатно)", value: 1000 },
          { name: "maxPlayers", type: "chips", label: "Игроков", options: [["4", "4"], ["8", "8"], ["16", "16"], ["32", "32"], ["64", "64"]], value: "16" },
          { name: "startsAt", type: "datetime-local", label: "Старт (ваше время)", value: local },
          { name: "variant", type: "chips", label: "Режим", options: [["podkidnoy", "Подкидной"], ["perevodnoy", "Переводной"]] }
        ], "Создать").then(function (v) {
          if (!v) return;
          if (!v.title || v.title.length < 3) return M.toast("Название — от 3 букв");
          AP("tournaments", {
            title: v.title, entryFee: parseInt(v.entryFee, 10) || 0, maxPlayers: parseInt(v.maxPlayers, 10),
            startsAt: new Date(v.startsAt).toISOString(),
            settings: { variant: v.variant, throwIn: "all", fairness: "fair", ending: "classic", speed: "normal" }
          }).then(function () { M.toast("Турнир объявлен"); M.render(); }).catch(fail);
        });
      };

      M.each("[data-cancel]", function (b) {
        b.onclick = function () {
          M.confirm("Отменить турнир?", "Взносы вернутся всем, кто записался.", "Отменить", true).then(function (yes) {
            if (yes) AP("tournaments/" + b.getAttribute("data-cancel") + "/cancel").then(function () { M.toast("Отменён"); M.render(); }).catch(fail);
          });
        };
      });
    }).catch(M.fail);
  });

  // =========================================================
  // Сезоны
  // =========================================================

  M.screen("arena_seasons", function () {
    A("seasons").then(function (rows) {
      var now = Date.now();
      var html = M.backButton() + '<button class="btn primary block" data-new style="margin-bottom:12px">➕ Новый сезон</button>'
        + '<div class="card">' + (rows.length ? rows.map(function (s) {
            var live = new Date(s.startsAt).getTime() <= now && new Date(s.endsAt).getTime() > now;
            return '<div class="list-item"><div class="grow"><div class="t">' + esc(s.title) + (live ? ' <span class="tag ok">идёт</span>' : "") + "</div>"
              + '<div class="s">' + when(s.startsAt) + " — " + when(s.endsAt) + " · игроков " + num(s.players) + "</div></div>"
              + (new Date(s.endsAt).getTime() > now ? '<button class="btn danger" data-end="' + s.id + '">Завершить</button>' : "") + "</div>";
          }).join("") : '<div class="dim">Сезонов ещё нет — без сезона колонка «В сезоне» в профилях пустая</div>') + "</div>";
      M.app.innerHTML = html;
      M.bind();

      M.app.querySelector("[data-new]").onclick = function () {
        var d = new Date();
        var first = new Date(d.getFullYear(), d.getMonth(), 1);
        var next = new Date(d.getFullYear(), d.getMonth() + 1, 1);
        var iso = function (x) { return new Date(x.getTime() - x.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };
        form("Новый сезон", [
          { name: "title", label: "Название", placeholder: "Осень" },
          { name: "startsAt", type: "date", label: "Начало", value: iso(first) },
          { name: "endsAt", type: "date", label: "Конец (не включительно)", value: iso(next) }
        ], "Создать").then(function (v) {
          if (!v) return;
          AP("seasons", { title: v.title, startsAt: new Date(v.startsAt + "T00:00:00").toISOString(), endsAt: new Date(v.endsAt + "T00:00:00").toISOString() })
            .then(function () { M.toast("Сезон создан"); M.render(); }).catch(function (e) { M.toast(e.message === "Проверьте введённые данные" ? "Даты пересекаются с другим сезоном или конец раньше начала" : e.message); });
        });
      };
      M.each("[data-end]", function (b) {
        b.onclick = function () {
          M.confirm("Завершить сезон сейчас?", "Сезонный рейтинг перестанет расти.", "Завершить", true).then(function (yes) {
            if (yes) AP("seasons/" + b.getAttribute("data-end") + "/end").then(function () { M.toast("Сезон завершён"); M.render(); }).catch(fail);
          });
        };
      });
    }).catch(M.fail);
  });

  // =========================================================
  // Магазин
  // =========================================================

  M.screen("arena_shop", function () {
    A("items").then(function (rows) {
      M.state.cache.arenaItems = rows;
      var html = M.backButton() + '<div class="dim" style="margin-bottom:8px">Цены и доступность, изменённые здесь, не сбросятся при обновлении арены.</div>'
        + '<div class="card">' + rows.map(function (i) {
            return '<div class="setting"><div class="grow"><div class="t">' + esc(i.name) + (i.overridden ? ' <span class="tag">изменено</span>' : "") + '</div><div class="s">'
              + (KIND[i.kind] || i.kind) + " · " + (i.price ? num(i.price) + " " + CUR_SHORT[i.currency] : "бесплатно") + " · у " + num(i.owners) + " игр.</div></div>"
              + '<button class="btn" data-edit="' + esc(i.key) + '" style="margin-right:8px">✏️</button>'
              + '<div class="switch' + (i.isActive ? " on" : "") + '" data-active="' + esc(i.key) + '"></div></div>';
          }).join("") + "</div>";
      M.app.innerHTML = html;
      M.bind();

      M.each("[data-active]", function (el) {
        el.onclick = function () {
          var next = !el.classList.contains("on");
          el.classList.toggle("on", next);
          AP("items/" + el.getAttribute("data-active"), { isActive: next }).then(function () { M.toast(next ? "В продаже" : "Снято с продажи"); }).catch(function (e) { el.classList.toggle("on", !next); fail(e); });
        };
      });
      M.each("[data-edit]", function (b) {
        b.onclick = function () {
          var item = rows.filter(function (i) { return i.key === b.getAttribute("data-edit"); })[0];
          form(item.name, [
            { name: "name", label: "Название", value: item.name },
            { name: "price", type: "number", label: "Цена (0 — бесплатно)", value: item.price },
            { name: "currency", type: "chips", label: "Валюта", options: [["CREDITS", CUR.CREDITS], ["COINS", CUR.COINS]], value: item.currency }
          ], "Сохранить").then(function (v) {
            if (!v) return;
            AP("items/" + item.key, { name: v.name, price: parseInt(v.price, 10) || 0, currency: v.currency }).then(function () { M.toast("Сохранено"); M.render(); }).catch(fail);
          });
        };
      });
    }).catch(M.fail);
  });

  // =========================================================
  // Рассылка игрокам
  // =========================================================

  M.screen("arena_broadcast", function () {
    var audience = "active30";
    M.app.innerHTML = M.backButton()
      + '<div class="card"><div class="card-title">Сообщение от бота в личку игрокам Арены</div>'
      + '<textarea data-text maxlength="3500" placeholder="Например: сегодня в 20:00 турнир с призовым фондом 100K!"></textarea>'
      + '<div class="dim" style="margin:10px 0 6px">Кому</div><div class="chips" data-aud>'
      + [["active7", "Активным за неделю"], ["active30", "Активным за месяц"], ["all", "Всем"]].map(function (a) {
          return '<span class="chip' + (a[0] === audience ? " on" : "") + '" data-a="' + a[0] + '">' + a[1] + "</span>";
        }).join("") + "</div>"
      + '<div class="setting"><div class="grow"><div class="t">Кнопка «🃏 Играть»</div><div class="s">Открывает Арену</div></div><div class="switch on" data-button></div></div>'
      + '<div class="dim" data-count style="margin:8px 0">Считаю получателей…</div>'
      + '<button class="btn primary block" data-send>Отправить</button></div>'
      + '<div class="dim">Бот отправляет ~20 сообщений в секунду. Забаненным не отправляется.</div>';
    M.bind();

    var count = M.app.querySelector("[data-count]");
    var button = M.app.querySelector("[data-button]");
    var recount = function () {
      count.textContent = "Считаю получателей…";
      AP("broadcast", { text: "-", audience: audience, dryRun: true }).then(function (r) { count.textContent = "Получателей: " + num(r.recipients); }).catch(function (e) { count.textContent = e.message; });
    };
    M.each("[data-a]", function (el) {
      el.onclick = function () {
        audience = el.getAttribute("data-a");
        M.each("[data-a]", function (o) { o.classList.toggle("on", o === el); });
        recount();
      };
    });
    button.onclick = function () { button.classList.toggle("on"); };
    M.app.querySelector("[data-send]").onclick = function () {
      var text = M.app.querySelector("[data-text]").value.trim();
      if (!text) return M.toast("Напишите сообщение");
      M.confirm("Отправить рассылку?", count.textContent + ". Отменить после отправки нельзя.", "Отправить").then(function (yes) {
        if (!yes) return;
        AP("broadcast", { text: text, audience: audience, button: button.classList.contains("on") }).then(function (r) {
          M.toast("Поставлено в очередь: " + num(r.recipients));
          M.back();
        }).catch(fail);
      });
    };
    recount();
  });

  // =========================================================
  // Правила экономики (только чтение)
  // =========================================================

  M.screen("arena_settings", function () {
    A("settings").then(function (s) {
      M.app.innerHTML = M.backButton()
        + '<div class="card">'
        + '<div class="kv"><span class="k">Бонус за регистрацию</span><span>🪙 ' + num(s.signupBonus) + "</span></div>"
        + '<div class="kv"><span class="k">Комиссия с банка</span><span>' + s.rakePercent + "%</span></div>"
        + '<div class="kv"><span class="k">Бесплатные кредиты</span><span>🪙 ' + num(s.dailyCredits.amount) + " раз в сутки, если меньше " + num(s.dailyCredits.belowBalance) + "</span></div>"
        + '<div class="kv"><span class="k">Вернуть карту</span><span>🟡 ' + s.featurePrices.undo + "</span></div>"
        + '<div class="kv"><span class="k">Напомнить отбой</span><span>🟡 ' + s.featurePrices.discardReminder + "</span></div>"
        + '<div class="kv"><span class="k">Подсветка карт</span><span>🟡 ' + s.featurePrices.hints + "</span></div>"
        + '<div class="kv"><span class="k">Ставки</span><span>' + s.stakes.map(short).join(" · ") + "</span></div>"
        + '<div class="kv"><span class="k">На «Готов» в турнире</span><span>' + s.readySeconds + " с</span></div>"
        + '<div class="kv"><span class="k">Бот / приложение</span><span>@' + esc(s.botUsername) + " / " + esc(s.miniApp || "—") + "</span></div>"
        + "</div>"
        + '<div class="dim">Бонус, комиссия и время на «Готов» меняются переменными арены в Railway (SIGNUP_BONUS_CREDITS, RAKE_PERCENT, MATCH_READY_SECONDS).</div>';
      M.bind();
    }).catch(M.fail);
  });
})();
