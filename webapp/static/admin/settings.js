/* ===========================================================
   Настройки группы и меню «Ещё».
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;
  var CATEGORY_TITLES = M.CATEGORY_TITLES, settingsMap = M.settingsMap, needChatScreen = M.needChatScreen;

  // =========================================================
  // НАСТРОЙКИ (весь список или один раздел)
  // =========================================================

  var SECTION_PERMISSION = { "Общение": "content", "Сообщество": "settings", "Модерация": "moderation", "Антимат": "moderation", "Развлечения": "games" };

  M.screen("settings", function (only) {
    if (!M.state.chat) {
      M.app.innerHTML = M.backButton() + M.chatPicker(false) + '<div class="center muted">Настройки задаются для каждой группы отдельно — выбери группу.</div>';
      M.bind();
      return;
    }

    M.api("/api/admin/settings" + M.chatQuery()).then(function (d) {
      var sections = d.sections.filter(function (s) { return !only || s.name === only; });
      var index = {};

      var html = M.backButton() + M.chatPicker(false);

      sections.forEach(function (sec) {
        var editable = M.can(SECTION_PERMISSION[sec.name] || "settings");

        html += '<div class="card"><div class="card-title">' + esc(sec.name)
          + (editable ? "" : ' <span class="tag">только просмотр</span>') + "</div>";

        sec.items.forEach(function (it) {
          index[it.key] = it;
          it.editable = editable;

          html += '<div class="setting" data-key="' + it.key + '"><div class="ico">' + it.emoji + "</div>"
            + '<div class="grow"><div class="t">' + esc(it.title) + '</div><div class="s">' + esc(it.description) + "</div>";

          if (it.kind === "choice") {
            html += '<select data-choice style="margin-top:8px"' + (editable ? "" : " disabled") + ">"
              + it.options.map(function (o) {
                  return '<option value="' + o.value + '"' + (o.value === it.value ? " selected" : "") + ">" + o.emoji + " " + esc(o.label) + "</option>";
                }).join("") + "</select>";
          }

          if (it.kind === "text") {
            html += '<textarea data-text rows="3" maxlength="' + it.max_length + '" style="margin-top:8px"' + (editable ? "" : " disabled") + ">" + esc(it.value) + "</textarea>"
              + (it.placeholders.length ? '<div class="dim">Подстановки: ' + it.placeholders.map(function (p) { return "{" + p + "}"; }).join(", ") + "</div>" : "")
              + (editable ? '<button class="btn" data-save-text style="margin-top:8px">Сохранить</button>' : "");
          }

          html += "</div>";

          if (it.kind === "toggle") html += '<div class="switch' + (it.value ? " on" : "") + (editable ? "" : " locked") + '" data-toggle></div>';

          if (it.kind === "number") {
            html += '<div class="stepper"' + (editable ? "" : ' style="opacity:.5;pointer-events:none"') + '><button data-minus>−</button><div class="v">' + esc(it.label) + '</div><button data-plus>+</button></div>';
          }

          html += "</div>";
        });

        html += "</div>";
      });

      M.app.innerHTML = html;
      M.bind();

      each(".setting", function (row) {
        var it = index[row.getAttribute("data-key")];
        if (!it || !it.editable) return;

        var save = function (value, done, undo) {
          M.post("/api/admin/settings", { chat_id: M.state.chat, key: it.key, value: value })
            .then(function () { M.haptic(); M.toast("Сохранено", undo); if (done) done(); })
            .catch(function (e) { M.toast(e.message); if (undo) undo(true); });
        };

        var t = row.querySelector("[data-toggle]");
        if (t) t.onclick = function () {
          var next = !t.classList.contains("on");
          t.classList.toggle("on", next);
          save(next, null, function (silent) {
            t.classList.toggle("on", !next);
            if (!silent) M.post("/api/admin/settings", { chat_id: M.state.chat, key: it.key, value: !next });
          });
        };

        var c = row.querySelector("[data-choice]");
        if (c) c.onchange = function () { save(c.value); };

        var v = row.querySelector(".v");
        var step = function (delta) {
          var next = Math.max(it.min, Math.min(it.max, it.value + delta));
          if (next === it.value) { M.toast("Дальше некуда"); return; }
          it.value = next;
          v.textContent = next + (it.unit ? " " + it.unit : "");
          save(next);
        };
        var mi = row.querySelector("[data-minus]"), pl = row.querySelector("[data-plus]");
        if (mi) mi.onclick = function () { step(-it.step); };
        if (pl) pl.onclick = function () { step(it.step); };
        // Нажатие на число — ввести своё значение (например, 1440 минут), а не листать по шагу
        if (v && it.kind === "number") v.onclick = function () {
          if (v.querySelector("input")) return;
          var input = document.createElement("input");
          input.type = "number"; input.inputMode = "numeric";
          input.min = it.min; input.max = it.max; input.value = it.value;
          input.style.cssText = "width:90px;text-align:center;padding:4px;margin:0";
          v.textContent = ""; v.appendChild(input); input.focus(); input.select();
          var done = false;
          var finish = function () {
            if (done) return; done = true;
            var n = parseInt(input.value, 10);
            if (isNaN(n)) { v.textContent = it.value + (it.unit ? " " + it.unit : ""); return; }
            n = Math.max(it.min, Math.min(it.max, n));
            v.textContent = n + (it.unit ? " " + it.unit : "");
            if (n !== it.value) { it.value = n; save(n); }
          };
          input.onblur = finish;
          input.onkeydown = function (e) { if (e.key === "Enter") input.blur(); };
        };

        var st = row.querySelector("[data-save-text]");
        if (st) st.onclick = function () { save(row.querySelector("[data-text]").value); };
      });
    }).catch(M.fail);
  });

  // =========================================================
  // ЕЩЁ
  // =========================================================

  var MORE = [
    ["changelog", "new", "Обновления", "Что нового в Маре", false, "pink"],
    ["settings", "settings", "Все настройки", "Каждый параметр группы", false, "purple"],
    ["analytics", "chart", "Аналитика", "Графики и тепловая карта", false, "blue"],
    ["economy", "diamond", "Экономика", "Алмазы и операции", false, "gold"],
    ["games", "game", "Игры", "Крокодил, кубики, награды", false, "green"],
    ["arena", "game", "Арена", "Дурак онлайн: игроки, деньги, турниры", true, "gold"],
    ["broadcasts", "megaphone", "Рассылки", "Фото, видео, кнопки, расписание", false, "blue"],
    ["journal", "journal", "Журнал", "Кто что сделал", false, "purple"],
    ["owners", "crown", "Главные админы", "Права как у создателя", true, "gold"],
    ["roles", "crown", "Роли", "Права администраторов", false, "gold"],
    ["groups", "group", "Группы", "Где работает Мара", false, "green"],
    ["achievements", "trophy", "Достижения", "Кто что открыл", false, "gold"],
    ["shop", "bag", "Магазин", "Товары и продажи", false, "pink"],
    ["logs", "file", "Логи", "Только для владельца", true, "red"],
    ["system", "database", "Система", "Только для владельца", true, "red"]
  ];

  M.screen("more", function () {
    var owner = M.state.session.user.owner;

    M.app.innerHTML = M.header("Ещё", "Все разделы панели", "menu", "blue")
      + '<div class="menu-grid">' + MORE.filter(function (r) { return owner || !r[4]; }).map(function (r) {
          var fresh = r[0] === "changelog" && M.hasUpdate();
          return '<div class="menu-tile" data-open="' + r[0] + '">' + M.tile(r[1], r[5], 20)
            + '<div class="t">' + r[2] + (fresh ? ' <span class="tag new">новое</span>' : "") + "</div>"
            + '<div class="s">' + r[3] + "</div></div>";
        }).join("") + "</div>";

    M.bind();
  });
})();
