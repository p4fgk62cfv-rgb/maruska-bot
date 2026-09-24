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
            return '<div class="setting" style="' + (p.active ? "" : "opacity:.5") + '"><div class="ico">' + (p.order || "—") + '</div><div class="grow"><div class="t">' + esc(p.name) + "</div>"
              + '<div class="s">Собрано ' + num(p.total) + " · в Telegram " + num(p.cached) + " · показано " + num(p.used) + "</div></div>"
              + '<span class="tag ' + (p.ready ? "ok" : "bad") + '">' + (p.ready ? "ключ есть" : "нет ключа") + "</span>"
              + (d.owner ? '<div class="row-gap" style="flex:0 0 auto;margin-left:6px">'
                  + (p.active && p.order > 1 ? '<button class="btn" data-up="' + p.name + '" style="padding:6px 9px">↑</button>' : "")
                  + '<div class="switch' + (p.active ? " on" : "") + '" data-src="' + p.name + '"></div></div>' : "")
              + "</div>";
          }).join("")
        + '<div class="dim" style="margin-top:8px">Сначала опрашивается первый источник, при ошибке — следующий.'
        + (d.owner ? " Порядок общий для всех групп." : " Менять порядок может только владелец бота.")
        + " Ключи API хранятся в переменных Railway.</div></div>"

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
})();
