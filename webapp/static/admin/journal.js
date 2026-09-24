/* ===========================================================
   Журнал событий с фильтрами.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;
  var CATEGORY_TITLES = M.CATEGORY_TITLES, settingsMap = M.settingsMap, needChatScreen = M.needChatScreen;

  // =========================================================
  // ЖУРНАЛ
  // =========================================================

  M.screen("journal", function () {
    var f = M.state.cache.jf || (M.state.cache.jf = { category: "", q: "", who: "", from: "", to: "", user: "", userName: "" });

    var query = M.chatQuery() + "&category=" + f.category + "&q=" + encodeURIComponent(f.q)
      + "&from=" + f.from + "&to=" + f.to;

    if (f.user) query += "&user_id=" + f.user;

    if (f.who === "bot" || f.who === "system" || f.who === "admin") query += "&actor_kind=" + f.who;
    else if (f.who) query += "&actor_id=" + f.who;

    M.api("/api/admin/journal" + query).then(function (d) {
      var chip = function (k, l) { return '<span class="chip' + (f.category === k ? " on" : "") + '" data-jc="' + k + '">' + l + "</span>"; };
      var active = f.q || f.who || f.from || f.to || f.user;

      // Лента с временем слева, как на макете; день — разделителем
      var lastDay = "";
      var rows = d.events.map(function (e) {
        var day = e.created_at.slice(0, 10);
        var sep = day !== lastDay ? '<div class="dim" style="margin:12px 0 4px;font-weight:700">' + M.time(e.created_at).slice(0, 5) + "</div>" : "";
        lastDay = day;
        return sep + '<div class="row-gap" style="align-items:flex-start"><span class="dim" style="width:40px;padding-top:12px">' + M.time(e.created_at).slice(6) + "</span>"
          + '<div class="grow">' + M.eventRow(e) + "</div></div>";
      }).join("");

      M.app.innerHTML = M.backButton() + M.chatPicker()
        + '<input data-jq placeholder="🔍  Имя, действие или подробности" value="' + esc(f.q) + '" style="margin-bottom:10px">'
        + '<div class="chips">' + chip("", "Все") + chip("moderation", "🛡 Модерация") + chip("economy", "💎 Экономика")
        + chip("actions", "⚡ Actions") + chip("member", "👥 Участники") + chip("settings", "⚙️ Настройки") + chip("broadcast", "📣 Рассылки") + "</div>"
        + '<div class="card"><div class="card-title">Фильтры' + (active ? ' <span class="link" data-jreset>Сбросить</span>' : "") + "</div>"
        + '<select data-jwho style="margin-bottom:8px"><option value="">Кто: все</option>'
        + '<option value="admin"' + (f.who === "admin" ? " selected" : "") + ">👤 Любой администратор</option>"
        + '<option value="bot"' + (f.who === "bot" ? " selected" : "") + ">🤖 Мара (автоматически)</option>"
        + '<option value="system"' + (f.who === "system" ? " selected" : "") + ">🗄 Система</option>"
        + d.actors.map(function (a) { return '<option value="' + a.id + '"' + (String(f.who) === String(a.id) ? " selected" : "") + ">👤 " + esc(a.name) + " · " + a.count + "</option>"; }).join("")
        + "</select>"
        + '<div class="row-gap"><input type="date" data-jfrom value="' + esc(f.from) + '"><input type="date" data-jto value="' + esc(f.to) + '"></div>'
        + (f.user
            ? '<div class="row-gap" style="margin-top:8px;align-items:center"><span class="grow">Над кем: <b>' + esc(f.userName) + '</b></span><button class="btn" data-juser-clear>×</button></div>'
            : '<input data-juser placeholder="Над кем: имя, @username или ID" style="margin-top:8px"><div data-juser-list></div>')
        + "</div>"
        + '<div class="card">' + (d.events.length ? rows : '<div class="dim">Событий нет</div>') + "</div>"
        + (d.events.length >= 150 ? '<div class="dim center">Показаны последние 150 — уточни фильтры</div>' : "");

      M.bind();

      var set = function (key, value) { f[key] = value; M.render(); };

      each("[data-jc]", function (el) { el.onclick = function () { set("category", el.getAttribute("data-jc")); }; });
      M.app.querySelector("[data-jwho]").onchange = function (e) { set("who", e.target.value); };
      M.app.querySelector("[data-jfrom]").onchange = function (e) { set("from", e.target.value); };
      M.app.querySelector("[data-jto]").onchange = function (e) { set("to", e.target.value); };

      var userInput = M.app.querySelector("[data-juser]");

      if (userInput) {
        var ut;
        userInput.oninput = function () {
          clearTimeout(ut);
          var q = userInput.value.trim();
          var box = M.app.querySelector("[data-juser-list]");
          if (q.length < 2) { box.innerHTML = ""; return; }

          ut = setTimeout(function () {
            M.api("/api/admin/search?q=" + encodeURIComponent(q)).then(function (r) {
              box.innerHTML = r.people.slice(0, 5).map(function (p) {
                return '<div class="list-item tap" data-juser-pick="' + p.telegram_id + '" data-juser-name="' + esc(p.name) + '" style="margin-top:6px">'
                  + M.avatar(p.telegram_id, p.name, "sm") + '<div class="grow t">' + esc(p.name) + "</div></div>";
              }).join("") || '<div class="dim" style="margin-top:6px">Никого</div>';
              M.loadImages(box);

              Array.prototype.forEach.call(box.querySelectorAll("[data-juser-pick]"), function (el) {
                el.onclick = function () {
                  f.user = el.getAttribute("data-juser-pick");
                  f.userName = el.getAttribute("data-juser-name");
                  M.render();
                };
              });
            });
          }, 350);
        };
      }

      var clearUser = M.app.querySelector("[data-juser-clear]");
      if (clearUser) clearUser.onclick = function () { f.user = ""; f.userName = ""; M.render(); };

      var reset = M.app.querySelector("[data-jreset]");
      if (reset) reset.onclick = function () { M.state.cache.jf = null; M.render(); };

      var input = M.app.querySelector("[data-jq]"), timer;
      input.oninput = function () { clearTimeout(timer); timer = setTimeout(function () { set("q", input.value.trim()); }, 400); };
    }).catch(M.fail);
  });
})();
