/* ===========================================================
   Настройки группы и меню «Ещё».
   =========================================================== */

(function () {
  var M = window.Mara, esc = M.esc, num = M.num, each = M.each;
  var CATEGORY_TITLES = M.CATEGORY_TITLES, settingsMap = M.settingsMap, needChatScreen = M.needChatScreen;

  // =========================================================
  // НАСТРОЙКИ (весь список или один раздел)
  // =========================================================

  var SECTION_PERMISSION = {
    "Маруська": "content", "Действия": "content", "Экономика": "economy", "Жизнь чата": "settings",
    "Модерация": "moderation", "Антимат": "moderation", "Развлечения": "games"
  };

  // Дни рождения группы: список с правкой даты и удалением
  function loadBirthdays(canEdit) {
    var box = M.app.querySelector("[data-bdays]");
    if (!box) return;
    M.api("/api/admin/birthdays" + M.chatQuery()).then(function (d) {
      var rows = d.people.map(function (p) {
        var when = p.days_left === 0 ? "сегодня 🎉" : p.days_left === 1 ? "завтра" : p.days_left === 2 ? "послезавтра" : "через " + p.days_left + " дн.";
        return '<div class="list-item"><div class="grow"><b>' + esc(p.name) + '</b><div class="s dim">' + when + "</div></div>"
          + (canEdit
            ? '<input data-bd-date="' + p.telegram_id + '" value="' + p.date + '" style="width:72px;text-align:center">'
              + '<button class="btn" data-bd-save="' + p.telegram_id + '" style="padding:6px 9px">✓</button>'
              + '<button class="btn danger" data-bd-del="' + p.telegram_id + '" style="padding:6px 9px">×</button>'
            : '<b>' + p.date + "</b>")
          + "</div>";
      }).join("") || '<div class="dim">Пока никто не сказал Маре свой день рождения. Мара будет спрашивать сама, а ещё можно написать в группе «мой др 15.03».</div>';
      box.innerHTML = '<div class="card-title">🎂 Дни рождения участников <span class="dim">' + d.people.length + "</span></div>" + rows;

      var send = function (uid, date) {
        M.post("/api/admin/birthdays", { chat_id: M.state.chat, telegram_id: uid, date: date })
          .then(function () { M.toast(date ? "Дата сохранена" : "Удалено"); loadBirthdays(canEdit); })
          .catch(function (e) { M.toast(e.message); });
      };
      each("[data-bd-save]", function (b) {
        b.onclick = function () { var uid = +b.getAttribute("data-bd-save"); send(uid, box.querySelector('[data-bd-date="' + uid + '"]').value.trim()); };
      });
      each("[data-bd-del]", function (b) { b.onclick = function () { send(+b.getAttribute("data-bd-del"), null); }; });
    }).catch(function () { box.innerHTML = '<div class="dim">Не удалось загрузить дни рождения</div>'; });
  }

  // Видео к приветствию: файл уходит телом запроса, Мара шлёт превью в личку
  function bindGreetingMedia() {
    var box = M.app.querySelector("[data-gmedia]");
    if (!box) return;
    var state = box.querySelector("[data-gmedia-state]"), del = box.querySelector("[data-gmedia-del]");
    var KIND = { video: "🎬 видео", animation: "🎞 GIF", photo: "🖼 фото" };

    var show = function (media) {
      state.textContent = media ? "Прикреплено: " + (KIND[media.kind] || "") + (media.name ? " — " + media.name : "") : "Не прикреплено — новичков встречает только текст.";
      del.classList.toggle("hidden", !media);
    };

    M.api("/api/admin/greeting_media" + M.chatQuery()).then(function (d) { show(d.media); }).catch(function () { state.textContent = "Не удалось проверить"; });

    box.querySelector("[data-gmedia-file]").onchange = function () {
      var file = this.files[0];
      if (!file) return;
      if (file.size > 20 * 1024 * 1024) { M.toast("Файл больше 20 МБ"); return; }
      var kind = /gif$/i.test(file.type) ? "animation" : /^image\//.test(file.type) ? "photo" : "video";
      state.textContent = "Загружаю… (" + Math.round(file.size / 1024 / 1024 * 10) / 10 + " МБ)";
      M.api("/api/admin/greeting_media" + M.chatQuery() + "&kind=" + kind + "&name=" + encodeURIComponent(file.name || ""), {
        method: "POST", body: file, headers: { "Content-Type": file.type || "application/octet-stream" }
      }).then(function (d) { M.haptic(); M.toast("Видео прикреплено, превью — в личке"); show(d.media); })
        .catch(function (e) { M.toast(e.message); state.textContent = "Не загрузилось: " + e.message; });
    };

    del.onclick = function () {
      M.post("/api/admin/greeting_media/delete", { chat_id: M.state.chat })
        .then(function () { M.toast("Видео убрано"); show(null); }).catch(function (e) { M.toast(e.message); });
    };
  }

  M.screen("settings", function (only) {
    if (!M.state.chat) {
      M.app.innerHTML = M.backButton() + M.chatPicker(false) + '<div class="center muted">Настройки задаются для каждой группы отдельно — выбери группу.</div>';
      M.bind();
      return;
    }

    M.api("/api/admin/settings" + M.chatQuery()).then(function (d) {
      // Аргумент — раздел («Экономика») или подборка «keys:Заголовок:ключ1,ключ2»
      // для экранов-хабов: открывается только то, о чём строка
      var picked = null, pickedTitle = "";
      if (only && only.indexOf("keys:") === 0) {
        var rest = only.slice(5), cut = rest.lastIndexOf(":");
        pickedTitle = rest.slice(0, cut);
        picked = rest.slice(cut + 1).split(",");
      }

      var sections = d.sections.filter(function (s) { return picked || !only || s.name === only; });
      if (picked) {
        sections = sections.map(function (s) {
          return { name: s.name, items: s.items.filter(function (i) { return picked.indexOf(i.key) >= 0; }) };
        }).filter(function (s) { return s.items.length; });
        // В порядке, в каком ключи перечислены в подборке
        var flat = [];
        sections.forEach(function (s) { s.items.forEach(function (i) { i._section = s.name; flat.push(i); }); });
        flat.sort(function (a, b) { return picked.indexOf(a.key) - picked.indexOf(b.key); });
        sections = flat.length ? [{ name: pickedTitle, items: flat, picked: true }] : [];
      }
      var index = {};

      var html = M.backButton() + M.chatPicker(false);

      sections.forEach(function (sec) {
        var canSection = function (name) { return M.can(SECTION_PERMISSION[name] || "settings"); };
        var editable = sec.picked
          ? sec.items.every(function (i) { return canSection(i._section); })
          : canSection(sec.name);

        html += '<div class="card"><div class="card-title">' + esc(sec.name)
          + (editable ? "" : ' <span class="tag">только просмотр</span>') + "</div>";

        sec.items.forEach(function (it) {
          index[it.key] = it;
          it.editable = sec.picked ? canSection(it._section) : editable;

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

      var withMedia = picked && picked.indexOf("greeting_text") >= 0 && M.can("settings");
      if (withMedia) {
        html += '<div class="card" data-gmedia><div class="card-title">🎬 Видео к приветствию</div>'
          + '<div class="dim" data-gmedia-state>Проверяю…</div>'
          + '<div class="btns" style="margin-top:8px">'
          + '<label class="btn primary" style="margin:0">Загрузить видео или GIF<input type="file" accept="video/*,image/gif" data-gmedia-file class="hidden"></label>'
          + '<button class="btn danger hidden" data-gmedia-del>Убрать</button></div>'
          + '<div class="dim" style="margin-top:8px">До 20 МБ, лучше MP4. Превью придёт тебе в личку от Мары. '
          + 'Ещё способ: в группе ответь на видео командой <code>/welcomevideo</code>.</div></div>';
      }

      var withBirthdays = picked && picked.indexOf("birthdays") >= 0;
      if (withBirthdays) html += '<div class="card" data-bdays><div class="card-title">🎂 Дни рождения участников</div><div class="dim">Загружаю…</div></div>';

      M.app.innerHTML = html;
      M.bind();

      if (withMedia) bindGreetingMedia();
      if (withBirthdays) loadBirthdays(M.can("settings"));

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

  // Разделы сгруппированы по задачам: развлечения, экономика, жизнь чата,
  // контроль, управление. Каждая строка показывает текущее состояние.
  M.screen("more", function () {
    var owner = M.state.session.user.owner;

    M.settingsIndex().then(function (k) {
      var has = Object.keys(k).length > 0;
      var v = function (key) { return k[key] ? k[key].value : null; };
      var l = function (key) { return k[key] ? k[key].label : "—"; };
      var R = M.hubRow, on = M.onOff;
      var fresh = M.hasUpdate() ? ' <span class="tag new">новое</span>' : "";
      var games = has ? [v("game_table") && "игры в чате", v("game_crocodile") && "крокодил", v("game_dice") && "кубики", v("fishing") && "рыбалка"].filter(Boolean) : [];

      var html = M.header("Ещё", "Все разделы панели", "menu", "blue")
        + '<div class="list-item tap hub-search" data-open="search">' + M.icon("search", 19)
        + '<div class="grow">Найти настройку, человека, действие…</div></div>'

        + M.hubSection("Развлечения", [
            R("zap", "gold", "Действия и картинки",
              has ? on(v("actions"), "Включены", "Выключены") + " · " + (v("image_limit_hour") ? "до " + l("image_limit_hour") + " картинок в час" : "картинки без лимита") : "Пиво, обнять, цветы и ещё 200", "content"),
            R("game", "green", "Игры", has ? (games.length ? games.join(", ") : on(false, "", "Все выключены")) : "Игры в чате, крокодил, кубики, рыбалка", "games"),
            owner ? R("game", "gold", "Арена", "Дурак онлайн: игроки, деньги, турниры", "arena") : ""
          ])

        + M.hubSection("Экономика", [
            R("diamond", "gold", "Алмазы", has ? (v("economy") ? "Бонус " + v("bonus_min") + "–" + l("bonus_max") + " · джекпот " + l("jackpot_chance") : on(false)) : "Балансы, бонус, джекпот", "diamonds"),
            R("star", "purple", "Опыт и уровни", has ? (v("progress") ? v("xp_message") + " XP за сообщение · до " + v("xp_daily_cap") + " в сутки" : on(false)) : "Опыт, уровни, таблица", "levels"),
            R("trophy", "gold", "Достижения", "Условия, награды, кто что открыл", "achievements"),
            R("heart", "red", "Карма и рейтинг", has ? on(v("rating"), "Рейтинг включён", "Рейтинг выключен") : "Голоса и рейтинг", "karma"),
            R("bag", "pink", "Магазин", "Товары, цены, покупки", "shop"),
            R("gift", "pink", "Браки и подарки", has ? (v("marriages") ? (v("marry_cost") ? "Свадьба " + l("marry_cost") : "Свадьба бесплатно") : on(false, "", "Браки выключены")) + " · подарки " + (v("gifts") ? "есть" : "выкл.") : "Свадьбы, подарки друг другу",
              "settings", "keys:Браки и подарки:marriages,marry_ring,marry_cost,gifts"),
            R("settings", "purple", "Все настройки экономики", "Бонус, опыт, рейтинг, свадьбы", "settings", "Экономика")
          ])

        + M.hubSection("Жизнь чата", [
            R("megaphone", "blue", "Рассылки", "Фото, видео, кнопки, расписание", "broadcasts"),
            R("calendar", "purple", "Итоги недели и топы", has ? on(v("digest"), "Итоги включены", "Итоги выключены") + " · топ " + (v("top_chatters") ? l("top_chatters_size") : "выкл.") : "Итоги, топ болтунов, часовой пояс",
              "settings", "keys:Итоги недели и топы:digest,digest_weekday,digest_hour,top_chatters,top_chatters_size,timezone"),
            R("heart", "pink", "Пара дня", has ? on(v("pair_of_day")) : "Кто сегодня пара", "settings", "keys:Пара дня и гармония:pair_of_day,pair_active_days,harmony"),
            R("gift", "gold", "Дни рождения", has ? on(v("birthdays"), "Подарок " + l("birthday_gift"), "Выключены") : "Напоминания и подарки",
              "settings", "keys:Дни рождения:birthdays,birthday_remind_days,birthday_hour,birthday_gift,birthday_ask_hours")
          ])

        + M.hubSection("Контроль", [
            R("chart", "blue", "Аналитика", "Графики и тепловая карта", "analytics"),
            R("journal", "purple", "Журнал", "Кто что сделал", "journal")
          ])

        + M.hubSection("Управление", [
            R("group", "green", "Группы", "Где работает Мара", "groups"),
            owner ? R("crown", "gold", "Главные админы", "Права как у создателя", "owners") : "",
            owner ? R("database", "red", "Система", "Здоровье, база, перезапуск", "system") : "",
            owner ? R("file", "red", "Логи", "Ошибки и события бота", "logs") : "",
            R("new", "pink", "Обновления", "Что нового в Маре · v" + M.version, "changelog", null, fresh)
          ]);

      if (!has) html += '<div class="dim" style="margin-top:10px">Выбери группу на главной — тут появятся её текущие значения.</div>';

      M.app.innerHTML = html;
      M.bind();
    }).catch(M.fail);
  });
})();
