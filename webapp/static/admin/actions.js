/* ===========================================================
   Actions: список и редактор действия.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;
  var CATEGORY_TITLES = M.CATEGORY_TITLES, settingsMap = M.settingsMap, needChatScreen = M.needChatScreen;

  // =========================================================
  // ДЕЙСТВИЯ
  // =========================================================


  M.screen("actions", function () {
    M.api("/api/admin/actions" + M.chatQuery()).then(function (d) {
      M.state.cache.actions = d.actions;

      var cat = M.state.cache.actionCat || "";
      var q = (M.state.cache.actionQuery || "").toLowerCase();

      var present = {};
      d.actions.forEach(function (a) { present[a.theme] = true; });
      var cats = M.THEME_ORDER.filter(function (t) { return present[t]; });

      var list = d.actions.filter(function (a) {
        if (cat === "_top") return a.usage > 0;
        if (cat === "_off") return !a.enabled;
        if (cat && a.theme !== cat) return false;
        if (q && a.title.toLowerCase().indexOf(q) < 0 && !a.aliases.some(function (x) { return x.indexOf(q) >= 0; })) return false;
        return true;
      });

      if (cat === "_top") list.sort(function (a, b) { return b.usage - a.usage; });

      var chip = function (key, label) { return '<span class="chip' + (cat === key ? " on" : "") + '" data-cat="' + key + '">' + label + "</span>"; };

      var html = M.backButton() + M.chatPicker()
        + '<input data-aq placeholder="🔍  Найти действие" value="' + esc(M.state.cache.actionQuery || "") + '" style="margin-bottom:10px">'
        + '<div class="chips">' + chip("", "Все " + d.actions.length) + chip("_top", "🔥 Популярные") + chip("_off", "Выключенные")
        + cats.map(function (c) { return chip(c, CATEGORY_TITLES[c] || c); }).join("") + "</div>"
        + '<div class="action-grid">' + list.slice(0, 60).map(function (a) {
            return '<div class="action-card' + (a.enabled ? "" : " off") + '" data-open="action" data-arg="' + a.key + '">'
              + '<div class="img" data-img="/api/admin/action_image?key=' + a.key + '">' + a.emoji + "</div>"
              + (a.usage ? '<div class="flag">🔥 ' + a.usage + "</div>" : "")
              + (a.custom ? '<div class="flag" style="left:8px;right:auto;background:rgba(139,92,246,.8)">✏️ ' + a.custom + "</div>" : "")
              + '<div class="b"><div class="t">' + esc(a.title) + '</div><div class="s">'
              + (a.enabled ? esc(CATEGORY_TITLES[a.category] || a.category) : "выключено") + " · " + a.usage + " за неделю"
              + (a.cooldown ? " · ⏱ " + a.cooldown + "с" : "") + "</div></div></div>";
          }).join("") + "</div>"
        + (list.length > 60 ? '<div class="dim center">Показаны первые 60 — уточни поиск</div>' : "");

      M.app.innerHTML = html;
      M.bind();

      each("[data-cat]", function (el) { el.onclick = function () { M.state.cache.actionCat = el.getAttribute("data-cat"); M.render(); }; });

      var input = M.app.querySelector("[data-aq]"), timer;
      input.oninput = function () { clearTimeout(timer); timer = setTimeout(function () { M.state.cache.actionQuery = input.value.trim(); M.render(); }, 350); };
    }).catch(M.fail);
  });

  M.screen("action", function (key) {
    M.api("/api/admin/action?key=" + encodeURIComponent(key) + (M.state.chat ? "&chat_id=" + M.state.chat : "")).then(function (a) {
      var chat = M.state.chat;
      var canEdit = !!chat && M.can("content");
      var owner = M.state.session.user.owner;

      var customs = function (kind) { return a.custom.filter(function (c) { return c.kind === kind; }); };
      var aliases = customs("alias"), phrases = customs("phrase"), images = customs("image");
      var visiblePool = a.pool.filter(function (p) { return !p.hidden; }).length;

      var html = M.backButton("Действия")

        // --- шапка с картинкой и главным переключателем ---
        + '<div class="card glow" style="padding:0;overflow:hidden">'
        + '<div class="action-card" style="border:0;border-radius:0;cursor:default"><div class="img" style="height:180px" data-img="/api/admin/action_image?key=' + a.key + '">' + a.emoji + "</div></div>"
        + '<div style="padding:14px"><div class="setting" style="border:0;padding:0">'
        + '<div class="grow"><h2 style="margin:0">' + a.emoji + " " + esc(a.title) + "</h2>"
        + '<div class="dim">' + esc(CATEGORY_TITLES[a.category] || a.category) + " · ключ " + esc(a.key) + "</div></div>"
        + '<div class="switch' + (a.enabled ? " on" : "") + (canEdit ? "" : " locked") + '" data-act-toggle></div></div></div></div>';

      if (!chat) html += '<div class="alert info"><span class="ico">💬</span><span class="grow">Правки делаются для конкретной группы — выбери её на экране действий.</span></div>';

      html += '<div class="metrics three">' + M.metric("🔥", a.usage_7, "За 7 дней") + M.metric("📅", a.usage_30, "За 30 дней")
        + M.metric("🖼", visiblePool + images.length, "Картинок") + "</div>"

        // --- слова-триггеры ---
        + '<div class="card"><div class="card-title">Ключевые слова</div>'
        + a.builtin_aliases.map(function (x) {
            return '<span class="tag"' + (canEdit ? ' data-hide-alias="' + esc(x.value) + '" data-hidden="' + (x.hidden ? 1 : 0) + '"' : "")
              + ' style="margin:0 4px 6px 0;' + (canEdit ? "cursor:pointer;" : "") + (x.hidden ? "text-decoration:line-through;opacity:.45" : "") + '">'
              + esc(x.text) + "</span>";
          }).join("")
        + aliases.map(function (c) {
            return '<span class="tag" style="margin:0 4px 6px 0;background:rgba(139,92,246,.25);color:var(--accent-3)">' + esc(c.value)
              + (canEdit ? ' <b data-del="' + c.id + '" style="cursor:pointer">×</b>' : "") + "</span>";
          }).join("")
        + (canEdit ? '<div class="row-gap" style="margin-top:8px"><input data-new-alias placeholder="Новое слово, например «пивка»"><button class="btn" data-add="alias">+ Добавить</button></div>' : "")
        + '<div class="dim" style="margin-top:6px">Серые — встроенные' + (canEdit ? " (нажми, чтобы скрыть в группе)" : "")
        + ', зачёркнутые — скрыты, фиолетовые — добавлены в этой группе.</div></div>'

        // --- картинки ---
        + '<div class="card"><div class="card-title">Изображения (' + (visiblePool + images.length) + ")</div>";

      if (images.length) {
        html += '<div class="dim" style="margin-bottom:6px">Свои картинки группы</div><div class="action-grid" style="margin-bottom:10px">'
          + images.map(function (c) {
              return '<div class="action-card" style="cursor:default"><div class="img" style="height:90px" data-img="/api/admin/action/custom_image?id=' + c.id + '">🖼</div>'
                + '<div class="b"><div class="s">показана ' + c.shows + " раз" + (c.cached ? " · в Telegram" : "")
                + (c.last_used ? " · последний раз " + M.ago(c.last_used) : "") + "</div>"
                + (canEdit ? '<label class="btn block" style="margin-top:6px;padding:6px">🔄 Заменить<input type="file" accept="image/*" data-replace="' + c.id + '" class="hidden"></label>'
                  + '<button class="btn danger block" data-del="' + c.id + '" style="margin-top:4px;padding:6px">Удалить</button>' : "")
                + "</div></div>";
            }).join("") + "</div>";
      }

      if (a.pool.length) {
        html += '<div class="dim" style="margin-bottom:6px">Общая коллекция · скрытые не показываются в этой группе</div><div class="action-grid">'
          + a.pool.slice(0, 24).map(function (p) {
              return '<div class="action-card' + (p.hidden ? " off" : "") + '" style="cursor:default">'
                + '<div class="img" style="height:90px" data-img="/api/admin/action_image?key=' + a.key + "&id=" + p.id + '">🖼</div>'
                + '<div class="b"><div class="s">' + esc(p.provider) + " · " + (p.cached ? "в Telegram" : "не загружена") + (p.used_at ? " · показ " + M.ago(p.used_at) : "") + "</div>"
                + (canEdit ? '<button class="btn block" data-hide="' + p.id + '" data-hidden="' + (p.hidden ? 1 : 0) + '" style="margin-top:6px;padding:6px">' + (p.hidden ? "👁 Вернуть" : "🙈 Скрыть") + "</button>" : "")
                + (owner ? '<button class="btn danger block" data-gdel="' + p.id + '" style="margin-top:4px;padding:6px">Удалить везде</button>' : "")
                + "</div></div>";
            }).join("") + "</div>";
      } else if (!images.length) {
        html += '<div class="dim">Картинок пока нет — они собираются при первых срабатываниях.</div>';
      }

      if (canEdit) {
        html += '<div class="dim" style="margin:12px 0 6px">Добавить свою: ссылка или файл до 2 МБ</div>'
          + '<div class="row-gap"><input data-img-url placeholder="https://…/picture.jpg"><button class="btn" data-add="image-url">+ Ссылка</button></div>'
          + '<input type="file" accept="image/*" data-img-file style="margin-top:8px">'
          + '<div class="setting" style="margin-top:8px"><div class="ico">🎞</div><div class="grow"><div class="t">Только свои картинки</div>'
          + '<div class="s">Выкл — свои вперемешку с общими</div></div>'
          + '<div class="switch' + (a.image_mode === "own" ? " on" : "") + '" data-own></div></div>';
      }

      html += "</div>"

        // --- фразы ---
        + '<div class="card"><div class="card-title">Фразы</div>'
        + phrases.map(function (c) {
            return '<div class="list-item" style="align-items:flex-start"><span style="font-size:16px">✏️</span><div class="grow" style="font-size:13px">' + esc(c.value) + "</div>"
              + (canEdit ? '<b data-del="' + c.id + '" style="cursor:pointer;color:var(--red)">×</b>' : "") + "</div>";
          }).join("")
        + (canEdit ? '<textarea data-new-phrase rows="3" placeholder="{emoji} {actor} <угостил|угостила> {target_acc} {item_instr}"></textarea>'
            + '<button class="btn block" data-add="phrase" style="margin-top:8px">+ Добавить фразу</button>'
            + '<div class="dim" style="margin-top:8px">Подстановки: ' + Object.keys(a.placeholders).map(function (k) {
                return "<b>{" + k + "}</b> " + esc(a.placeholders[k]);
              }).join(" · ") + '. Род: &lt;угостил|угостила&gt;</div>' : "")
        + '<details style="margin-top:10px"><summary class="muted" style="cursor:pointer">Встроенные фразы (' + a.builtin_phrases.length + ")</summary>"
        + (a.phrases_shared ? '<div class="dim" style="margin:6px 0">Эти фразы общие для всей категории «' + esc(CATEGORY_TITLES[a.category] || a.category) + '»: скрытая пропадёт у всех её действий в группе.</div>' : "")
        + a.builtin_phrases.map(function (p) {
            return '<div class="event" style="' + (p.hidden ? "opacity:.45" : "") + '"><div class="grow t" style="' + (p.hidden ? "text-decoration:line-through" : "") + '">' + esc(p.preview) + "</div>"
              + (canEdit ? '<b data-hide-phrase="' + esc(p.template) + '" data-hidden="' + (p.hidden ? 1 : 0) + '" style="cursor:pointer;padding-left:8px">' + (p.hidden ? "👁" : "🙈") + "</b>" : "")
              + "</div>";
          }).join("")
        + "</details></div>"

        // --- поведение ---
        + '<div class="card"><div class="card-title">Поведение</div>'
        + '<div class="setting"><div class="ico">⏱</div><div class="grow"><div class="t">Cooldown</div><div class="s">Пауза между срабатываниями в группе</div></div>'
        + '<select data-cooldown style="width:auto"' + (canEdit ? "" : " disabled") + ">"
        + [[0, "Без паузы"], [5, "5 сек"], [15, "15 сек"], [30, "30 сек"], [60, "1 мин"], [300, "5 мин"], [900, "15 мин"]].map(function (o) {
            return '<option value="' + o[0] + '"' + (a.cooldown === o[0] ? " selected" : "") + ">" + o[1] + "</option>";
          }).join("") + "</select></div>"
        + '<div class="setting"><div class="ico">🔁</div><div class="grow"><div class="t">Защита от повторов</div><div class="s">Картинки идут по кругу: одна не повторится, пока не покажут все</div></div><span class="tag ok">всегда</span></div>'
        + '<div class="setting"><div class="ico">⚧</div><div class="grow"><div class="t">Пол</div><div class="s">' + esc(a.gender_logic) + (a.pair_logic ? ". Картинка подбирается по паре: он–она, он–он, она–она" : "") + '</div></div><span class="tag">авто</span></div>'
        + '<div class="setting"><div class="ico">🎯</div><div class="grow"><div class="t">Цель</div><div class="s">' + esc(a.target_logic) + "</div></div></div>"
        + "</div>"

        + '<button class="btn primary" data-test>🧪 Протестировать Action</button>';

      M.app.innerHTML = html;
      M.bind();
      bindActionEditor(a, canEdit);
    }).catch(M.fail);
  });

  function bindActionEditor(a, canEdit) {
    var reload = function (msg) { if (msg) M.toast(msg); M.state.cache.actions = null; M.render(); };
    var fail = function (e) { M.toast(e.message); };

    var addCustom = function (kind, value, okMsg) {
      if (!value) { M.toast("Пусто"); return; }
      M.post("/api/admin/action/custom", { chat_id: M.state.chat, key: a.key, kind: kind, value: value })
        .then(function () { M.haptic(); reload(okMsg); }).catch(fail);
    };

    var t = M.app.querySelector("[data-act-toggle]");
    if (t && canEdit) t.onclick = function () {
      var next = !t.classList.contains("on");
      t.classList.toggle("on", next);
      M.post("/api/admin/actions/toggle", { chat_id: M.state.chat, key: a.key, enabled: next })
        .then(function () { M.toast(next ? "Включено" : "Выключено"); M.state.cache.actions = null; })
        .catch(function (e) { t.classList.toggle("on", !next); fail(e); });
    };

    each("[data-add]", function (btn) {
      btn.onclick = function () {
        var kind = btn.getAttribute("data-add");
        if (kind === "alias") addCustom("alias", M.app.querySelector("[data-new-alias]").value.trim(), "Слово добавлено");
        if (kind === "phrase") addCustom("phrase", M.app.querySelector("[data-new-phrase]").value.trim(), "Фраза добавлена");
        if (kind === "image-url") addCustom("image", M.app.querySelector("[data-img-url]").value.trim(), "Картинка добавлена");
      };
    });

    var file = M.app.querySelector("[data-img-file]");
    if (file) file.onchange = function () {
      var f = file.files[0];
      if (!f) return;
      if (f.size > 2 * 1024 * 1024) { M.toast("Картинка больше 2 МБ"); file.value = ""; return; }
      var reader = new FileReader();
      reader.onload = function () { addCustom("image", reader.result, "Картинка загружена"); };
      reader.readAsDataURL(f);
    };

    each("[data-del]", function (el) {
      el.onclick = function () {
        M.post("/api/admin/action/custom/delete", { chat_id: M.state.chat, id: parseInt(el.getAttribute("data-del"), 10) })
          .then(function () { reload("Удалено"); }).catch(fail);
      };
    });

    each("[data-hide]", function (el) {
      el.onclick = function () {
        var hidden = el.getAttribute("data-hidden") !== "1";
        M.post("/api/admin/action/hide_image", { chat_id: M.state.chat, key: a.key, image_id: parseInt(el.getAttribute("data-hide"), 10), hidden: hidden })
          .then(function () { reload(hidden ? "Скрыта в этой группе" : "Возвращена"); }).catch(fail);
      };
    });

    each("[data-gdel]", function (el) {
      el.onclick = function () {
        M.confirm("Удалить картинку везде?", "Она пропадёт из общей коллекции во всех группах. Это не отменить.", "Удалить", true)
          .then(function (y) {
            if (!y) return;
            M.post("/api/admin/action/delete_image", { image_id: parseInt(el.getAttribute("data-gdel"), 10) })
              .then(function () { reload("Удалена из коллекции"); }).catch(fail);
          });
      };
    });

    var toggleBuiltin = function (kind, value, hidden) {
      M.post("/api/admin/action/hide_builtin", { chat_id: M.state.chat, key: a.key, kind: kind, value: value, hidden: hidden })
        .then(function () { reload(hidden ? "Скрыто в этой группе" : "Возвращено"); }).catch(fail);
    };

    each("[data-hide-alias]", function (el) {
      el.onclick = function () { toggleBuiltin("alias", el.getAttribute("data-hide-alias"), el.getAttribute("data-hidden") !== "1"); };
    });

    each("[data-hide-phrase]", function (el) {
      el.onclick = function () { toggleBuiltin("phrase", el.getAttribute("data-hide-phrase"), el.getAttribute("data-hidden") !== "1"); };
    });

    each("[data-replace]", function (input) {
      input.onchange = function () {
        var f = input.files[0];
        if (!f) return;
        if (f.size > 2 * 1024 * 1024) { M.toast("Картинка больше 2 МБ"); return; }
        var reader = new FileReader();
        reader.onload = function () {
          M.post("/api/admin/action/replace_image", { chat_id: M.state.chat, id: parseInt(input.getAttribute("data-replace"), 10), value: reader.result })
            .then(function () { reload("Картинка заменена"); }).catch(fail);
        };
        reader.readAsDataURL(f);
      };
    });

    var own = M.app.querySelector("[data-own]");
    if (own) own.onclick = function () {
      var next = !own.classList.contains("on");
      own.classList.toggle("on", next);
      M.post("/api/admin/action/option", { chat_id: M.state.chat, key: a.key, kind: "image_mode", value: next ? "own" : "mix" })
        .then(function () { M.toast(next ? "Только свои картинки" : "Вперемешку с общими"); })
        .catch(function (e) { own.classList.toggle("on", !next); fail(e); });
    };

    var cd = M.app.querySelector("[data-cooldown]");
    if (cd && canEdit) cd.onchange = function () {
      M.post("/api/admin/action/option", { chat_id: M.state.chat, key: a.key, kind: "cooldown", value: parseInt(cd.value, 10) })
        .then(function () { M.toast("Сохранено"); M.state.cache.actions = null; }).catch(fail);
    };

    M.app.querySelector("[data-test]").onclick = function () {
      M.api("/api/admin/action/preview?key=" + a.key + (M.state.chat ? "&chat_id=" + M.state.chat : "")).then(function (p) {
        var bg = document.createElement("div");
        bg.className = "sheet-bg";
        bg.innerHTML = '<div class="sheet"><div class="grip"></div><h3>Так это увидит чат</h3>'
          + '<div class="action-card" style="cursor:default;margin:10px 0"><div class="img" style="height:170px" data-img="/api/admin/action_image?key=' + a.key + '">' + a.emoji + "</div>"
          + '<div class="b" style="font-size:14px;line-height:1.45">' + esc(p.male) + "</div></div>"
          + '<div class="dim" style="margin-bottom:12px">Если пишет девушка: ' + esc(p.female) + (p.custom ? " · фраза группы" : "") + "</div>"
          + '<div class="btns"><button class="btn" data-again>🔄 Ещё вариант</button><button class="btn" data-close>Закрыть</button></div></div>';
        document.body.appendChild(bg);
        M.loadImages(bg);
        bg.querySelector("[data-close]").onclick = function () { bg.remove(); };
        bg.querySelector("[data-again]").onclick = function () { bg.remove(); M.app.querySelector("[data-test]").click(); };
        bg.onclick = function (e) { if (e.target === bg) bg.remove(); };
      }).catch(fail);
    };
  }
})();
