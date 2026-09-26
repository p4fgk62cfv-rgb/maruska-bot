/* ===========================================================
   Экономика: хаб, алмазы, XP, карма, достижения, магазин, медиа.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;
  var CATEGORY_TITLES = M.CATEGORY_TITLES, settingsMap = M.settingsMap, needChatScreen = M.needChatScreen;

  // =========================================================
  // ЭКОНОМИКА
  // =========================================================

  var REASONS = {
    daily_bonus: "Ежедневный бонус", game_win: "Победы в играх", game_host: "Ведущий в игре",
    purchase: "Покупки", gift_out: "Подарки", admin: "Правки админов", achievement: "Достижения",
    like: "Лайки рисункам", jackpot: "Джекпот", fishing: "Рыбалка", fishing_shop: "Магазин рыбалки"
  };

  function short(n) {
    var a = Math.abs(n);
    if (a >= 1e6) return (n / 1e6).toFixed(1).replace(".0", "") + "M";
    if (a >= 1e4) return (n / 1e3).toFixed(1).replace(".0", "") + "K";
    return num(n);
  }

  // ---------- массовая корректировка: общий блок ----------

  function massForm(kind) {
    if (!M.state.chat || !M.can("economy")) return "";

    var unit = { coins: "💎", xp: "XP", karma: "❤️" }[kind];

    return '<div class="card"><div class="card-title">Массовая корректировка ' + unit + "</div>"
      + '<div class="dim" style="margin-bottom:6px">Кому</div>'
      + '<div class="chips" data-aud>' + [["all", "Всем"], ["active", "Активным за неделю"], ["vip", "VIP"], ["level", "С уровня…"]].map(function (a, i) {
          return '<span class="chip' + (i === 0 ? " on" : "") + '" data-a="' + a[0] + '">' + a[1] + "</span>";
        }).join("") + "</div>"
      + '<input type="number" data-level-min min="1" placeholder="Минимальный уровень" class="hidden" style="margin-bottom:8px">'
      + '<div class="row-gap"><input type="number" data-mass-amount placeholder="Сколько (минус — списать)">'
      + '<input data-mass-note placeholder="Причина"></div>'
      + '<button class="btn block" data-mass="' + kind + '" style="margin-top:8px">Применить</button></div>';
  }

  function bindMass() {
    var audience = "all";

    each("[data-a]", function (el) {
      el.onclick = function () {
        audience = el.getAttribute("data-a");
        each("[data-a]", function (o) { o.classList.toggle("on", o === el); });
        M.app.querySelector("[data-level-min]").classList.toggle("hidden", audience !== "level");
      };
    });

    var btn = M.app.querySelector("[data-mass]");
    if (!btn) return;

    btn.onclick = function () {
      var kind = btn.getAttribute("data-mass");
      var amount = parseInt(M.app.querySelector("[data-mass-amount]").value, 10);
      if (!amount) { M.toast("Введи сумму"); return; }

      var body = {
        chat_id: M.state.chat, kind: kind, amount: amount, audience: audience,
        level_min: parseInt(M.app.querySelector("[data-level-min]").value, 10) || 1,
        note: M.app.querySelector("[data-mass-note]").value.trim()
      };

      // Сначала узнаём, скольких затронет, и только потом спрашиваем
      M.post("/api/admin/economy/mass", Object.assign({ dry_run: true }, body)).then(function (r) {
        var unit = { coins: "💎", xp: "XP", karma: "❤️" }[kind];

        return M.confirm(
          (amount > 0 ? "Начислить " : "Списать ") + Math.abs(amount) + " " + unit + "?",
          "Затронет " + r.count + " чел. Отменить одной кнопкой не получится — только обратной корректировкой.",
          "Применить", amount < 0
        ).then(function (yes) {
          if (!yes) return;
          return M.post("/api/admin/economy/mass", body).then(function (res) {
            M.haptic("medium");
            M.toast("Готово: " + res.done + " чел." + (res.skipped ? ", пропущено " + res.skipped : ""));
            M.render();
          });
        });
      }).catch(function (e) { M.toast(e.message); });
    };
  }

  // =========================================================
  // ЭКОНОМИКА — хаб
  // =========================================================

  var ECONOMY_TINTS = { "💎": "purple", "⭐": "gold", "❤️": "red", "🏆": "gold", "🛍": "pink", "⚙️": "blue" };

  M.screen("economy", function () {
    M.api("/api/admin/economy" + M.chatQuery()).then(function (d) {
      var row = function (icon, title, sub, open, arg) {
        return '<div class="list-item tap" data-open="' + open + '"' + (arg ? ' data-arg="' + arg + '"' : "") + ">" + M.glyph(icon, ECONOMY_TINTS[icon])
          + '<div class="grow"><div class="t">' + title + '</div><div class="s">' + sub + '</div></div>' + M.chev() + '</div>';
      };

      M.app.innerHTML = M.backButton() + M.chatPicker()
        + '<div class="hero" style="text-align:center"><div class="eyebrow">Экономика</div>'
        + '<div class="big">' + num(d.totals.coins) + " 💎</div>"
        + '<div class="sub">Всего в ' + (M.state.chat ? "группе" : "группах") + "</div>"
        + '<div class="row-gap" style="justify-content:center;margin-top:10px;font-weight:700">'
        + '<span style="color:var(--green)">+' + short(d.today.issued) + " сегодня</span>"
        + '<span style="color:var(--red)">−' + short(d.today.spent) + " сегодня</span></div></div>"

        + row("💎", "Алмазы", "Балансы, история, массовая корректировка", "diamonds")
        + row("⭐", "XP и уровни", "Начисление, таблица уровней", "levels")
        + row("❤️", "Карма", "Голоса и рейтинг", "karma")
        + row("🏆", "Достижения", "Условия, награды, статистика", "achievements")
        + row("🛍", "Магазин", "Цены, наличие, покупки", "shop")
        + row("⚙️", "Настройки экономики", "Бонус, джекпот, награды", "settings", "Сообщество");

      M.bind();
    }).catch(M.fail);
  });

  // ---------- алмазы ----------

  M.screen("diamonds", function () {
    var reason = M.state.cache.txReason || "";

    M.api("/api/admin/economy" + M.chatQuery() + "&reason=" + reason).then(function (d) {
      var reasons = d.week.by_reason.map(function (r) { return r.reason; });

      M.app.innerHTML = M.backButton("Экономика") + M.chatPicker()
        + '<div class="metrics">' + M.metric("💎", short(d.totals.coins), "В обороте")
        + M.metric("📈", "+" + short(d.week.issued), "Выдано за неделю", "", "rgba(52,211,153,.18)")
        + M.metric("📉", "−" + short(d.week.spent), "Потрачено за неделю", "", "rgba(248,113,113,.18)")
        + M.metric("👥", num(d.totals.people), "Владельцев") + "</div>"

        + '<div class="card"><div class="card-title">Откуда и куда за неделю</div>'
        + (d.week.by_reason.length ? d.week.by_reason.map(function (r) {
            return '<div class="kv"><span class="k">' + esc(REASONS[r.reason] || r.reason) + " · " + r.count + " раз</span>"
              + '<span style="color:' + (r.total > 0 ? "var(--green)" : "var(--red)") + '">' + (r.total > 0 ? "+" : "") + num(r.total) + "</span></div>";
          }).join("") : '<div class="dim">Операций не было</div>') + "</div>"

        + '<div class="card"><div class="card-title">Самые богатые</div>' + M.bars(d.rich, " 💎") + "</div>"

        + massForm("coins")

        + '<div class="card"><div class="card-title">История</div>'
        + '<div class="chips"><span class="chip' + (reason ? "" : " on") + '" data-r="">Все</span>'
        + reasons.map(function (r) { return '<span class="chip' + (reason === r ? " on" : "") + '" data-r="' + r + '">' + esc(REASONS[r] || r) + "</span>"; }).join("")
        + "</div>"
        + (d.history.length ? d.history.map(function (h) {
            return '<div class="kv"><span class="k">' + esc(h.name) + " · " + esc(h.note || REASONS[h.reason] || h.reason) + " · " + M.time(h.created_at) + "</span>"
              + '<span style="color:' + (h.amount > 0 ? "var(--green)" : "var(--red)") + '">' + (h.amount > 0 ? "+" : "") + h.amount + "</span></div>";
          }).join("") : '<div class="dim">Пусто</div>') + "</div>";

      M.bind();
      bindMass();
      each("[data-r]", function (el) { el.onclick = function () { M.state.cache.txReason = el.getAttribute("data-r"); M.render(); }; });
    }).catch(M.fail);
  });

  // ---------- XP и уровни ----------

  M.screen("levels", function () {
    M.api("/api/admin/levels" + M.chatQuery()).then(function (d) {
      M.app.innerHTML = M.backButton("Экономика") + M.chatPicker()
        + '<div class="card"><div class="card-title">Как начисляется опыт</div>'
        + '<div class="dim" style="margin-bottom:8px">За сообщения, Actions, победы и ведение игр, бонус и подарки. Сколько именно — в настройках.</div>'
        + '<div class="btns"><button class="btn" data-open="settings" data-arg="Сообщество">✨ За сообщения и Actions</button>'
        + '<button class="btn" data-open="settings" data-arg="Развлечения">🎮 За игры</button></div></div>'

        + '<div class="card"><div class="card-title">Лидеры по опыту</div>' + M.bars(d.top, " xp") + "</div>"

        + massForm("xp")

        + '<div class="card"><div class="card-title">Уровни</div>'
        + d.levels.map(function (l) {
            return '<div class="kv"><span class="k">Уровень ' + l.level + " · " + esc(l.title) + "</span><span>" + num(l.xp) + " xp</span></div>";
          }).join("") + "</div>";

      M.bind();
      bindMass();
    }).catch(M.fail);
  });

  // ---------- карма ----------

  M.screen("karma", function () {
    M.api("/api/admin/karma" + M.chatQuery()).then(function (d) {
      M.app.innerHTML = M.backButton("Экономика") + M.chatPicker()
        + '<div class="card"><div class="card-title">Правила</div>'
        + '<div class="dim" style="margin-bottom:8px">Карму дают ответом «+» или «−» на сообщение, за игры и вручную из профиля.</div>'
        + '<div class="btns"><button class="btn" data-open="settings" data-arg="Сообщество">⏱ Пауза между голосами</button>'
        + '<button class="btn" data-open="settings" data-arg="Развлечения">🎮 Карма за игры</button></div></div>'

        + '<div class="card"><div class="card-title">Лидеры по карме</div>' + M.bars(d.top) + "</div>"

        + massForm("karma")

        + '<div class="card"><div class="card-title">Последние голоса</div>'
        + (d.votes.length ? d.votes.map(function (v) {
            return '<div class="event"><div class="ico">' + (v.amount > 0 ? "👍" : "👎") + '</div><div class="grow"><div class="t">'
              + esc(v.giver) + " → <b>" + esc(v.target) + "</b> " + (v.amount > 0 ? "+" : "") + v.amount + '</div><div class="s">' + M.time(v.at) + "</div></div></div>";
          }).join("") : '<div class="dim">Голосов пока не было</div>') + "</div>";

      M.bind();
      bindMass();
    }).catch(M.fail);
  });

  // =========================================================
  // ДОСТИЖЕНИЯ, МАГАЗИН, МЕДИА
  // =========================================================

  M.screen("achievements", function () {
    M.api("/api/admin/achievements").then(function (d) {
      M.app.innerHTML = M.backButton() + '<div class="card">' + d.items.map(function (a) {
        return '<div class="setting"><div class="ico">' + a.emoji + '</div><div class="grow"><div class="t">' + esc(a.title) + (a.secret ? " 🔒" : "")
          + '</div><div class="s">' + esc(a.description) + " · 💎 " + a.reward + '</div></div><span class="tag">' + a.unlocked + "</span></div>";
      }).join("") + "</div>";
      M.bind();
    }).catch(M.fail);
  });

  M.screen("shop", function () {
    M.api("/api/admin/shop" + M.chatQuery()).then(function (d) {
      var canEdit = !!M.state.chat && M.can("economy");

      var html = M.backButton("Экономика") + M.chatPicker();

      if (!M.state.chat) html += '<div class="alert info"><span class="ico">💬</span><span class="grow">Цены и наличие настраиваются для каждой группы — выбери группу.</span></div>';

      d.categories.forEach(function (cat) {
        html += '<div class="card"><div class="card-title">' + esc(cat.title) + "</div>";

        cat.items.forEach(function (i) {
          var soldOut = i.stock === 0;

          html += '<div class="setting" style="align-items:flex-start;flex-wrap:wrap' + (i.enabled ? "" : ";opacity:.55") + '" data-item="' + i.key + '">'
            + '<div class="ico">' + i.emoji + "</div>"
            + '<div class="grow"><div class="t">' + esc(i.title)
            + (soldOut ? ' <span class="tag bad">нет в наличии</span>' : "")
            + (i.custom_price ? ' <span class="tag coins">своя цена</span>' : "") + "</div>"
            + '<div class="s">' + esc(i.description) + " · куплено " + i.owned + (i.gifted ? ", подарено " + i.gifted : "") + "</div>";

          if (canEdit) {
            html += '<div class="row-gap" style="margin-top:8px">'
              + '<input type="number" data-price min="1" value="' + i.price + '" placeholder="Цена" title="Цена, 💎">'
              + '<input type="number" data-stock min="0" value="' + (i.stock == null ? "" : i.stock) + '" placeholder="Склад: ∞">'
              + '<button class="btn" data-save>💾</button></div>'
              + '<div class="dim" style="margin-top:4px">В каталоге: ' + i.base_price + " 💎 · пусто в складе — без ограничений</div>";
          } else {
            html += '<div style="margin-top:6px"><span class="tag coins">💎 ' + num(i.price) + "</span>"
              + (i.stock != null ? ' <span class="tag">склад ' + i.stock + "</span>" : "") + "</div>";
          }

          html += "</div>"
            + (canEdit ? '<div class="switch' + (i.enabled ? " on" : "") + '" data-enabled title="В продаже"></div>' : "")
            + "</div>";
        });

        html += "</div>";
      });

      html += '<div class="card"><div class="card-title">Последние покупки</div>'
        + (d.purchases.length ? d.purchases.map(function (p) {
            return '<div class="kv"><span class="k">' + (p.gift ? "🎁 " : "🛍 ") + esc(p.name) + " · " + esc(p.note || "") + " · " + M.time(p.at) + "</span><span>" + p.amount + " 💎</span></div>";
          }).join("") : '<div class="dim">Покупок пока не было</div>') + "</div>";

      M.app.innerHTML = html;
      M.bind();

      if (!canEdit) return;

      each("[data-item]", function (row) {
        var key = row.getAttribute("data-item");
        var sw = row.querySelector("[data-enabled]");

        var save = function (enabled) {
          var price = row.querySelector("[data-price]").value;
          var stock = row.querySelector("[data-stock]").value;

          return M.post("/api/admin/shop/item", {
            chat_id: M.state.chat, key: key,
            price: price === "" ? null : parseInt(price, 10),
            stock: stock === "" ? null : parseInt(stock, 10),
            enabled: enabled
          });
        };

        row.querySelector("[data-save]").onclick = function () {
          save(sw.classList.contains("on")).then(function () { M.haptic(); M.toast("Сохранено"); M.render(); })
            .catch(function (e) { M.toast(e.message); });
        };

        sw.onclick = function () {
          var next = !sw.classList.contains("on");
          sw.classList.toggle("on", next);
          save(next).then(function () { M.toast(next ? "В продаже" : "Снят с продажи"); M.render(); })
            .catch(function (e) { sw.classList.toggle("on", !next); M.toast(e.message); });
        };
      });
    }).catch(M.fail);
  });

  M.screen("media", function () {
    M.api("/api/admin/media").then(function (d) {
      M.app.innerHTML = M.backButton() + '<div class="card"><div class="card-title">Коллекции картинок</div>'
        + (d.collections.length ? d.collections.map(function (r) {
            return '<div class="kv"><span>' + esc(r.collection.split("#")[0]) + '</span><span class="muted">' + r.total + " · в Telegram " + r.cached + "</span></div>";
          }).join("") : '<div class="dim">Пока ничего</div>') + "</div>";
      M.bind();
    }).catch(M.fail);
  });
})();
