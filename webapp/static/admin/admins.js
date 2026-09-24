/* ===========================================================
   Администраторы и группы: роли, карточка группы.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;
  var CATEGORY_TITLES = M.CATEGORY_TITLES, settingsMap = M.settingsMap, needChatScreen = M.needChatScreen;

  // =========================================================
  // РОЛИ
  // =========================================================

  M.screen("roles", function () {
    if (!M.state.chat) {
      M.app.innerHTML = M.backButton() + M.chatPicker(false) + '<div class="center muted">Роли назначаются в каждой группе — выбери группу.</div>';
      M.bind();
      return;
    }

    M.api("/api/admin/roles" + M.chatQuery()).then(function (d) {
      var canEdit = M.can("roles");

      var html = M.backButton() + M.chatPicker(false)
        + '<div class="dim" style="margin-bottom:10px">Если роль не назначена, она берётся из Telegram: создатель — главный админ, остальные админы — модераторы.</div>';

      d.admins.forEach(function (a) {
        html += '<div class="list-item">' + M.avatar(a.telegram_id, a.name, "sm")
          + '<div class="grow"><div class="t">' + esc(a.name) + '</div><div class="s">'
          + (a.status === "creator" ? "Создатель группы" : "Администратор") + (a.explicit ? "" : " · по правам Telegram") + "</div>"
          + (canEdit && a.status !== "creator"
              ? '<select data-role="' + a.telegram_id + '" style="margin-top:8px"><option value="">По правам Telegram</option>'
                + d.roles.map(function (r) { return '<option value="' + r.key + '"' + (a.explicit && a.role === r.key ? " selected" : "") + ">" + r.emoji + " " + esc(r.title) + " — " + esc(r.hint) + "</option>"; }).join("") + "</select>"
              : '<span class="tag" style="margin-top:6px">' + esc((d.roles.filter(function (r) { return r.key === a.role; })[0] || { title: a.role || "—" }).title) + "</span>")
          + "</div></div>";
      });

      M.app.innerHTML = html;
      M.bind();

      each("[data-role]", function (sel) {
        sel.onchange = function () {
          M.post("/api/admin/roles", { chat_id: M.state.chat, user_id: parseInt(sel.getAttribute("data-role"), 10), role: sel.value || null })
            .then(function () { M.toast("Роль сохранена"); })
            .catch(function (e) { M.toast(e.message); });
        };
      });
    }).catch(M.fail);
  });

  // =========================================================
  // ГРУППЫ
  // =========================================================

  M.screen("groups", function () {
    var chats = M.state.session.chats;

    M.app.innerHTML = M.backButton()
      + (chats.length ? chats.map(function (c) {
          return '<div class="list-item tap" data-open="group" data-arg="' + c.chat_id + '">'
            + '<div class="avatar" data-img="/api/admin/chat_photo?chat_id=' + c.chat_id + '">' + esc(c.title.slice(0, 1)) + "</div>"
            + '<div class="grow"><div class="t">' + esc(c.title) + '</div><div class="s">' + c.members + " участников · " + M.ago(c.last_seen) + "</div></div>"
            + '<span class="tag ' + (c.active ? "ok" : "") + '">' + (c.active ? "активна" : "тихо") + '</span>' + M.chev() + '</div>';
        }).join("") : '<div class="center muted">Нет групп</div>');

    M.bind();
  });

  M.screen("group", function (chatId) {
    var c = M.state.session.chats.filter(function (x) { return String(x.chat_id) === String(chatId); })[0];
    if (!c) { M.fail({ message: "Группа не найдена" }); return; }

    M.app.innerHTML = M.backButton("Группы")
      + '<div class="card glow profile-hero"><div class="avatar xl" style="margin:0 auto" data-img="/api/admin/chat_photo?chat_id=' + c.chat_id + '">' + esc(c.title.slice(0, 1)) + "</div>"
      + "<h2>" + esc(c.title) + '</h2><div class="dim">' + c.members + " участников</div></div>"
      + '<div class="card"><div class="card-title">Чат</div><div class="dim" data-lock-state style="margin-bottom:10px">Проверяю…</div>'
      + '<div class="btns"><button class="btn" data-lock="1">🔒 Закрыть</button><button class="btn" data-lock="0">🔓 Открыть</button></div></div>'
      + '<div class="card"><div class="card-title">Название</div>'
      + '<div class="row-gap"><input data-title value="' + esc(c.title) + '" maxlength="128"><button class="btn" data-save-title>💾</button></div>'
      + '<div class="dim" style="margin-top:6px">Нужно право Мары «Изменение профиля группы».</div></div>'
      + '<div class="btns"><button class="btn" data-pick-chat>✅ Работать с этой группой</button><button class="btn" data-open="roles">👑 Роли</button></div>';

    M.bind();

    var state = M.app.querySelector("[data-lock-state]");
    var show = function (l) { state.textContent = l == null ? "Не удалось узнать — у Мары может не быть прав" : (l ? "Сейчас: 🔒 закрыт, пишут только админы" : "Сейчас: 🔓 открыт"); };

    M.api("/api/admin/chat_lock?chat_id=" + c.chat_id).then(function (d) { show(d.locked); }).catch(function () { show(null); });

    each("[data-lock]", function (btn) {
      btn.onclick = function () {
        var locked = btn.getAttribute("data-lock") === "1";
        var go = function () {
          M.post("/api/admin/chat_lock", { chat_id: c.chat_id, locked: locked })
            .then(function () { show(locked); M.toast(locked ? "Чат закрыт" : "Чат открыт"); })
            .catch(function (e) { M.toast(e.message); });
        };
        if (locked) M.confirm("Закрыть чат?", "Писать смогут только администраторы.", "Закрыть", true).then(function (y) { if (y) go(); });
        else go();
      };
    });

    M.app.querySelector("[data-save-title]").onclick = function () {
      var title = M.app.querySelector("[data-title]").value.trim();
      if (!title || title === c.title) { M.toast("Название не изменилось"); return; }

      M.post("/api/admin/group/title", { chat_id: c.chat_id, title: title })
        .then(function () { c.title = title; M.toast("Группа переименована"); M.render(); })
        .catch(function (e) { M.toast(e.message); });
    };

    M.app.querySelector("[data-pick-chat]").onclick = function () {
      M.state.stack = [];
      M.setChat(String(c.chat_id));
      M.switchTab("home");
    };
  });
})();
