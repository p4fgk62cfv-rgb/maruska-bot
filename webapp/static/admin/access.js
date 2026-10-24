/* ===========================================================
   🛡 Доступ групп: какие функции Марушки открыты каждой группе.
   Новая группа, куда добавили Марушку, не получает ничего, кроме
   /help и /settings, пока владелец не включит модули здесь.
   Только для владельца.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc;

  function row(title, hint, on, attrs) {
    return '<div class="setting"><div class="grow"><div class="t">' + esc(title) + "</div>"
      + (hint ? '<div class="s">' + esc(hint) + "</div>" : "") + "</div>"
      + '<div class="switch' + (on ? " on" : "") + '" ' + attrs + "></div></div>";
  }

  function badge(access, total) {
    if (access.all) return '<span class="chip on">всё открыто</span>';
    if (!access.modules.length) return '<span class="chip">🔒 ничего не открыто</span>';
    return '<span class="chip">открыто ' + access.modules.length + " из " + total + "</span>";
  }

  M.screen("access", function () {
    M.app.innerHTML = M.backButton() + '<div class="dim">Загружаю…</div>';

    M.api("/api/admin/access").then(function (data) {
      var total = data.modules.length;

      function card(g) {
        var a = g.access;
        var modules = a.all ? "" : data.modules.map(function (m) {
          return row(m.title, m.hint, a.modules.indexOf(m.key) >= 0,
            'data-chat="' + esc(g.chat_id) + '" data-module="' + esc(m.key) + '"');
        }).join("");
        return '<div class="card" data-card="' + esc(g.chat_id) + '">'
          + '<div class="card-title">' + esc(g.title) + " " + badge(a, total) + "</div>"
          + '<div class="dim" style="margin-bottom:6px">' + esc(g.members) + " участников"
          + (g.active ? "" : " · давно не писали") + " · ID " + esc(g.chat_id) + "</div>"
          + row("Всё разрешено", "Все функции Марушки, и новые тоже", a.all, 'data-chat="' + esc(g.chat_id) + '" data-all')
          + modules + "</div>";
      }

      function draw() {
        M.app.innerHTML = M.backButton()
          + '<div class="card"><div class="dim">Новая группа, куда добавили Марушку, получает только /help и /settings. '
          + "Арену, турниры, рыбалку, игры, разговор с Марой и остальное открываешь ей ты — здесь. "
          + "На закрытую функцию Марушка в группе отвечает: «включает владелец». Когда Марушку добавляют в новую группу, она пишет тебе в личку.</div></div>"
          + (data.groups.length ? data.groups.map(card).join("") : '<div class="center muted">Марушки пока нет ни в одной группе</div>');
        M.bind();
        bind();
      }

      function update(chatId, access) {
        data.groups.forEach(function (g) { if (String(g.chat_id) === String(chatId)) g.access = access; });
        draw();
      }

      function bind() {
        M.each("[data-all]", function (el) {
          el.onclick = function () {
            var chatId = el.getAttribute("data-chat"), next = !el.classList.contains("on");
            var go = function () {
              M.post("/api/admin/access/" + chatId, { all: next }).then(function (r) {
                M.toast(next ? "Группе открыто всё" : "Всё выключено — включай по одному");
                update(chatId, r.access);
              }).catch(function (e) { M.toast(e.message || "Не получилось"); });
            };
            if (next) go();
            else M.confirm("Закрыть всё?", "Все функции Марушки в этой группе выключатся, дальше включаешь нужные по одному.", "Закрыть", true)
              .then(function (yes) { if (yes) go(); });
          };
        });
        M.each("[data-module]", function (el) {
          el.onclick = function () {
            var chatId = el.getAttribute("data-chat"), next = !el.classList.contains("on");
            el.classList.toggle("on", next);
            M.post("/api/admin/access/" + chatId, { module: el.getAttribute("data-module"), on: next }).then(function (r) {
              update(chatId, r.access);
            }).catch(function (e) { el.classList.toggle("on", !next); M.toast(e.message || "Не получилось"); });
          };
        });
      }

      draw();
    }).catch(M.fail);
  });
})();
