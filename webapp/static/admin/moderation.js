/* ===========================================================
   Модерация: защита, нарушители, правила «условие → действие».
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;
  var CATEGORY_TITLES = M.CATEGORY_TITLES, settingsMap = M.settingsMap, needChatScreen = M.needChatScreen;

  // =========================================================
  // МОДЕРАЦИЯ
  // =========================================================

  // ---------- свои правила: «если [нарушение] N раз за M минут → действие» ----------

  var RULE_ACTIONS = [["delete", "Удалить"], ["warn", "Предупредить"], ["mute", "Мут"], ["tempban", "Бан на время"], ["ban", "Бан навсегда"]];

  function spanText(minutes) {
    if (minutes < 60) return minutes + " мин";
    if (minutes < 1440) return (minutes / 60) + " ч";
    return (minutes / 1440) + " дн";
  }

  // То же описание, что пишет сервер — чтобы админ видел правило до сохранения
  function describe(r, titles) {
    var what = r.violation === "any" ? "любое нарушение" : (titles[r.violation] || r.violation);
    var act = { delete: "удалить", warn: "предупредить", ban: "бан навсегда" }[r.action]
      || ((r.action === "mute" ? "мут на " : "бан на ") + spanText(r.duration));
    return "Если " + what + " — " + r.count + " раз за " + r.window + " мин → " + act;
  }

  function customRules(data, canEdit) {
    var titles = {};
    data.violations.forEach(function (v) { titles[v.key] = v.title; });

    var html = '<div class="card"><div class="card-title">Свои правила <span class="dim">' + data.rules.length + " из " + data.max + "</span></div>"
      + '<div class="dim" style="margin-bottom:8px">Проверяются сверху вниз, срабатывает первое подходящее. Если ни одно не подошло — действие по умолчанию ниже.</div>';

    html += data.rules.map(function (r, i) {
      return '<div class="list-item" style="' + (r.enabled ? "" : "opacity:.5") + '"><div class="grow" style="font-size:13px">' + esc(r.text) + "</div>"
        + (canEdit ? '<div class="row-gap" style="flex:0 0 auto">'
          + (i > 0 ? '<button class="btn" data-rmove="' + r.id + '" style="padding:6px 9px">↑</button>' : "")
          + '<button class="btn danger" data-rdel="' + r.id + '" style="padding:6px 9px">×</button></div>' : "")
        + "</div>";
    }).join("") || '<div class="dim">Своих правил нет</div>';

    if (canEdit && data.rules.length < data.max) {
      var opt = function (list, sel) {
        return list.map(function (o) { return '<option value="' + o[0] + '"' + (o[0] === sel ? " selected" : "") + ">" + esc(o[1]) + "</option>"; }).join("");
      };

      html += '<div style="margin-top:10px;border-top:1px solid var(--line);padding-top:10px">'
        + '<div class="dim" style="margin-bottom:6px">Новое правило</div>'
        + '<select data-r="violation" style="margin-bottom:6px">' + opt(data.violations.map(function (v) { return [v.key, v.title]; }), "flood") + "</select>"
        + '<div class="row-gap" style="margin-bottom:6px"><input type="number" data-r="count" value="3" min="1" max="50" placeholder="Сколько раз">'
        + '<input type="number" data-r="window" value="10" min="1" max="10080" placeholder="За минут"></div>'
        + '<div class="row-gap"><select data-r="action">' + opt(RULE_ACTIONS, "mute") + "</select>"
        + '<select data-r="duration">' + opt([["10", "10 мин"], ["60", "1 ч"], ["360", "6 ч"], ["1440", "1 день"], ["10080", "неделя"], ["43200", "30 дней"]], "1440") + "</select></div>"
        + '<div data-r-preview style="margin:10px 0;padding:10px;border-radius:12px;background:var(--card-2);font-size:13px"></div>'
        + '<button class="btn primary" data-r-save style="margin:0">+ Добавить правило</button></div>';
    }

    return html + "</div>";
  }

  function bindCustomRules(data) {
    var titles = {};
    data.violations.forEach(function (v) { titles[v.key] = v.title; });

    var read = function () {
      var get = function (k) { var el = M.app.querySelector('[data-r="' + k + '"]'); return el ? el.value : ""; };
      return { violation: get("violation"), count: parseInt(get("count"), 10) || 1, window: parseInt(get("window"), 10) || 1,
               action: get("action"), duration: parseInt(get("duration"), 10) || 60 };
    };

    var preview = M.app.querySelector("[data-r-preview]");
    var refresh = function () {
      if (!preview) return;
      var r = read();
      var strict = (r.action === "ban" || r.action === "tempban") && r.count === 1;
      preview.innerHTML = esc(describe(r, titles)) + (strict ? '<div style="color:var(--red);margin-top:6px">⚠️ Бан за первое же нарушение — очень строго</div>' : "");
      var dur = M.app.querySelector('[data-r="duration"]');
      if (dur) dur.style.display = (r.action === "mute" || r.action === "tempban") ? "" : "none";
    };

    M.each("[data-r]", function (el) { el.oninput = refresh; el.onchange = refresh; });
    refresh();

    var save = function (extra) {
      return M.post("/api/admin/punish_rules", Object.assign({ chat_id: M.state.chat }, read(), extra || {}));
    };

    var btn = M.app.querySelector("[data-r-save]");
    if (btn) btn.onclick = function () {
      save().then(function () { M.toast("Правило добавлено"); M.render(); }).catch(function (e) {
        if (!/подтверди/.test(e.message)) { M.toast(e.message); return; }
        M.confirm("Бан за первое нарушение?", describe(read(), titles) + ". Человек вылетит сразу, без предупреждений.", "Да, так и задумано", true)
          .then(function (yes) {
            if (!yes) return;
            save({ confirm_strict: true }).then(function () { M.toast("Правило добавлено"); M.render(); })
              .catch(function (err) { M.toast(err.message); });
          });
      });
    };

    M.each("[data-rdel]", function (el) {
      el.onclick = function () {
        M.post("/api/admin/punish_rules/delete", { chat_id: M.state.chat, id: parseInt(el.getAttribute("data-rdel"), 10) })
          .then(function () { M.toast("Удалено"); M.render(); }).catch(function (e) { M.toast(e.message); });
      };
    });

    M.each("[data-rmove]", function (el) {
      el.onclick = function () {
        M.post("/api/admin/punish_rules/move", { chat_id: M.state.chat, id: parseInt(el.getAttribute("data-rmove"), 10), direction: "up" })
          .then(function () { M.render(); }).catch(function (e) { M.toast(e.message); });
      };
    });
  }

  M.screen("moderation", function () {
    if (!M.state.chat) {
      M.app.innerHTML = M.header("Модерация", "Выбери группу", "shield", "purple") + M.chatPicker(false)
        + '<div class="center muted">Защита настраивается для каждой группы отдельно.</div>';
      M.bind();
      return;
    }

    Promise.all([
      M.api("/api/admin/settings" + M.chatQuery()),
      M.api("/api/admin/violators" + M.chatQuery()),
      M.api("/api/admin/punish_rules" + M.chatQuery()),
      M.api("/api/admin/journal" + M.chatQuery() + "&category=moderation").catch(function () { return { events: [] }; })
    ]).then(function (res) {
      var section = res[0].sections.filter(function (s) { return s.name === "Модерация"; })[0] || { items: [] };
      var byKey = {};
      section.items.forEach(function (i) { byKey[i.key] = i; });

      var val = function (k) { return byKey[k] ? byKey[k].value : null; };
      var on = val("automod");
      var rights = M.state.me.bot_rights || {};
      var canEdit = M.can("moderation");
      var canRestrict = !!rights.restrict;
      var canDelete = !!rights.delete;

      var TILE_ICONS = { "🌊": "wind", "🔁": "repeat", "🔗": "link", "🚫": "ban", "🔣": "alert", "🎭": "image" };

      var tile = function (icon, title, active, state) {
        return '<div class="menu-tile" data-open="settings" data-arg="Модерация">' + M.tile(TILE_ICONS[icon] || "shield", active ? "purple" : "blue", 19)
          + '<div class="t">' + title + '</div><div class="s" style="color:' + (active ? "var(--green)" : "var(--dim)") + '">'
          + state + "</div></div>";
      };

      var linkState = { allow: "Разрешены", newbies: "Нельзя новичкам", everyone: "Запрещены" };
      var words = (val("stop_words") || "").split(",").filter(function (w) { return w.trim(); }).length;

      var html = M.header("Модерация", "Защита и порядок", "shield", "purple") + M.chatPicker(false);

      // Без права удаления автомодерация не уберёт ни одного нарушения
      if (!canDelete) {
        html += '<div class="alert danger"><span class="ico">🗑</span><span class="grow">'
          + "У Мары нет права удалять сообщения. Автомодерация будет только предупреждать и наказывать — сами нарушения останутся в чате.</span></div>";
      }

      if (!canRestrict) {
        html += '<div class="alert danger"><span class="ico">🔑</span><span class="grow">'
          + "У Мары нет права ограничивать участников. Мут и бан недоступны — выдай ей права администратора.</span></div>";
      }

      html += '<div class="card glow" style="' + (on ? "border-color:rgba(52,211,153,.45)" : "") + '">'
        + '<div class="setting" style="border:0;padding:0"><div class="ico">🛡</div><div class="grow">'
        + '<div class="t">' + (on ? "Защита активна" : "Защита выключена") + '</div>'
        + '<div class="s">' + (on ? "Все системы работают" : "Бот не удаляет нарушения сам") + "</div></div>"
        + '<div class="switch' + (on ? " on" : "") + (canEdit ? "" : " locked") + '" data-automod></div></div></div>'

        + '<div class="menu-grid" style="margin-bottom:12px">'
        + tile("🌊", "Антифлуд", true, val("flood_messages") + " за " + val("flood_seconds") + " сек")
        + tile("🔁", "Антиспам", val("automod_repeats"), val("automod_repeats") ? "Повторы: ON" : "OFF")
        + tile("🔗", "Ссылки", val("link_policy") !== "allow", linkState[val("link_policy")] || "")
        + tile("🚫", "Стоп-слова", words > 0, words + " слов")
        + tile("🔣", "Символы", val("automod_symbols"), val("automod_symbols") ? "ON" : "OFF")
        + tile("🤖", "Капча", val("captcha"), val("captcha") ? val("captcha_minutes") + " мин на ответ" : "OFF")
        + tile("🐣", "Новички", val("newbie_no_media") || val("newbie_slowmode"),
            (val("newbie_no_media") ? "без медиа" : "медиа можно") + (val("newbie_slowmode") ? " · 1 сообщ. в " + val("newbie_slowmode") + "с" : ""))
        + tile("🎭", "Стикеры/медиа", val("sticker_limit") || val("media_limit"),
            (val("sticker_limit") || "∞") + " / " + (val("media_limit") || "∞") + " в мин")
        + "</div>";

      // --- последние нарушители с быстрыми кнопками ---
      html += '<div class="card"><div class="card-title">Нарушители за неделю <span class="link" data-open="journal">Все →</span></div>';

      if (res[1].violators.length) {
        res[1].violators.forEach(function (v) {
          html += '<div class="list-item" style="flex-wrap:wrap">'
            + '<div class="row-gap grow tap" data-open="profile" data-arg="' + v.telegram_id + '" style="align-items:center;cursor:pointer">'
            + M.avatar(v.telegram_id, v.name, "sm")
            + '<div class="grow"><div class="t">' + esc(v.name) + '</div><div class="s">' + v.warnings + " предупр. за 7 дней</div></div></div>"
            + (canEdit ? '<div class="row-gap" style="flex:0 0 auto">'
                + (canRestrict ? '<button class="btn" data-q="mute" data-u="' + v.telegram_id + '" data-n="' + esc(v.name) + '">Мут</button>'
                  + '<button class="btn danger" data-q="ban" data-u="' + v.telegram_id + '" data-n="' + esc(v.name) + '">Бан</button>' : "")
                + '<button class="btn" data-q="warn" data-u="' + v.telegram_id + '" data-n="' + esc(v.name) + '">Предупр.</button></div>' : "")
            + "</div>";
        });
      } else {
        html += '<div class="dim">Нарушений нет 🎉</div>';
      }

      html += "</div>";

      // --- конструктор: условие → действие ---
      var rules = ["act_flood", "act_repeat", "act_link", "act_stop_word", "act_symbols", "act_stickers", "act_media", "act_newbie", "warn_action"];

      html += '<div class="card"><div class="card-title">Правила: условие → действие</div>';

      rules.forEach(function (key) {
        var r = byKey[key];
        if (!r) return;

        var options = r.options.filter(function (o) {
          return canRestrict || ["delete", "warn"].indexOf(o.value) >= 0 || key === "warn_action";
        });

        html += '<div class="setting"><div class="ico">' + r.emoji + '</div><div class="grow"><div class="t">'
          + esc(r.title.replace(" →", "")) + "</div>"
          + (key === "warn_action" ? '<div class="s">после ' + val("warn_limit") + " предупреждений</div>" : "")
          + "</div>"
          + '<select data-rule="' + key + '" style="width:auto;max-width:52%"' + (canEdit ? "" : " disabled") + ">"
          + options.map(function (o) {
              return '<option value="' + o.value + '"' + (o.value === r.value ? " selected" : "") + ">" + o.emoji + " " + esc(o.label.replace("Удалить + ", "")) + "</option>";
            }).join("") + "</select></div>";
      });

      html += '<div class="dim" style="margin-top:8px">Мут и временный бан — на ' + val("punish_minutes") + " мин. Сообщение-нарушение удаляется всегда.</div></div>"

        + customRules(res[2], canEdit)

        + '<div class="card"><div class="card-title">Последние действия</div>'
        + (res[3].events.length ? res[3].events.slice(0, 8).map(M.eventRow).join("") : '<div class="dim">Пока пусто</div>')
        + "</div>"

        + '<button class="btn primary" data-open="settings" data-arg="Модерация">⚙️ Настроить правила</button>';

      M.app.innerHTML = html;
      M.bind();
      bindCustomRules(res[2]);

      var sw = M.app.querySelector("[data-automod]");
      if (sw && canEdit) sw.onclick = function () {
        var next = !sw.classList.contains("on");
        sw.classList.toggle("on", next);
        M.post("/api/admin/settings", { chat_id: M.state.chat, key: "automod", value: next })
          .then(function () { M.toast(next ? "Защита включена" : "Защита выключена"); M.haptic(); M.render(); })
          .catch(function (e) { sw.classList.toggle("on", !next); M.toast(e.message); });
      };

      Array.prototype.forEach.call(M.app.querySelectorAll("[data-rule]"), function (sel) {
        sel.onchange = function () {
          M.post("/api/admin/settings", { chat_id: M.state.chat, key: sel.getAttribute("data-rule"), value: sel.value })
            .then(function () { M.toast("Правило сохранено"); M.haptic(); })
            .catch(function (e) { M.toast(e.message); });
        };
      });

      Array.prototype.forEach.call(M.app.querySelectorAll("[data-q]"), function (btn) {
        btn.onclick = function () {
          var action = btn.getAttribute("data-q");
          var user = parseInt(btn.getAttribute("data-u"), 10);
          var name = btn.getAttribute("data-n");

          var go = function () {
            M.post("/api/admin/moderate", { action: action, chat_id: M.state.chat, user_id: user, minutes: val("punish_minutes") || 60 })
              .then(function () {
                M.haptic("medium");
                M.toast({ mute: "Замучен", ban: "Забанен", warn: "Предупреждение выдано" }[action]);
                if (action !== "warn") M.render();
              })
              .catch(function (e) { M.toast(e.message); });
          };

          if (action === "ban") {
            M.confirm("Забанить " + name + "?", "Человек вылетит из группы и не сможет вернуться, пока его не разбанят.", "Забанить", true)
              .then(function (y) { if (y) go(); });
          } else { go(); }
        };
      });
    }).catch(M.fail);
  });
})();
