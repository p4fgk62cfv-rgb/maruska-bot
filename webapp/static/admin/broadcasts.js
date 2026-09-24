/* ===========================================================
   Рассылки: конструктор, превью, тест, расписание.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;
  var CATEGORY_TITLES = M.CATEGORY_TITLES, settingsMap = M.settingsMap, needChatScreen = M.needChatScreen;

  // =========================================================
  // РАССЫЛКИ
  // =========================================================

  // Черновик рассылки живёт между перерисовками экрана
  function draft() {
    if (!M.state.cache.bc) M.state.cache.bc = { targets: ["all"], text: "", media: null, mediaType: "photo", mediaName: "", buttons: [], when: "", mode: "groups", segType: "all", segValue: "" };
    return M.state.cache.bc;
  }

  function safePreview(text) {
    // Показываем как в Telegram: разрешённые теги работают, остальное — текстом
    return esc(text)
      .replace(/&lt;(\/?)(b|i|u|s)&gt;/g, "<$1$2>")
      .replace(/\n/g, "<br>");
  }

  M.screen("broadcasts", function () {
    var tab = M.state.cache.bcTab || "new";

    M.api("/api/admin/broadcasts").then(function (d) {
      var chats = M.state.session.chats;
      var st = { scheduled: "⏳ Запланирована", sent: "✅ Отправлена", failed: "❌ Ошибка", cancelled: "🚫 Отменена" };
      var mediaIcon = { photo: "🖼", video: "🎬", animation: "🎞" };
      var scheduled = d.broadcasts.filter(function (b) { return b.status === "scheduled"; });
      var history = d.broadcasts.filter(function (b) { return b.status !== "scheduled"; });

      var tabChip = function (key, label) { return '<span class="chip' + (tab === key ? " on" : "") + '" data-tab-bc="' + key + '">' + label + "</span>"; };

      var list = function (items, empty) {
        return items.length ? items.map(function (b) {
          return '<div class="list-item"><div class="grow"><div class="t">' + esc(b.text.slice(0, 70)) + (b.text.length > 70 ? "…" : "") + "</div>"
            + '<div class="s">' + st[b.status] + " · " + M.time(b.send_at) + " · " + (b.mode === "dm" ? "✉️ в личку" : b.chats + " групп")
            + (b.has_photo ? " · " + (mediaIcon[b.media_type] || "🖼") : "") + (b.buttons.length ? " · 🔗" + b.buttons.length : "")
            + (b.status === "sent" || b.status === "failed" ? " · доставлено " + b.sent + (b.failed ? ", ошибок " + b.failed : "") : "") + "</div></div>"
            + (b.status === "scheduled" ? '<button class="btn danger" data-cancel="' + b.id + '">Отменить</button>' : "") + "</div>";
        }).join("") : '<div class="center muted">' + empty + "</div>";
      };

      var html = M.backButton() + '<div class="chips">' + tabChip("new", "Новое") + tabChip("scheduled", "Запланированные " + (scheduled.length || ""))
        + tabChip("history", "История") + "</div>";

      if (tab === "scheduled") html += list(scheduled, "Запланированных нет");
      if (tab === "history") html += list(history, "Рассылок ещё не было");

      if (tab === "new") {
        var b = draft();

        var dm = b.mode === "dm";
        var SEG = [["all", "Все"], ["active", "Активные за неделю"], ["vip", "VIP"], ["level", "С уровня…"], ["balance", "С баланса…"], ["achievement", "С достижением…"]];

        html += '<div class="card"><div class="card-title">Получатели</div>'
          + '<div class="chips"><span class="chip' + (dm ? "" : " on") + '" data-mode="groups">💬 В группы</span>'
          + '<span class="chip' + (dm ? " on" : "") + '" data-mode="dm">✉️ В личку</span></div>'
          + '<div class="dim" style="margin-bottom:6px">' + (dm ? "Из каких групп брать людей" : "В какие группы") + "</div>"
          + '<div class="chips" style="flex-wrap:wrap"><span class="chip' + (b.targets[0] === "all" ? " on" : "") + '" data-t="all">Все мои группы (' + chats.length + ")</span>"
          + chats.map(function (c) { return '<span class="chip' + (b.targets.indexOf(String(c.chat_id)) >= 0 ? " on" : "") + '" data-t="' + c.chat_id + '">' + esc(c.title) + "</span>"; }).join("")
          + "</div>"
          + (dm
              ? '<div class="dim" style="margin:6px 0">Кому</div><select data-seg>' + SEG.map(function (o) {
                  return '<option value="' + o[0] + '"' + (b.segType === o[0] ? " selected" : "") + ">" + o[1] + "</option>";
                }).join("") + "</select>"
                + (["level", "balance", "achievement"].indexOf(b.segType) >= 0
                    ? '<input data-seg-value style="margin-top:6px" value="' + esc(b.segValue) + '" placeholder="'
                      + ({ level: "Минимальный уровень", balance: "Минимум алмазов", achievement: "Ключ достижения, например first_win" })[b.segType] + '">'
                    : "")
                + '<div data-seg-count class="alert info" style="margin-top:8px"><span class="grow">Считаю получателей…</span></div>'
                + '<div class="dim">В личку можно писать только тем, кто сам запускал Мару (/start). Остальным Telegram не даст отправить.</div>'
              : '<div class="dim">Сообщение увидят все участники выбранных групп.</div>')
          + "</div>"

          + '<div class="card"><div class="card-title">Сообщение</div>'
          + '<textarea data-bc-text rows="5" placeholder="Напишите сообщение… Можно <b>жирный</b> и <i>курсив</i>">' + esc(b.text) + "</textarea>"
          + '<div class="btns four" style="margin-top:8px">'
          + '<label class="quick"><span class="ic">🖼</span>Фото<input type="file" accept="image/*" data-media="photo" class="hidden"></label>'
          + '<label class="quick"><span class="ic">🎬</span>Видео<input type="file" accept="video/*" data-media="video" class="hidden"></label>'
          + '<label class="quick"><span class="ic">🎞</span>GIF<input type="file" accept="image/gif,video/mp4" data-media="animation" class="hidden"></label>'
          + '<div class="quick" data-media-clear><span class="ic">✖️</span>Убрать</div></div>'
          + (b.media ? '<div class="dim" style="margin-top:6px">Вложение: ' + (mediaIcon[b.mediaType] || "") + " " + esc(b.mediaName) + "</div>" : "")
          + "</div>"

          + '<div class="card"><div class="card-title">Кнопки (необязательно)</div>'
          + b.buttons.map(function (btn, i) {
              return '<div class="row-gap" style="margin-bottom:6px"><input data-bt="' + i + '" placeholder="Текст" value="' + esc(btn.text) + '">'
                + '<input data-bu="' + i + '" placeholder="https://…" value="' + esc(btn.url) + '"><button class="btn danger" data-bdel="' + i + '">×</button></div>';
            }).join("")
          + (b.buttons.length < 6 ? '<button class="btn block" data-badd>+ Добавить кнопку</button>' : "") + "</div>"

          + '<div class="card"><div class="card-title">Превью</div><div data-preview></div></div>'

          + '<div class="card"><div class="card-title">Отправить</div>'
          + '<button class="btn block" data-bc-test style="margin-bottom:8px">🧪 Тест себе в личку</button>'
          + '<div class="btns"><button class="btn primary" data-bc-now style="margin:0">Сейчас</button><button class="btn" data-bc-plan>Запланировать</button></div>'
          + '<input type="datetime-local" data-bc-when value="' + esc(b.when) + '" style="margin-top:8px" class="' + (M.state.cache.bcPlan ? "" : "hidden") + '"></div>';
      }

      M.app.innerHTML = html;
      M.bind();

      each("[data-tab-bc]", function (el) { el.onclick = function () { M.state.cache.bcTab = el.getAttribute("data-tab-bc"); M.render(); }; });

      each("[data-cancel]", function (el) {
        el.onclick = function () {
          M.post("/api/admin/broadcasts/cancel", { id: parseInt(el.getAttribute("data-cancel"), 10) })
            .then(function () { M.toast("Отменено"); M.render(); }).catch(function (e) { M.toast(e.message); });
        };
      });

      if (tab === "new") bindComposer(chats);
    }).catch(M.fail);
  });

  function bindComposer(chats) {
    var b = draft();
    var textEl = M.app.querySelector("[data-bc-text]");

    var collect = function () {
      b.text = textEl.value;
      each("[data-bt]", function (el) { b.buttons[+el.getAttribute("data-bt")].text = el.value; });
      each("[data-bu]", function (el) { b.buttons[+el.getAttribute("data-bu")].url = el.value; });
      var when = M.app.querySelector("[data-bc-when]");
      if (when) b.when = when.value;
      var seg = M.app.querySelector("[data-seg]");
      if (seg) b.segType = seg.value;
      var segValue = M.app.querySelector("[data-seg-value]");
      if (segValue) b.segValue = segValue.value;
    };

    M.each("[data-mode]", function (el) {
      el.onclick = function () { collect(); b.mode = el.getAttribute("data-mode"); M.render(); };
    });

    var countBox = M.app.querySelector("[data-seg-count]");

    var countAudience = function () {
      if (!countBox) return;
      collect();
      M.post("/api/admin/broadcasts/audience", { chat_ids: b.targets[0] === "all" ? "all" : b.targets, segment: { type: b.segType, value: b.segValue } })
        .then(function (r) { countBox.querySelector(".grow").textContent = "Получат " + r.count + " чел."; })
        .catch(function (e) { countBox.querySelector(".grow").textContent = e.message; });
    };

    var segSelect = M.app.querySelector("[data-seg]");
    if (segSelect) segSelect.onchange = function () { collect(); M.render(); };

    var segInput = M.app.querySelector("[data-seg-value]"), segTimer;
    if (segInput) segInput.oninput = function () { clearTimeout(segTimer); segTimer = setTimeout(countAudience, 400); };

    countAudience();

    var preview = function () {
      collect();
      var box = M.app.querySelector("[data-preview]");
      var media = "";

      if (b.media) {
        media = b.mediaType === "photo" && b.media.indexOf("data:image") === 0
          ? '<img src="' + b.media + '" style="width:100%;border-radius:12px;margin-bottom:8px;display:block">'
          : '<div class="action-card" style="margin-bottom:8px"><div class="img" style="height:120px">' + (b.mediaType === "video" ? "🎬" : "🎞") + "</div></div>";
      }

      box.innerHTML = '<div style="background:var(--card-2);border:1px solid var(--line);border-radius:16px 16px 16px 4px;padding:10px">'
        + media + '<div style="font-size:14px;line-height:1.45">' + (b.text ? safePreview(b.text) : '<span class="dim">Текст сообщения</span>') + "</div></div>"
        + b.buttons.filter(function (x) { return x.text; }).map(function (x) {
            return '<div class="btn block" style="margin-top:6px;pointer-events:none">' + esc(x.text) + " ↗</div>";
          }).join("");
    };

    preview();
    textEl.oninput = preview;
    each("[data-bt],[data-bu]", function (el) { el.oninput = preview; });

    each("[data-t]", function (el) {
      el.onclick = function () {
        collect();
        var t = el.getAttribute("data-t");
        if (t === "all") b.targets = ["all"];
        else {
          b.targets = b.targets.filter(function (x) { return x !== "all"; });
          var i = b.targets.indexOf(t);
          if (i >= 0) b.targets.splice(i, 1); else b.targets.push(t);
          if (!b.targets.length) b.targets = ["all"];
        }
        M.render();
      };
    });

    each("[data-media]", function (input) {
      input.onchange = function () {
        var file = input.files[0];
        if (!file) return;
        var kind = input.getAttribute("data-media");
        var limit = kind === "photo" ? 5 : 10;
        if (file.size > limit * 1024 * 1024) { M.toast("Файл больше " + limit + " МБ"); return; }
        collect();
        var reader = new FileReader();
        reader.onload = function () { b.media = reader.result; b.mediaType = kind; b.mediaName = file.name; M.render(); };
        reader.readAsDataURL(file);
      };
    });

    var clear = M.app.querySelector("[data-media-clear]");
    if (clear) clear.onclick = function () { collect(); b.media = null; b.mediaName = ""; M.render(); };

    var add = M.app.querySelector("[data-badd]");
    if (add) add.onclick = function () { collect(); b.buttons.push({ text: "", url: "" }); M.render(); };

    each("[data-bdel]", function (el) { el.onclick = function () { collect(); b.buttons.splice(+el.getAttribute("data-bdel"), 1); M.render(); }; });

    var payload = function (when) {
      collect();
      return {
        mode: b.mode,
        segment: { type: b.segType, value: b.segValue },
        text: b.text.trim(),
        chat_ids: b.targets[0] === "all" ? "all" : b.targets,
        photo: b.media, media_type: b.mediaType,
        buttons: b.buttons.filter(function (x) { return x.text && x.url; }),
        send_at: when ? new Date(when).toISOString() : null
      };
    };

    M.app.querySelector("[data-bc-test]").onclick = function () {
      var body = payload(null);
      if (!body.text) { M.toast("Напиши текст"); return; }
      M.post("/api/admin/broadcasts/test", body).then(function () { M.toast("Отправила тебе в личку"); }).catch(function (e) { M.toast(e.message); });
    };

    var send = function (when) {
      var body = payload(when);
      if (!body.text) { M.toast("Напиши текст"); return; }
      var count = b.targets[0] === "all" ? chats.length : b.targets.length;
      var where = b.mode === "dm"
        ? "Сообщение уйдёт в личку выбранным людям (" + ((countBox && countBox.textContent) || "сколько — посчитано выше") + ")"
        : "Сообщение уйдёт в " + count + " групп";

      M.confirm(when ? "Запланировать рассылку?" : "Отправить рассылку?",
        where + (when ? " " + new Date(when).toLocaleString("ru") : " в течение 20 секунд") + ".",
        when ? "Запланировать" : "Отправить").then(function (yes) {
          if (!yes) return;
          M.post("/api/admin/broadcasts", body).then(function () {
            M.state.cache.bc = null;
            M.state.cache.bcPlan = false;
            M.state.cache.bcTab = when ? "scheduled" : "history";
            M.toast(when ? "Запланировано" : "Отправляется…");
            M.render();
          }).catch(function (e) { M.toast(e.message); });
        });
    };

    M.app.querySelector("[data-bc-now]").onclick = function () { send(null); };

    M.app.querySelector("[data-bc-plan]").onclick = function () {
      var when = M.app.querySelector("[data-bc-when]");
      if (when.classList.contains("hidden")) { collect(); M.state.cache.bcPlan = true; M.render(); return; }
      if (!when.value) { M.toast("Выбери дату и время"); return; }
      send(when.value);
    };
  }
})();
