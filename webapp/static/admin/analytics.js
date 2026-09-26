/* ===========================================================
   Аналитика: периоды, часы, разделы, тепловая карта.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;
  var CATEGORY_TITLES = M.CATEGORY_TITLES, settingsMap = M.settingsMap, needChatScreen = M.needChatScreen;

  // =========================================================
  // АНАЛИТИКА
  // =========================================================

  function delta(change) {
    if (change === null || change === undefined) return "";
    var up = change >= 0;
    return ' <span style="font-size:12px;font-weight:700;color:' + (up ? "var(--green)" : "var(--red)") + '">' + (up ? "↑ +" : "↓ ") + change + "%</span>";
  }

  function hourBars(hours) {
    var top = Math.max.apply(null, hours.concat([1]));
    var peak = hours.indexOf(Math.max.apply(null, hours));

    return '<div style="display:flex;align-items:flex-end;gap:3px;height:110px;margin-top:6px">'
      + hours.map(function (v, h) {
          var height = Math.max(3, Math.round(v * 100 / top));
          return '<div title="' + h + ':00 — ' + v + '" style="flex:1;height:' + height + '%;border-radius:4px 4px 0 0;background:'
            + (h === peak && v ? "linear-gradient(180deg,#e9d5ff,#c084fc)" : "linear-gradient(180deg,#8b5cf6,#5b3aa8)") + '"></div>';
        }).join("") + "</div>"
      + '<div class="row-gap dim" style="justify-content:space-between;margin-top:4px"><span>00</span><span>06</span><span>12</span><span>18</span><span>23</span></div>'
      + (hours[peak] ? '<div class="dim" style="margin-top:6px">Пик — около ' + peak + ":00 UTC</div>" : "");
  }

  M.screen("analytics", function () {
    var days = M.state.cache.days || 7;

    Promise.all([
      M.api("/api/admin/analytics" + M.chatQuery() + "&days=" + days),
      M.api("/api/admin/heatmap" + M.chatQuery())
    ]).then(function (res) {
      var a = res[0], grid = res[1].grid, c = a.current, ch = a.change, e = a.economy;
      var chip = function (n, label) { return '<span class="chip' + (days === n ? " on" : "") + '" data-days="' + n + '">' + label + "</span>"; };
      var kv = function (label, value, change) { return '<div class="kv"><span class="k">' + label + "</span><span>" + value + (change !== undefined ? delta(change) : "") + "</span></div>"; };

      var top = Math.max.apply(null, [].concat.apply([1], grid));
      var names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
      var heat = '<div class="heat"><span></span>' + Array.apply(null, Array(24)).map(function (_, h) { return "<span>" + (h % 6 ? "" : h) + "</span>"; }).join("");
      grid.forEach(function (row, day) {
        heat += "<span>" + names[day] + "</span>" + row.map(function (v) {
          return '<div class="cell" style="' + (v ? "background:rgba(192,132,252," + (0.15 + 0.85 * v / top).toFixed(2) + ")" : "") + '"></div>';
        }).join("");
      });
      heat += "</div>";

      var reason = function (key) { return (e.by_reason.filter(function (r) { return r.reason === key; })[0] || { total: 0, count: 0 }); };
      var rewards = Math.abs(reason("game_win").total) + Math.abs(reason("game_host").total);

      M.app.innerHTML = M.backButton() + M.chatPicker()
        + '<div class="chips">' + chip(1, "Сегодня") + chip(7, "7 дней") + chip(30, "30 дней") + "</div>"

        + '<div class="card glow"><div class="dim">Сообщения</div>'
        + '<div style="font-size:28px;font-weight:800">' + num(c.messages) + delta(ch.messages) + "</div>"
        + (days > 1 ? M.chart(a.series, "messages") : "") + "</div>"

        + '<div class="metrics">'
        + M.metric("👥", "+" + num(c.new_users), "Новых участников", "", "rgba(52,211,153,.18)")
        + M.metric("⚠️", num(c.warnings), "Нарушений", "", "rgba(248,113,113,.18)")
        + M.metric("⚡", num(c.actions), "Actions")
        + M.metric("🤖", num(c.ai_requests), "AI-запросов", "", "rgba(96,165,250,.18)")
        + "</div>"

        + '<div class="card"><div class="card-title">Активность по времени</div>' + hourBars(a.hours) + "</div>"

        + '<div class="card"><div class="card-title">Активность</div>'
        + kv("Сообщений", num(c.messages), ch.messages)
        + kv("Активных (сумма по дням)", num(c.active_users), ch.active_users)
        + kv("Новых участников", num(c.new_users), ch.new_users)
        + kv("Возвращающихся", num(a.returning))
        + "</div>"

        + '<div class="card"><div class="card-title">Маруська</div>'
        + kv("Actions", num(c.actions), ch.actions)
        + kv("Картинок отправлено", num(c.images), ch.images)
        + kv("AI-ответов", num(c.ai_requests), ch.ai_requests)
        + kv("Команд", num(c.commands), ch.commands)
        + kv("Автоответов", num(c.autoreplies), ch.autoreplies)
        + "</div>"

        + '<div class="card"><div class="card-title">Экономика</div>'
        + kv("Выдано 💎", '<span style="color:var(--green)">+' + num(e.issued) + "</span>")
        + kv("Потрачено 💎", '<span style="color:var(--red)">−' + num(e.spent) + "</span>")
        + kv("Покупок", num(reason("purchase").count))
        + kv("Подарков", num(reason("gift_out").count))
        + kv("Выдано XP", num(c.xp), ch.xp)
        + "</div>"

        + '<div class="card"><div class="card-title">Модерация</div>'
        + kv("Предупреждений", num(c.warnings), ch.warnings)
        + kv("Мутов", num(c.mutes), ch.mutes)
        + kv("Банов", num(c.bans), ch.bans)
        + kv("Удалено сообщений (антиспам)", num(c.deleted), ch.deleted)
        + "</div>"

        + '<div class="card"><div class="card-title">Игры</div>'
        + kv("Раундов", num(a.games.rounds)) + kv("Доиграно", num(a.games.finished))
        + kv("Лайков рисункам", num(a.games.likes)) + kv("Выдано наград", num(rewards) + " 💎")
        + (a.games.top.length ? '<div class="dim" style="margin:10px 0 6px">Победители</div>' + M.bars(a.games.top) : "")
        + "</div>"

        + '<div class="card"><div class="card-title">Когда чат живой <span class="dim">UTC, 4 недели</span></div>' + heat + "</div>"
        + '<div class="dim">Проценты — сравнение с таким же периодом до этого.</div>';

      M.bind();

      // Топ болтунов за сегодня — отдельным запросом, только для одной группы
      if (M.state.chat) {
        var holder = document.createElement("div");
        holder.className = "card";
        holder.innerHTML = '<div class="card-title">🗣 Болтуны сегодня</div><div class="dim">Считаю…</div>';
        var first = M.app.querySelector(".card.glow");
        if (first) first.insertAdjacentElement("afterend", holder); else M.app.appendChild(holder);

        M.api("/api/admin/chatters" + M.chatQuery()).then(function (t) {
          holder.innerHTML = '<div class="card-title">🗣 Болтуны сегодня <span class="dim">' + t.total + " сообщ. · " + t.speakers + " чел.</span></div>"
            + (t.people.length ? M.bars(t.people.map(function (p) { return { name: p.name, value: p.messages }; })) : '<div class="dim">Сегодня ещё тихо</div>');
        }).catch(function () { holder.remove(); });
      }

      each("[data-days]", function (el) { el.onclick = function () { M.state.cache.days = parseInt(el.getAttribute("data-days"), 10); M.render(); }; });
    }).catch(M.fail);
  });
})();
