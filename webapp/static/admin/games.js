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

        + '<button class="btn primary" data-open="settings" data-arg="Развлечения">⚙️ Награды, паузы и лимиты</button>';

      M.app.innerHTML = html;
      M.bind();

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
})();
