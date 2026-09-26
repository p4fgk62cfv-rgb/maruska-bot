/* ===========================================================
   Игры: Крокодил и мини-игры.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;
  var CATEGORY_TITLES = M.CATEGORY_TITLES, settingsMap = M.settingsMap, needChatScreen = M.needChatScreen;

  // =========================================================
  // ИГРЫ
  // =========================================================

  M.screen("games", function () {
    Promise.all([M.api("/api/admin/games" + M.chatQuery()), M.state.chat ? settingsMap() : Promise.resolve(null)]).then(function (res) {
      var g = res[0], m = res[1];
      var canEdit = !!m && M.can("games");
      var st = g.crocodile.stats, rules = g.crocodile.rules;

      var toggle = function (key, title, sub) {
        if (!m) return "";
        var on = m[key].value;
        return '<div class="setting"><div class="ico">' + m[key].emoji + '</div><div class="grow"><div class="t">' + title + '</div><div class="s">' + sub + "</div></div>"
          + '<div class="switch' + (on ? " on" : "") + (canEdit ? "" : " locked") + '" data-g="' + key + '"></div></div>';
      };

      var html = M.backButton() + M.chatPicker();

      if (m) {
        html += '<div class="card glow">' + toggle("games", "Игры в группе", m.games.value ? "Включены" : "Выключены — ни одна игра не работает") + "</div>";
      }

      html += '<div class="list-item tap card" data-open="fishing" style="margin-bottom:12px">'
        + '<span style="font-size:26px;width:38px;text-align:center">🎣</span><div class="grow"><div class="t">Рыбалка</div>'
        + '<div class="s">Мини-приложение: награды, лимиты, рекорды, шансы рыб</div></div><span class="chev">›</span></div>'
        + (m ? '<div class="card">' + toggle("fishing", "Рыбалка в группе", "/fishing — игра, /fishtop — топ рыбаков")
          + toggle("fishing_announce", "Объявлять крупный улов", "Трофейная, легендарная и мифическая рыба — в чат") + "</div>" : "");

      html += '<div class="card"><div class="card-title">🐊 Крокодил</div>'
        + toggle("game_crocodile", "Включён", "/croc — объясняй или рисуй, остальные угадывают")
        + '<div class="metrics three" style="margin-top:10px">' + M.metric("🎮", num(st.rounds), "Раундов за 30 дн") + M.metric("🏁", num(st.finished), "Доиграно") + M.metric("👍", num(st.likes), "Лайков") + "</div>"
        + (rules ? '<div class="kv"><span class="k">Победителю</span><span>' + rules.win_prize + " 💎 · " + rules.xp_win + " xp · +" + rules.karma + " ❤️</span></div>"
          + '<div class="kv"><span class="k">Ведущему</span><span>' + rules.host_prize + " 💎 · " + rules.xp_host + " xp · +" + rules.karma + " ❤️</span></div>" : "")
        + (m ? '<div class="kv"><span class="k">Подсказки</span><span>пауза ' + m.hint_cooldown.label + " · до " + m.hint_max_percent.label + " букв</span></div>" : "")
        + (st.top.length ? '<div style="margin-top:10px"><div class="dim" style="margin-bottom:6px">Чаще всех угадывают</div>' + M.bars(st.top) + "</div>" : "")
        + "</div>"

        + '<div class="card"><div class="card-title">🎲 Кубики и рандом</div>'
        + toggle("game_dice", "Включены", "Кубики, монетка, выбор, шар судьбы")
        + (m ? '<div class="kv"><span class="k">Пауза для одного человека</span><span>' + (m.dice_cooldown.value ? m.dice_cooldown.label : "нет") + "</span></div>" : "")
        + g.minigames.map(function (x) {
            return '<div class="kv"><span class="k">' + x.emoji + " " + esc(x.title) + ' <span class="dim">' + esc(x.example) + "</span></span><span>" + x.week + " за неделю · " + x.month + " за месяц</span></div>";
          }).join("") + "</div>"

        + (M.state.chat ? '<div class="card" data-social><div class="card-title">💞 Пара дня и браки</div><div class="dim">Загружаю…</div></div>' : "")
        + '<button class="btn primary" data-open="settings" data-arg="Развлечения">⚙️ Награды, паузы и лимиты</button>'
        + '<button class="btn block" data-open="settings" data-arg="Сообщество" style="margin-top:8px">💍 Настройки пары дня и браков</button>';

      M.app.innerHTML = html;
      M.bind();

      var social = M.app.querySelector("[data-social]");
      if (social) {
        var drawSocial = function () {
          M.api("/api/admin/social" + M.chatQuery()).then(function (d) {
            var now = Date.now();
            social.innerHTML = '<div class="card-title">💞 Пара дня и браки</div>'
              + '<div class="kv"><span class="k">Пара дня сегодня</span><span>' + (d.pair ? esc(d.pair.a) + " 💞 " + esc(d.pair.b) : "ещё не выбрана") + "</span></div>"
              + '<div class="dim" style="margin:10px 0 6px">Браки: ' + d.marriages.length + "</div>"
              + (d.marriages.length ? d.marriages.map(function (m) {
                  var days = Math.max(1, Math.floor((now - new Date(m.since + "Z").getTime()) / 86400000) + 1);
                  return '<div class="list-item"><div class="grow"><div class="t">' + esc(m.name1) + " 💞 " + esc(m.name2) + '</div><div class="s">вместе ' + days + " дн.</div></div>"
                    + (M.can("moderation") ? '<button class="btn danger" data-unmarry="' + m.user1 + '" data-names="' + esc(m.name1 + " и " + m.name2) + '">Развести</button>' : "") + "</div>";
                }).join("") : '<div class="dim">Пар пока нет</div>');

            M.each("[data-unmarry]", function (b) {
              b.onclick = function () {
                M.confirm("Развести " + b.getAttribute("data-names") + "?", "Брак будет расторгнут без согласия пары.", "Развести", true).then(function (yes) {
                  if (!yes) return;
                  M.post("/api/admin/social", { chat_id: M.state.chat, user_id: parseInt(b.getAttribute("data-unmarry"), 10) })
                    .then(function () { M.toast("Разведены"); drawSocial(); }).catch(function (e) { M.toast(e.message); });
                });
              };
            });
          }).catch(function () { social.remove(); });
        };
        drawSocial();
      }

      each("[data-g]", function (el) {
        if (!canEdit) return;
        el.onclick = function () {
          var next = !el.classList.contains("on");
          el.classList.toggle("on", next);
          M.saveSetting(el.getAttribute("data-g"), next, next ? "Включено" : "Выключено")
            .catch(function () { el.classList.toggle("on", !next); });
        };
      });
    }).catch(M.fail);
  });

  // =========================================================
  // РЫБАЛКА
  // =========================================================

  M.screen("fishing", function () {
    M.api("/api/admin/fishing").then(function (d) {
      var s = d.settings, t = d.today;

      var field = function (key, title, sub, unit) {
        return '<div class="setting"><div class="grow"><div class="t">' + title + '</div><div class="s">' + sub + "</div></div>"
          + (d.owner ? '<input data-fs="' + key + '" type="number" value="' + s[key] + '" style="width:90px;text-align:right">'
                     : "<b>" + s[key] + "</b>") + '<span class="dim" style="margin-left:6px">' + (unit || "") + "</span></div>";
      };

      var html = '<div class="metrics three">'
        + M.metric("🎣", num(t.catches), "Улов сегодня") + M.metric("💎", num(t.diamonds), "Алмазов сегодня")
        + M.metric("👥", num(t.anglers), "Рыбаков сегодня") + "</div>"
        + '<div class="dim" style="margin:6px 0 12px">Всего игроков: ' + num(d.players) + " · поймано рыб: " + num(d.total_catches) + "</div>"

        + '<div class="card"><div class="card-title">⚙️ Награды и защита экономики</div>'
        + '<div class="setting"><div class="grow"><div class="t">Рыбалка включена</div><div class="s">Для всех групп и лички</div></div>'
        + '<div class="switch' + (s.enabled ? " on" : "") + (d.owner ? "" : " locked") + '" data-fs-on></div></div>'
        + field("reward_percent", "Алмазы за рыбу", "Процент от цен игры (там до 3000 за рыбу)", "%")
        + field("xp_percent", "Опыт за рыбу", "Процент от опыта игры", "%")
        + field("daily_cap", "Потолок в сутки", "Сколько алмазов с рыбалки можно получить за день. 0 — без потолка", "💎")
        + field("cooldown", "Пауза между забросами", "Защита от автокликеров", "сек")
        + field("min_fight", "Минимум вываживания", "Быстрее рыбу не вытащить", "сек")
        + (d.owner ? '<button class="btn primary block" data-fs-save style="margin-top:10px">💾 Сохранить</button>'
                   : '<div class="dim" style="margin-top:8px">Меняет только владелец бота</div>')
        + "</div>";

      html += '<div class="card"><div class="card-title">🏆 Лучшие рыбаки</div>'
        + (d.top.length ? d.top.map(function (p, i) {
            return '<div class="kv"><span class="k">' + (i + 1) + ". " + esc(p.name) + "</span><span>" + p.best + " кг · " + p.catches + " рыб</span></div>";
          }).join("") : '<div class="dim">Пока никто не рыбачил</div>') + "</div>";

      html += '<div class="card"><div class="card-title">📏 Рекорды по видам</div>'
        + (d.records.length ? d.records.map(function (r) {
            return '<div class="kv"><span class="k">' + esc(r.name) + ' <span class="dim">' + esc(r.rarity) + "</span></span><span>" + r.best + " кг · " + r.count + " шт</span></div>";
          }).join("") : '<div class="dim">Рекордов пока нет</div>') + "</div>";

      html += '<div class="card"><div class="card-title">🕐 Последний улов</div>'
        + (d.recent.length ? d.recent.map(function (r) {
            return '<div class="kv"><span class="k">' + esc(r.name) + " · " + esc(r.fish) + (r.trophy ? " 👑" : "") + '</span><span>' + r.weight + " кг · +" + r.reward + " 💎 · " + M.ago(r.at) + "</span></div>";
          }).join("") : '<div class="dim">Улова пока нет</div>') + "</div>";

      html += '<div class="card"><div class="card-title">🎲 Шансы рыб (червь, простая удочка)</div>'
        + '<div class="dim" style="margin-bottom:8px">Наживка поднимает шанс «своих» рыб, сильная удочка — чуть поднимает редких.</div>'
        + Object.keys(d.chances).map(function (k) {
            var loc = d.chances[k];
            return '<div style="margin-bottom:10px"><b>' + esc(loc.name) + '</b> <span class="dim">с ' + loc.level + " ур.</span>"
              + loc.fish.map(function (f) { return '<div class="kv"><span class="k">' + esc(f.name) + ' <span class="dim">' + esc(f.rarity) + "</span></span><span>" + f.chance + "%</span></div>"; }).join("")
              + "</div>";
          }).join("") + "</div>";

      M.app.innerHTML = M.backButton("Игры") + html;
      M.bind();

      if (!d.owner) return;

      var enabled = !!s.enabled;
      var sw = M.app.querySelector("[data-fs-on]");
      sw.onclick = function () { enabled = !enabled; sw.classList.toggle("on", enabled); };

      M.app.querySelector("[data-fs-save]").onclick = function () {
        var body = { enabled: enabled };
        M.each("[data-fs]", function (el) { body[el.getAttribute("data-fs")] = parseInt(el.value, 10) || 0; });
        M.post("/api/admin/fishing", body).then(function () { M.toast("Сохранено"); M.render(); })
          .catch(function (e) { M.toast(e.message); });
      };
    }).catch(M.fail);
  });
})();
