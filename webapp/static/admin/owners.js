/* ===========================================================
   👑 Главные админы: люди с такими же полными правами, как у создателя.
   Назначают и снимают создатель и сами главные админы; создателя
   (OWNER_IDS) не снять никому.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc;

  function letter(name) {
    return '<div class="avatar">' + esc(String(name || "?").replace("@", "").slice(0, 1).toUpperCase()) + "</div>";
  }

  M.screen("owners", function () {
    M.app.innerHTML = M.backButton() + '<div class="dim">Загружаю…</div>';

    M.api("/api/admin/owners").then(function (data) {
      M.app.innerHTML = M.backButton()
        + '<div class="card"><div class="card-title">Добавить главного админа</div>'
        + '<div class="dim" style="margin-bottom:8px">Получит все права, как у создателя: все группы, все разделы панели, Арена, логи и система, в том числе назначать и снимать главных админов. Убрать создателя не сможет никто.</div>'
        + '<input data-user placeholder="Telegram ID или @username">'
        + '<button class="btn primary block" data-add style="margin-top:10px">Назначить</button>'
        + '<div class="dim" style="margin-top:8px">По @username найдётся тот, кто уже писал боту или есть в его группах. Свой ID человек узнает командой /myid.</div></div>'

        + '<div class="card"><div class="card-title">Главные админы · ' + data.admins.length + "</div>"
        + (data.admins.length ? data.admins.map(function (a) {
            return '<div class="list-item">' + letter(a.name)
              + '<div class="grow"><div class="t">⭐ ' + esc(a.name) + "</div>"
              + '<div class="s">' + (a.username ? "@" + esc(a.username) + " · " : "") + "ID " + esc(a.id)
              + (a.created_at ? " · с " + M.time(a.created_at) : "") + "</div></div>"
              + '<button class="btn danger" data-remove="' + esc(a.id) + '" data-name="' + esc(a.name) + '">Снять</button></div>';
          }).join("") : '<div class="center muted">Пока никого — права есть только у создателя</div>')
        + "</div>"

        + '<div class="card"><div class="card-title">Создатель</div>'
        + data.creators.map(function (c) {
            return '<div class="list-item">' + letter(c.name)
              + '<div class="grow"><div class="t">👑 ' + esc(c.name) + "</div>"
              + '<div class="s">' + (c.username ? "@" + esc(c.username) + " · " : "") + "ID " + esc(c.id) + "</div></div></div>";
          }).join("")
        + '<div class="dim" style="margin-top:6px">Создатель задаётся переменной OWNER_IDS в Railway — из панели его не снять.</div></div>';
      M.bind();

      var input = M.app.querySelector("[data-user]");
      var add = function () {
        var value = input.value.trim();
        if (!value) return M.toast("Укажите Telegram ID или @username");
        M.confirm("Назначить главным админом?", value + " получит все права в боте, как у создателя.", "Назначить").then(function (yes) {
          if (!yes) return;
          M.post("/api/admin/owners", { user: value }).then(function (r) {
            M.toast("Назначен: " + r.admin.name);
            M.render();
          }).catch(function (e) { M.toast(e.message || "Не получилось"); });
        });
      };
      M.app.querySelector("[data-add]").onclick = add;
      input.onkeydown = function (e) { if (e.key === "Enter") add(); };

      M.each("[data-remove]", function (btn) {
        btn.onclick = function () {
          var name = btn.getAttribute("data-name");
          M.confirm("Снять главного админа?", name + " потеряет права создателя. Права админа в своих группах у него останутся.", "Снять", true).then(function (yes) {
            if (!yes) return;
            M.post("/api/admin/owners/" + btn.getAttribute("data-remove") + "/remove", {}).then(function () {
              M.toast("Снят: " + name);
              M.render();
            }).catch(function (e) { M.toast(e.message || "Не получилось"); });
          });
        };
      });
    }).catch(M.fail);
  });
})();
