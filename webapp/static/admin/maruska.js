/* ===========================================================
   Маруська: хаб, интенсивность и личность, память, автоответы, изображения.
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;
  var CATEGORY_TITLES = M.CATEGORY_TITLES, settingsMap = M.settingsMap, needChatScreen = M.needChatScreen;

  // =========================================================
  // МАРУСЬКА — AI и контент
  // =========================================================

  M.screen("mara", function () {
    var needChat = !M.state.chat;
    var p = needChat ? Promise.resolve(null) : M.api("/api/admin/settings" + M.chatQuery());

    p.then(function (settings) {
      var byKey = {};
      if (settings) settings.sections.forEach(function (s) { s.items.forEach(function (i) { byKey[i.key] = i; }); });

      var v = function (k) { return byKey[k] ? byKey[k].value : null; };
      var label = function (k) { return byKey[k] ? byKey[k].label : "—"; };
      var ai = v("ai");

      var MARA_ICONS = {
        "💬": ["message", "purple"], "🧠": ["brain", "pink"], "⚡": ["zap", "gold"], "🖼": ["image", "blue"],
        "🎮": ["game", "green"], "🔥": ["flame", "red"], "🎭": ["mask", "purple"], "👋": ["wave", "gold"]
      };

      var row = function (icon, title, sub, open, arg) {
        var look = MARA_ICONS[icon] || ["sparkles", "purple"];
        return '<div class="list-item tap" data-open="' + open + '"' + (arg ? ' data-arg="' + arg + '"' : "") + ">"
          + M.tile(look[0], look[1], 19) + '<div class="grow"><div class="t">' + title
          + '</div><div class="s">' + sub + '</div></div>' + M.chev() + '</div>';
      };

      var html = M.header("Маруська 💜", "AI и автоматизация") + M.chatPicker();

      if (!needChat) {
        html += '<div class="card glow" style="' + (ai ? "border-color:rgba(52,211,153,.45)" : "") + '"><div class="setting" style="border:0;padding:0"><div class="ico">🤖</div>'
          + '<div class="grow"><div class="t">' + (ai ? "AI активна" : "AI выключена") + "</div>"
          + '<div class="s">' + (ai ? "Готова общаться и помогать" : "Мара молчит, действия и игры работают") + "</div></div>"
          + '<div class="switch' + (ai ? " on" : "") + (M.can("content") ? "" : " locked") + '" data-ai></div></div></div>';
      }

      html += row("💬", "Автоответы", v("autoreplies") === false ? "Выключены" : "Ответы на ключевые слова", "autoreplies")
        + row("🧠", "Память и контекст", needChat ? "Что Мара помнит" : (v("memory") ? "Помнит " + label("context_messages") + " · хранит " + label("memory_days") : "Выключена"), "memory")
        + row("⚡", "Actions", "Настройка действий", "actions")
        + row("🖼", "Изображения", "Источники и подбор", "images")
        + (M.state.session.user.owner ? row("📚", "Моя коллекция", "Свои картинки: #пиво в личку Маре", "library") : "")
        + row("🎮", "Игры", "Крокодил, кубики, награды", "games")
        + row("🔥", "Интенсивность AI", needChat ? "Режим и лимиты" : label("chattiness") + (v("ai_daily_limit") ? " · до " + v("ai_daily_limit") + " в сутки" : ""), "ai")
        + row("🎭", "Личность Маруськи", needChat ? "Характер" : label("persona"), "ai")
        + row("👋", "Приветствие", "Текст для новичков", "settings", "Сообщество")
        + row("🌍", "Язык", needChat ? "Русский или English" : label("language"), "settings", "Общение");

      if (needChat) html += '<div class="dim" style="margin-top:6px">Выбери группу, чтобы видеть текущие значения.</div>';

      M.app.innerHTML = html;
      M.bind();

      var sw = M.app.querySelector("[data-ai]");
      if (sw && M.can("content")) sw.onclick = function () {
        var next = !sw.classList.contains("on");
        sw.classList.toggle("on", next);
        M.post("/api/admin/settings", { chat_id: M.state.chat, key: "ai", value: next })
          .then(function () { M.toast(next ? "Мара снова отвечает" : "Мара молчит"); M.render(); })
          .catch(function (e) { sw.classList.toggle("on", !next); M.toast(e.message); });
      };
    }).catch(M.fail);
  });

  // Сохранить одну настройку группы — общий помощник для экранов
  M.saveSetting = function (key, value, okText) {
    return M.post("/api/admin/settings", { chat_id: M.state.chat, key: key, value: value })
      .then(function () { M.haptic(); M.toast(okText || "Сохранено"); })
      .catch(function (e) { M.toast(e.message); throw e; });
  };

  // =========================================================
  // МАРУСЬКА: интенсивность и личность
  // =========================================================



  var MODE_HINTS = {
    quiet: "Отвечает по имени, но не чаще раза в пару минут",
    normal: "Отвечает всегда, когда к ней обращаются",
    active: "Плюс изредка вмешивается в разговор сама",
    fun: "Шутит больше, предлагает игры и челленджи, вмешивается чаще"
  };

  M.screen("ai", function () {
    if (!M.state.chat) { needChatScreen("Режим задаётся для каждой группы — выбери группу."); return; }

    settingsMap().then(function (m) {
      var canEdit = M.can("content");
      var cards = function (key, hints) {
        return m[key].options.map(function (o) {
          var on = o.value === m[key].value;
          return '<div class="list-item' + (canEdit ? " tap" : "") + '" data-pick="' + key + '" data-v="' + o.value + '" style="' + (on ? "border-color:var(--accent-2);box-shadow:var(--glow)" : "") + '">'
            + '<div style="font-size:24px">' + o.emoji + '</div><div class="grow"><div class="t">' + esc(o.label) + "</div>"
            + (hints && hints[o.value] ? '<div class="s">' + esc(hints[o.value]) + "</div>" : "") + "</div>"
            + (on ? '<span class="tag ok">выбрано</span>' : "") + "</div>";
        }).join("");
      };

      M.app.innerHTML = M.backButton("Маруська") + M.chatPicker(false)
        + '<div class="card-title" style="font-size:17px">🔥 Интенсивность</div>' + cards("chattiness", MODE_HINTS)
        + '<div class="card" style="margin-top:12px"><div class="card-title">Лимиты</div>'
        + '<div class="kv"><span class="k">Ответов в сутки</span><span>' + (m.ai_daily_limit.value || "без ограничений") + "</span></div>"
        + '<div class="kv"><span class="k">Пауза для одного человека</span><span>' + (m.ai_cooldown.value ? m.ai_cooldown.label : "нет") + "</span></div>"
        + '<div class="kv"><span class="k">Сообщений в контексте</span><span>' + m.context_messages.label + "</span></div>"
        + '<button class="btn block" data-open="settings" data-arg="Общение" style="margin-top:8px">Изменить лимиты</button></div>'
        + '<div class="card-title" style="font-size:17px;margin-top:6px">🎭 Личность</div>' + cards("persona");

      M.bind();

      each("[data-pick]", function (el) {
        if (!canEdit) return;
        el.onclick = function () {
          M.saveSetting(el.getAttribute("data-pick"), el.getAttribute("data-v")).then(function () { M.render(); });
        };
      });
    }).catch(M.fail);
  });

  // =========================================================
  // ПАМЯТЬ
  // =========================================================

  M.screen("memory", function () {
    if (!M.state.chat) { needChatScreen("Память у каждой группы своя — выбери группу."); return; }

    Promise.all([settingsMap(), M.api("/api/admin/memory" + M.chatQuery())]).then(function (res) {
      var m = res[0], st = res[1];
      var canEdit = M.can("content");
      var on = m.memory.value;

      M.app.innerHTML = M.backButton("Маруська") + M.chatPicker(false)
        + '<div class="card glow"><div class="setting" style="border:0;padding:0"><div class="ico">🧠</div><div class="grow">'
        + '<div class="t">' + (on ? "Память включена" : "Память выключена") + '</div><div class="s">'
        + (on ? "Мара отвечает с учётом разговора" : "Мара видит только само обращение и ничего не сохраняет") + "</div></div>"
        + '<div class="switch' + (on ? " on" : "") + (canEdit ? "" : " locked") + '" data-mem></div></div></div>'

        + '<div class="metrics three">' + M.metric("💬", num(st.messages), "Сообщений в базе")
        + M.metric("🗓", m.memory_days.label, "Срок хранения") + M.metric("🧩", m.context_messages.label, "В контексте") + "</div>"
        + '<div class="dim" style="margin:-4px 0 12px">Самое старое: ' + (st.oldest ? M.time(st.oldest) : "—") + ". Старше срока удаляется само раз в 6 часов.</div>"

        + '<div class="card"><div class="card-title">Исключения</div>'
        + '<div class="dim" style="margin-bottom:6px">Чьи сообщения Мара не запоминает. Статистика и опыт у них считаются как обычно.</div>'
        + '<textarea data-except rows="2" placeholder="@username, 123456789"' + (canEdit ? "" : " disabled") + ">" + esc(m.memory_except.value) + "</textarea>"
        + (canEdit ? '<button class="btn block" data-save-except style="margin-top:8px">Сохранить</button>' : "") + "</div>"

        + '<button class="btn block" data-open="settings" data-arg="Общение" style="margin-bottom:8px">⚙️ Размер контекста и срок хранения</button>'
        + (canEdit ? '<button class="btn danger block" data-clear>🗑 Очистить память группы</button>' : "");

      M.bind();

      var sw = M.app.querySelector("[data-mem]");
      if (sw && canEdit) sw.onclick = function () {
        var next = !sw.classList.contains("on");
        sw.classList.toggle("on", next);
        M.saveSetting("memory", next, next ? "Память включена" : "Память выключена").then(function () { M.render(); })
          .catch(function () { sw.classList.toggle("on", !next); });
      };

      var saveEx = M.app.querySelector("[data-save-except]");
      if (saveEx) saveEx.onclick = function () { M.saveSetting("memory_except", M.app.querySelector("[data-except]").value.trim()); };

      var clear = M.app.querySelector("[data-clear]");
      if (clear) clear.onclick = function () {
        M.confirm("Очистить память?", "Мара забудет все сохранённые сообщения этой группы (" + num(st.messages) + "). Статистика и профили останутся.", "Очистить", true)
          .then(function (yes) {
            if (!yes) return;
            M.post("/api/admin/memory/clear", { chat_id: M.state.chat })
              .then(function (r) { M.toast("Удалено: " + num(r.removed)); M.render(); })
              .catch(function (e) { M.toast(e.message); });
          });
      };
    }).catch(M.fail);
  });

  // =========================================================
  // АВТООТВЕТЫ
  // =========================================================

  var MATCH_TITLES = { contains: "Содержит слово", exact: "Точно совпадает", start: "Начинается с" };

  M.screen("autoreplies", function () {
    if (!M.state.chat) { needChatScreen("Автоответы у каждой группы свои — выбери группу."); return; }

    Promise.all([settingsMap(), M.api("/api/admin/autoreplies" + M.chatQuery())]).then(function (res) {
      var m = res[0], rules = res[1].rules;
      var canEdit = M.can("content");
      var editing = M.state.cache.editReply || null;
      var on = m.autoreplies.value;

      var html = M.backButton("Маруська") + M.chatPicker(false)
        + '<div class="card glow"><div class="setting" style="border:0;padding:0"><div class="ico">💬</div><div class="grow">'
        + '<div class="t">Автоответы ' + (on ? "включены" : "выключены") + '</div><div class="s">Сработал автоответ — Мара не тратит AI-запрос</div></div>'
        + '<div class="switch' + (on ? " on" : "") + (canEdit ? "" : " locked") + '" data-ar-on></div></div></div>';

      html += rules.length ? rules.map(function (r) {
        return '<div class="card" style="' + (r.enabled ? "" : "opacity:.55") + '"><div class="row-gap" style="align-items:center">'
          + '<div class="grow"><div class="t">«' + esc(r.trigger) + '»</div><div class="dim">' + MATCH_TITLES[r.match]
          + " · " + r.probability + "% · пауза " + r.cooldown + "с · сработал " + r.hits + " раз</div></div>"
          + (canEdit ? '<div class="switch' + (r.enabled ? " on" : "") + '" data-ar-toggle="' + r.id + '"></div>' : "") + "</div>"
          + '<div style="margin-top:8px;font-size:13px;white-space:pre-wrap">' + esc(r.response) + "</div>"
          + (canEdit ? '<div class="btns" style="margin-top:8px"><button class="btn" data-ar-edit="' + r.id + '">✏️ Изменить</button><button class="btn danger" data-ar-del="' + r.id + '">Удалить</button></div>' : "")
          + "</div>";
      }).join("") : '<div class="center muted">Автоответов пока нет</div>';

      if (canEdit) {
        var e = editing ? rules.filter(function (r) { return r.id === editing; })[0] : null;
        var opt = function (list, value) {
          return list.map(function (o) { return '<option value="' + o[0] + '"' + (String(o[0]) === String(value) ? " selected" : "") + ">" + o[1] + "</option>"; }).join("");
        };

        html += '<div class="card glow"><div class="card-title">' + (e ? "Изменить автоответ" : "Новый автоответ") + "</div>"
          + '<input data-f-trigger placeholder="Ключевое слово, например «доброе утро»" value="' + esc(e ? e.trigger : "") + '" style="margin-bottom:8px">'
          + '<select data-f-match style="margin-bottom:8px">' + opt([["contains", "Содержит слово"], ["exact", "Точно совпадает"], ["start", "Начинается с"]], e ? e.match : "contains") + "</select>"
          + '<textarea data-f-response rows="3" placeholder="Ответ. {name} — имя того, кто написал">' + esc(e ? e.response : "") + "</textarea>"
          + '<div class="row-gap" style="margin-top:8px">'
          + '<select data-f-prob>' + opt([[100, "Всегда"], [75, "75%"], [50, "50%"], [25, "25%"], [10, "10%"]], e ? e.probability : 100) + "</select>"
          + '<select data-f-cd>' + opt([[0, "Без паузы"], [30, "Пауза 30 сек"], [60, "1 мин"], [300, "5 мин"], [1800, "30 мин"], [3600, "1 час"], [86400, "Раз в сутки"]], e ? e.cooldown : 30) + "</select></div>"
          + '<button class="btn primary" data-f-save style="margin-top:10px">' + (e ? "Сохранить" : "+ Добавить") + "</button>"
          + (e ? '<button class="btn block" data-f-cancel style="margin-top:8px">Отмена</button>' : "") + "</div>";
      }

      M.app.innerHTML = html;
      M.bind();

      var fail = function (err) { M.toast(err.message); };
      var sw = M.app.querySelector("[data-ar-on]");
      if (sw && canEdit) sw.onclick = function () {
        var next = !sw.classList.contains("on");
        M.saveSetting("autoreplies", next).then(function () { M.render(); });
      };

      each("[data-ar-toggle]", function (el) {
        el.onclick = function () {
          var r = rules.filter(function (x) { return x.id === parseInt(el.getAttribute("data-ar-toggle"), 10); })[0];
          M.post("/api/admin/autoreplies", Object.assign({}, r, { chat_id: M.state.chat, enabled: !r.enabled }))
            .then(function () { M.toast(r.enabled ? "Выключен" : "Включён"); M.render(); }).catch(fail);
        };
      });

      each("[data-ar-edit]", function (el) { el.onclick = function () { M.state.cache.editReply = parseInt(el.getAttribute("data-ar-edit"), 10); M.render(); }; });

      each("[data-ar-del]", function (el) {
        el.onclick = function () {
          M.post("/api/admin/autoreplies/delete", { chat_id: M.state.chat, id: parseInt(el.getAttribute("data-ar-del"), 10) })
            .then(function () { M.toast("Удалён"); M.render(); }).catch(fail);
        };
      });

      var cancel = M.app.querySelector("[data-f-cancel]");
      if (cancel) cancel.onclick = function () { M.state.cache.editReply = null; M.render(); };

      var save = M.app.querySelector("[data-f-save]");
      if (save) save.onclick = function () {
        var q = function (sel) { return M.app.querySelector(sel).value; };
        M.post("/api/admin/autoreplies", {
          chat_id: M.state.chat, id: editing || undefined,
          trigger: q("[data-f-trigger]").trim(), response: q("[data-f-response]").trim(), match: q("[data-f-match]"),
          probability: parseInt(q("[data-f-prob]"), 10), cooldown: parseInt(q("[data-f-cd]"), 10), enabled: true
        }).then(function () { M.state.cache.editReply = null; M.haptic(); M.toast(editing ? "Сохранено" : "Автоответ добавлен"); M.render(); })
          .catch(fail);
      };
    }).catch(M.fail);
  });

  // =========================================================
  // ИЗОБРАЖЕНИЯ
  // =========================================================

  M.screen("images", function () {
    Promise.all([
      M.api("/api/admin/images"),
      M.api("/api/admin/actions" + M.chatQuery()),
      M.state.chat ? settingsMap() : Promise.resolve(null)
    ]).then(function (res) {
      var d = res[0], actions = res[1].actions, m = res[2];
      var canEdit = !!M.state.chat && M.can("content");

      var cats = {};
      actions.forEach(function (a) {
        var c = cats[a.category] = cats[a.category] || { total: 0, on: 0 };
        c.total++; if (a.enabled) c.on++;
      });

      var html = M.backButton("Маруська") + M.chatPicker()
        + '<div class="card"><div class="card-title">Источники</div>'
        + d.providers.map(function (p, i) {
            return '<div class="setting" style="' + (p.active ? "" : "opacity:.5") + '"><div class="ico">' + (p.builtin ? "∞" : (p.order || "—")) + '</div><div class="grow"><div class="t">' + esc(p.label || p.name) + "</div>"
              + '<div class="s">' + (p.builtin ? "Встроенный источник · " : "Собрано ") + num(p.total) + " · в Telegram " + num(p.cached) + " · показано " + num(p.used) + "</div></div>"
              + '<span class="tag ' + (p.ready ? "ok" : "bad") + '">' + (p.ready ? "ключ есть" : "нет ключа") + "</span>"
              + (d.owner && !p.builtin ? '<div class="row-gap" style="flex:0 0 auto;margin-left:6px">'
                  + (p.active && p.order > 1 ? '<button class="btn" data-up="' + p.name + '" style="padding:6px 9px">↑</button>' : "")
                  + '<div class="switch' + (p.active ? " on" : "") + '" data-src="' + p.name + '"></div></div>' : "")
              + "</div>";
          }).join("")
        + '<div class="dim" style="margin-top:8px">Личная библиотека — встроенный основной источник. Pixabay/Unsplash используются только как внешние источники пополнения/резерва.'
        + (d.owner ? " Порядок общий для всех групп." : " Менять порядок может только владелец бота.")
        + " Ключи API хранятся в переменных Railway.</div></div>"

        + (d.owner ? '<div class="card"><div class="card-title">🔎 Пополнение библиотеки через Pixabay</div>'
        + '<div class="dim" style="margin-bottom:8px">Пользовательские фразы сюда не попадают. Для каждого Action используется внутренний английский запрос и жёсткий фильтр: только фото, SafeSearch, размер от 800×600, популярные и исключение иллюстраций/векторов/логотипов.</div>'
        + '<select data-px-action style="width:100%;margin-bottom:7px"><option value="">Выбери Action</option>'
        + actions.filter(function(a){return a.enabled;}).map(function(a){return '<option value="'+esc(a.key)+'">'+esc((a.emoji||'')+' '+(a.title||a.key))+'</option>';}).join('')
        + '</select>'
        + '<div data-px-profile class="dim" style="margin-bottom:7px">После выбора Action здесь появится внутренний Pixabay-профиль.</div>'
        + '<div class="row-gap" style="margin-top:7px"><input data-px-tag placeholder="Категория библиотеки: кошки" style="flex:1"><button class="btn" data-px-search>🔍 Найти</button></div>'
        + '<div data-px-results style="display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin-top:10px"></div>'
        + '<button class="btn block" data-px-import style="margin-top:8px;display:none">📥 Импортировать выбранные</button>'
        + '</div>' : "")
        + '<div class="card"><div class="card-title">Подбор</div>'
        + '<div class="setting"><div class="ico">🔁</div><div class="grow"><div class="t">Защита от повторов</div><div class="s">Картинка не повторится, пока не покажут всю коллекцию</div></div><span class="tag ok">всегда</span></div>'
        + (m ? '<div class="setting"><div class="ico">⏱</div><div class="grow"><div class="t">Лимит в час</div><div class="s">Сверх лимита действие уходит текстом</div></div><span class="tag">' + (m.image_limit_hour.value || "∞") + "</span></div>"
          + '<button class="btn block" data-open="settings" data-arg="Общение" style="margin-top:8px">Изменить лимит</button>' : "")
        + "</div>"

        + '<div class="card"><div class="card-title">Категории</div>'
        + (M.state.chat ? "" : '<div class="dim" style="margin-bottom:8px">Выбери группу, чтобы включать и выключать.</div>')
        + Object.keys(cats).map(function (c) {
            var on = cats[c].on > 0;
            return '<div class="setting"><div class="grow"><div class="t">' + esc(CATEGORY_TITLES[c] || c) + '</div><div class="s">включено ' + cats[c].on + " из " + cats[c].total + "</div></div>"
              + (canEdit ? '<div class="switch' + (on ? " on" : "") + '" data-cat-toggle="' + c + '"></div>' : "") + "</div>";
          }).join("") + "</div>";

      M.app.innerHTML = html;
      M.bind();

      var saveOrder = function (order) {
        M.post("/api/admin/images/order", { order: order })
          .then(function () { M.toast("Порядок сохранён"); M.render(); })
          .catch(function (e) { M.toast(e.message); });
      };

      var activeOrder = function () {
        return d.providers.filter(function (p) { return p.active; }).map(function (p) { return p.name; });
      };

      each("[data-up]", function (el) {
        el.onclick = function () {
          var order = activeOrder(), name = el.getAttribute("data-up"), i = order.indexOf(name);
          if (i > 0) { order.splice(i, 1); order.splice(i - 1, 0, name); saveOrder(order); }
        };
      });

      each("[data-src]", function (el) {
        el.onclick = function () {
          var name = el.getAttribute("data-src"), order = activeOrder();
          var i = order.indexOf(name);
          if (i >= 0) order.splice(i, 1); else order.push(name);
          if (!order.length) { M.toast("Нужен хотя бы один источник"); return; }
          saveOrder(order);
        };
      });

             var pxSelected = {};
       var pxSearch = M.app.querySelector("[data-px-search]");
       var pxResults = M.app.querySelector("[data-px-results]");
       var pxImport = M.app.querySelector("[data-px-import]");
       var pxAction = M.app.querySelector("[data-px-action]");
       var pxProfile = M.app.querySelector("[data-px-profile]");
       function renderPxSelected() { if (!pxImport) return; var n=Object.keys(pxSelected).length; pxImport.style.display=n?"block":"none"; pxImport.textContent="📥 Импортировать выбранные ("+n+")"; }
       function showProfile(a){ if(!pxProfile)return; if(!a){pxProfile.textContent="После выбора Action здесь появится внутренний Pixabay-профиль.";return;} var q=(a.search||""); var cat=(a.category||""); pxProfile.innerHTML="<b>Внутренний запрос:</b> "+esc(q)+"<br><b>Категория:</b> "+esc(cat||"авто")+"<br><b>Фильтр:</b> только фото · SafeSearch · ≥800×600 · popular · без illustration/vector/cartoon/logo"; }
       if (pxAction) pxAction.onchange=function(){var a=(actions||[]).find(function(x){return String(x.key)===String(pxAction.value);});showProfile(a);pxSelected={};renderPxSelected();if(pxResults)pxResults.innerHTML="";};
       if (pxSearch) pxSearch.onclick=function(){ var key=(pxAction&&pxAction.value)||""; if(!key){M.toast("Выбери Action");return;} var tag=(M.app.querySelector("[data-px-tag]").value||"").trim(); if(!tag){M.toast("Укажи категорию библиотеки");return;} var params=new URLSearchParams({action:key,page:"1"}); pxSearch.disabled=true; M.api("/api/admin/pixabay/search?"+params.toString()).then(function(r){ pxResults.innerHTML=(r.photos||[]).map(function(p){var on=!!pxSelected[p.id];return '<div data-px-id="'+esc(p.id)+'" style="position:relative;border:2px solid '+(on?'var(--accent-2)':'var(--line)')+';border-radius:10px;overflow:hidden;cursor:pointer;background:var(--card)" title="'+esc(p.tags)+'"><img src="'+esc(p.url)+'" style="width:100%;height:110px;object-fit:cover;display:block"><div style="position:absolute;right:5px;top:5px;background:rgba(0,0,0,.65);border-radius:99px;padding:2px 6px">'+(on?'✓':'＋')+'</div></div>';}).join("")||'<div class="dim" style="grid-column:1/-1">Ничего не найдено.</div>'; each("[data-px-id]",function(el){el.onclick=function(){var id=el.getAttribute("data-px-id"),photo=(r.photos||[]).find(function(x){return String(x.id)===String(id);});if(!photo)return;if(pxSelected[id])delete pxSelected[id];else pxSelected[id]=photo;el.style.borderColor=pxSelected[id]?"var(--accent-2)":"var(--line)";el.querySelector("div").textContent=pxSelected[id]?"✓":"＋";renderPxSelected();};}); }).catch(function(e){M.toast(e.message);}).finally(function(){pxSearch.disabled=false;}); };
       if (pxImport) pxImport.onclick=function(){var tag=(M.app.querySelector("[data-px-tag]").value||"").trim(),chosen=Object.keys(pxSelected).map(function(k){return pxSelected[k];});if(!tag){M.toast("Укажи категорию библиотеки");return;}if(!chosen.length){M.toast("Выбери картинки");return;}pxImport.disabled=true;M.post("/api/admin/pixabay/import",{tag:tag,photos:chosen,action:(pxAction&&pxAction.value)||""}).then(function(r){M.toast("Импортировано: "+r.imported+(r.duplicates?", дублей: "+r.duplicates:""));pxSelected={};renderPxSelected();M.render();}).catch(function(e){M.toast(e.message);}).finally(function(){pxImport.disabled=false;});}; renderPxSelected();

       each("[data-cat-toggle]", function (el) {
        el.onclick = function () {
          var next = !el.classList.contains("on");
          var c = el.getAttribute("data-cat-toggle");
          M.confirm((next ? "Включить" : "Выключить") + " всю категорию?", (CATEGORY_TITLES[c] || c) + ": " + cats[c].total + " действий.", next ? "Включить" : "Выключить", !next)
            .then(function (yes) {
              if (!yes) return;
              M.post("/api/admin/actions/category", { chat_id: M.state.chat, category: c, enabled: next })
                .then(function (r) { M.state.cache.actions = null; M.toast((next ? "Включено " : "Выключено ") + r.count); M.render(); })
                .catch(function (e) { M.toast(e.message); });
            });
        };
      });
    }).catch(M.fail);
  });

  // =========================================================
  // МОЯ КОЛЛЕКЦИЯ (владелец)
  // =========================================================

  M.screen("library", function () {
    M.api("/api/admin/library").then(function (d) {
      var html = '<div class="card glow"><div class="card-title">Как пополнять</div>'
        + '<div style="font-size:14px;line-height:1.5">Отправь Маре <b>в личку</b> фото или альбом с подписью <code>#пиво</code> — '
        + "всё улетит в коллекцию «пиво». Бот сам привяжет её к действию, если поймёт по названию.</div>"
        + '<div class="dim" style="margin-top:6px">Список коллекций в личке — команда /collections</div></div>';

      html += '<div class="card"><div class="card-title">Коллекции <span class="dim">' + d.collections.length + "</span></div>"
        + (d.collections.length ? d.collections.map(function (c) {
            var status = c.targets.length ? "" : c.as_action
              ? ' · <span style="color:var(--green)">своё действие</span>'
              : ' · <span style="color:var(--gold)">не привязана</span>';
            return '<div class="list-item tap" data-open="library_tag" data-arg="' + esc(c.tag) + '">'
              + '<span style="font-size:24px;width:38px;text-align:center">' + esc(c.emoji || "🖼") + "</span>"
              + '<div class="grow"><div class="t">#' + esc(c.tag.replace(/ /g, "_")) + "</div>"
              + '<div class="s">' + c.count + " фото · показано " + c.shows + status + "</div></div>"
              + '<span class="chev">›</span></div>';
          }).join("") : '<div class="dim">Пока пусто — пришли первый альбом</div>')
        + '<div class="row-gap" style="margin-top:10px"><input data-new-emoji value="✨" style="width:60px;text-align:center">'
        + '<input data-new-tag placeholder="Новая категория, например булочка"><button class="btn" data-new-col>+</button></div>'
        + '<div class="dim" style="margin-top:6px">Можно создать заранее, а фото догрузить потом с тем же #хэштегом.</div>'
        + "</div>";

      if (d.missing.length) {
        html += '<div class="card"><div class="card-title">Что догрузить</div>'
          + '<div class="dim" style="margin-bottom:8px">Популярные действия без своих картинок — сейчас для них берётся Pixabay</div>'
          + d.missing.slice(0, 15).map(function (m) {
              return '<div class="kv"><span class="k">' + m.emoji + " " + esc(m.title) + ' <span class="dim">#' + esc(m.title.toLowerCase().replace(/ /g, "_")) + "</span></span>"
                + "<span>" + (m.usage ? m.usage + " за месяц" : "—") + "</span></div>";
            }).join("")
          + (d.cats_covered ? "" : '<div class="kv"><span class="k">🐱 Котики <span class="dim">#кошки</span></span><span>—</span></div>')
          + "</div>";
      }

      M.app.innerHTML = M.backButton("Маруська") + html;
      M.bind();

      M.app.querySelector("[data-new-col]").onclick = function () {
        var tag = M.app.querySelector("[data-new-tag]").value.trim();
        if (!tag) { M.toast("Напиши название"); return; }

        M.post("/api/admin/library/collection", { tag: tag, emoji: M.app.querySelector("[data-new-emoji]").value, create: true })
          .then(function (r) { M.toast("Категория создана"); M.open("library_tag", r.tag); })
          .catch(function (e) { M.toast(e.message); });
      };
    }).catch(M.fail);
  });

  // ---------- коллекция как своё действие ----------

  function actionCard(tag, col) {
    var on = !!col.as_action;
    var triggers = [tag].concat(col.triggers || []);

    return '<div class="card glow"><div class="setting" style="border:0;padding:0">'
      + '<input data-c-emoji value="' + esc(col.emoji || "✨") + '" style="width:54px;text-align:center;font-size:20px;padding:6px">'
      + '<div class="grow"><div class="t">Своё действие</div><div class="s">'
      + (on ? "Ответь кому-нибудь в группе словом «" + esc(tag) + "» — придёт фото отсюда" : "Выключено: фото только для привязанных действий")
      + "</div></div>"
      + '<div class="switch' + (on ? " on" : "") + '" data-c-action></div></div>'

      + (on ? '<div class="dim" style="margin:12px 0 6px">Слова-триггеры (в любой форме: «' + esc(tag) + "», «" + esc(tag.slice(0, -1)) + "у»…)</div>"
          + triggers.map(function (w, i) {
              return '<span class="tag" style="margin:0 4px 6px 0">' + esc(w) + (i ? ' <b data-c-untrig="' + esc(w) + '" style="cursor:pointer">×</b>' : "") + "</span>";
            }).join("")
          + '<div class="row-gap" style="margin-top:6px"><input data-c-trig placeholder="Ещё слово, например плюшка"><button class="btn" data-c-addtrig>+</button></div>'
          + '<div class="dim" style="margin:12px 0 6px">Фраза (пусто — одна из стандартных)</div>'
          + '<textarea data-c-phrase rows="2" placeholder="{emoji} {actor} <угостил|угостила> {target_acc}: <b>{item}</b>">' + esc(col.phrase || "") + "</textarea>"
          + '<div class="dim" style="margin-top:4px">{actor} — кто, {target_acc} / {target_dat} — кому, {item} — «' + esc(tag) + "», &lt;угостил|угостила&gt; — род</div>"
          + '<button class="btn block" data-c-save style="margin-top:8px">💾 Сохранить</button>'
        : "")
      + "</div>";
  }

  function bindActionCard(tag, col) {
    var save = function (data, ok) {
      return M.post("/api/admin/library/collection", Object.assign({ tag: tag }, data))
        .then(function () { M.toast(ok || "Сохранено"); M.render(); })
        .catch(function (e) { M.toast(e.message); });
    };

    var sw = M.app.querySelector("[data-c-action]");
    if (sw) sw.onclick = function () { save({ as_action: !col.as_action }, col.as_action ? "Действие выключено" : "Теперь это действие"); };

    var add = M.app.querySelector("[data-c-addtrig]");
    if (add) add.onclick = function () {
      var word = M.app.querySelector("[data-c-trig]").value.trim();
      if (!word) return;
      save({ triggers: (col.triggers || []).concat([word]) }, "Слово добавлено");
    };

    M.each("[data-c-untrig]", function (el) {
      el.onclick = function () {
        var word = el.getAttribute("data-c-untrig");
        save({ triggers: (col.triggers || []).filter(function (w) { return w !== word; }) }, "Слово убрано");
      };
    });

    var btn = M.app.querySelector("[data-c-save]");
    if (btn) btn.onclick = function () {
      save({ emoji: M.app.querySelector("[data-c-emoji]").value, phrase: M.app.querySelector("[data-c-phrase]").value });
    };

    var emoji = M.app.querySelector("[data-c-emoji]");
    if (emoji && !btn) emoji.onchange = function () { save({ emoji: emoji.value }); };
  }

  M.screen("library_tag", function (tag) {
    var limits = M.state.cache.libLimit || (M.state.cache.libLimit = {});
    var limit = limits[tag] || 60;

    Promise.all([
      M.api("/api/admin/library/images?tag=" + encodeURIComponent(tag) + "&limit=" + limit),
      M.api("/api/admin/library")
    ]).then(function (res) {
      var images = res[0].images, meta = res[1];
      var col = meta.collections.filter(function (c) { return c.tag === tag; })[0]
        || { tag: tag, targets: [], count: 0, shows: 0, emoji: "✨", as_action: false, triggers: [], phrase: null };

      var titles = {};
      meta.targets.forEach(function (t) { titles[t.key] = t.title; });

      var html = M.backButton("Моя коллекция")
        + '<div class="screen-head">' + M.tile("image", "green", 22) + '<div class="grow"><h1>#' + esc(tag.replace(/ /g, "_")) + "</h1>"
        + '<div class="sub">' + col.count + " фото · показано " + col.shows + "</div></div></div>"

        + actionCard(tag, col)

        + '<div class="card"><div class="card-title">Привязана к встроенным действиям</div>'
        + (col.targets.length ? col.targets.map(function (t) {
            return '<span class="tag" style="margin:0 6px 6px 0">' + esc(titles[t] || t) + ' <b data-unlink="' + esc(t) + '" style="cursor:pointer">×</b></span>';
          }).join("") : '<div class="dim" style="margin-bottom:6px">Ни к чему — картинки пока не используются</div>')
        + '<select data-link style="margin-top:6px"><option value="">+ Привязать к действию…</option>'
        + meta.targets.filter(function (t) { return col.targets.indexOf(t.key) < 0; }).map(function (t) {
            return '<option value="' + t.key + '">' + esc(t.title) + "</option>";
          }).join("") + "</select>"
        + '<div class="dim" style="margin-top:6px">Одну коллекцию можно привязать к нескольким действиям: «алкоголь» — к пиву, вину и коктейлю.</div></div>'

        + '<div class="card"><div class="card-title">Фото</div><div class="action-grid">'
        + images.map(function (im) {
            return '<div class="action-card" style="cursor:default"><div class="img" style="height:100px" data-img="/api/admin/library/image?id=' + im.id + '">🖼</div>'
              + '<div class="b"><div class="s">показано ' + im.shows + (im.last_used ? " · " + M.ago(im.last_used) : "") + "</div>"
              + '<button class="btn danger block" data-del-img="' + im.id + '" style="margin-top:6px;padding:6px">Удалить</button></div></div>';
          }).join("") + "</div>"
        + (images.length ? "" : '<div class="dim">Фото нет</div>')
        + (col.count > images.length ? '<button class="btn block" data-lib-more style="margin-top:10px">Показать ещё (' + (col.count - images.length) + ")</button>" : "")
        + "</div>"

        + '<button class="btn danger block" data-del-col>🗑 Удалить всю коллекцию</button>';

      M.app.innerHTML = html;
      M.bind();

      var fail = function (e) { M.toast(e.message); };
      var link = function (target, linked) {
        M.post("/api/admin/library/link", { tag: tag, target: target, linked: linked })
          .then(function () { M.toast(linked ? "Привязано" : "Отвязано"); M.render(); }).catch(fail);
      };

      M.app.querySelector("[data-link]").onchange = function (e) { if (e.target.value) link(e.target.value, true); };
      bindActionCard(tag, col);

      var more = M.app.querySelector("[data-lib-more]");
      if (more) more.onclick = function () { limits[tag] = limit + 60; M.render(); };
      M.each("[data-unlink]", function (el) { el.onclick = function () { link(el.getAttribute("data-unlink"), false); }; });

      M.each("[data-del-img]", function (el) {
        el.onclick = function () {
          M.post("/api/admin/library/delete", { id: parseInt(el.getAttribute("data-del-img"), 10) })
            .then(function () { M.toast("Удалено"); M.render(); }).catch(fail);
        };
      });

      M.app.querySelector("[data-del-col]").onclick = function () {
        M.confirm("Удалить коллекцию #" + tag + "?", "Все " + col.count + " фото пропадут из коллекции. Действия снова будут брать картинки из Pixabay.", "Удалить", true)
          .then(function (yes) {
            if (!yes) return;
            M.post("/api/admin/library/delete", { tag: tag }).then(function () { M.toast("Коллекция удалена"); M.back(); }).catch(fail);
          });
      };
    }).catch(M.fail);
  });
})();
