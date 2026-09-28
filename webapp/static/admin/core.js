/* ===========================================================
   Ядро панели: запросы, состояние, навигация, общие элементы.
   Экраны регистрируются в screens.js через Mara.screen().
   =========================================================== */

(function () {
  var tg = window.Telegram && window.Telegram.WebApp;
  if (tg) { tg.ready(); tg.expand(); try { tg.setHeaderColor("#0b0816"); tg.setBackgroundColor("#0b0816"); } catch (e) {} }

  var Mara = window.Mara = {
    tg: tg,
    initData: (tg && tg.initData) || "",
    version: window.MARA_VERSION || "?",
    screens: {},
    state: {
      tab: "home",
      stack: [],          // вложенные экраны: [{name, arg}]
      chat: null,
      session: null,
      me: null,
      cache: {}
    }
  };

  var app = document.getElementById("app");
  Mara.app = app;

  // ---------- утилиты ----------

  Mara.esc = function (v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  };

  Mara.num = function (v) {
    return String(Math.round(v || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  };

  Mara.ago = function (iso) {
    if (!iso) return "давно";
    var diff = (Date.now() - new Date(iso + (iso.endsWith("Z") ? "" : "Z")).getTime()) / 1000;
    if (diff < 0) diff = 0;
    if (diff < 300) return "онлайн";
    if (diff < 3600) return Math.floor(diff / 60) + " мин назад";
    if (diff < 86400) return Math.floor(diff / 3600) + " ч назад";
    return Math.floor(diff / 86400) + " дн назад";
  };

  Mara.time = function (iso) {
    var d = new Date(iso + (iso.endsWith("Z") ? "" : "Z"));
    var p = function (n) { return (n < 10 ? "0" : "") + n; };
    return p(d.getDate()) + "." + p(d.getMonth() + 1) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
  };

  Mara.haptic = function (kind) {
    try { tg.HapticFeedback.impactOccurred(kind || "light"); } catch (e) {}
  };

  // ---------- запросы ----------

  Mara.api = function (path, options) {
    options = options || {};
    options.headers = Object.assign(
      { "X-Init-Data": Mara.initData, "Content-Type": "application/json" },
      options.headers || {}
    );

    return fetch(path, options).then(function (response) {
      return response.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) {}

        if (!response.ok || (data && data.ok === false)) {
          var error = new Error((data && data.error) || humanError(response.status, text));
          error.status = response.status;
          throw error;
        }

        return data;
      });
    });
  };

  Mara.post = function (path, body) {
    return Mara.api(path, { method: "POST", body: JSON.stringify(body) });
  };

  function humanError(status, text) {
    if (status === 403) {
      if (/permission/.test(text)) return "Недостаточно прав для этого действия";
      if (/owner only/.test(text)) return "Только для владельца бота";
      return "Нет доступа";
    }
    if (status === 401) return "Открой панель заново из Telegram";
    return "Не получилось (" + status + ")";
  }

  Mara.chatQuery = function (prefix) {
    return (prefix || "?") + (Mara.state.chat ? "chat_id=" + Mara.state.chat : "");
  };

  Mara.can = function (permission) {
    var me = Mara.state.me;
    if (!me) return false;
    return me.permissions.indexOf("*") >= 0 || me.permissions.indexOf(permission) >= 0;
  };

  // ---------- аватарки: <img> не умеет слать заголовок авторизации ----------

  var imageCache = {};

  Mara.loadImages = function (root) {
    Array.prototype.forEach.call((root || app).querySelectorAll("[data-img]"), function (el) {
      var url = el.getAttribute("data-img");
      el.removeAttribute("data-img");

      function apply(src) { if (src) el.innerHTML = '<img src="' + src + '" alt="">'; }

      if (url in imageCache) { apply(imageCache[url]); return; }

      fetch(url, { headers: { "X-Init-Data": Mara.initData } })
        .then(function (r) { if (!r.ok) throw 0; return r.blob(); })
        .then(function (b) { imageCache[url] = URL.createObjectURL(b); apply(imageCache[url]); })
        .catch(function () { imageCache[url] = null; });
    });
  };

  Mara.avatar = function (userId, name, cls) {
    return '<div class="avatar ' + (cls || "") + '" data-img="/api/admin/avatar?user_id=' + userId + '">'
      + Mara.esc((name || "?").slice(0, 1).toUpperCase()) + "</div>";
  };

  // ---------- всплывашка с отменой ----------

  var toastEl = document.getElementById("toast");
  var toastTimer = null;

  Mara.toast = function (text, undo) {
    clearTimeout(toastTimer);
    toastEl.innerHTML = "<span>" + Mara.esc(text) + "</span>"
      + (undo ? '<span class="undo">Отменить</span>' : "");
    toastEl.classList.add("show");

    if (undo) {
      toastEl.querySelector(".undo").onclick = function () {
        toastEl.classList.remove("show");
        undo();
      };
    }

    toastTimer = setTimeout(function () { toastEl.classList.remove("show"); }, undo ? 6000 : 2200);
  };

  // ---------- подтверждение опасных действий ----------

  Mara.confirm = function (title, text, okLabel, danger) {
    return new Promise(function (resolve) {
      var bg = document.createElement("div");
      bg.className = "sheet-bg";
      bg.innerHTML = '<div class="sheet"><div class="grip"></div>'
        + "<h3>" + Mara.esc(title) + "</h3>"
        + '<div class="muted" style="margin-bottom:16px">' + Mara.esc(text) + "</div>"
        + '<div class="btns"><button class="btn" data-no>Отмена</button>'
        + '<button class="btn ' + (danger ? "danger" : "") + '" data-yes>'
        + Mara.esc(okLabel || "Да") + "</button></div></div>";

      document.body.appendChild(bg);

      function close(value) { bg.remove(); resolve(value); }

      bg.querySelector("[data-no]").onclick = function () { close(false); };
      bg.querySelector("[data-yes]").onclick = function () { Mara.haptic("medium"); close(true); };
      bg.onclick = function (e) { if (e.target === bg) close(false); };
    });
  };

  // ---------- выбор группы ----------

  Mara.chatPicker = function (allowAll) {
    var chats = Mara.state.session.chats;
    if (!chats.length) return "";

    var options = allowAll === false ? [] : ['<option value="">Все группы</option>'];

    chats.forEach(function (c) {
      options.push('<option value="' + c.chat_id + '"'
        + (String(Mara.state.chat) === String(c.chat_id) ? " selected" : "")
        + ">" + Mara.esc(c.title) + "</option>");
    });

    return '<div class="chat-pick"><span>💬</span><select data-chat-pick>'
      + options.join("") + "</select></div>";
  };

  function bindChatPick() {
    var pick = app.querySelector("[data-chat-pick]");
    if (!pick) return;

    pick.onchange = function () {
      Mara.setChat(pick.value || null);
    };
  }

  Mara.setChat = function (chatId) {
    Mara.state.chat = chatId;
    Mara.state.cache = {};
    loadMe().then(Mara.render);
  };

  function loadMe() {
    return Mara.api("/api/admin/me" + Mara.chatQuery())
      .then(function (me) { Mara.state.me = me; })
      .catch(function () { Mara.state.me = { permissions: [], role: null }; });
  }

  // ---------- навигация ----------

  Mara.screen = function (name, render) { Mara.screens[name] = render; };

  Mara.open = function (name, arg) {
    Mara.state.stack.push({ name: name, arg: arg });
    Mara.render();
    window.scrollTo(0, 0);
  };

  Mara.back = function () {
    Mara.state.stack.pop();
    Mara.render();
  };

  Mara.backButton = function (label) {
    var arrow = Mara.icon ? Mara.icon("back", 18) : "←";
    return '<div class="back" data-back>' + arrow + " " + Mara.esc(label || "Назад") + "</div>";
  };

  Mara.loading = function () {
    app.innerHTML = '<div class="skel skel-h" style="width:55%;margin-top:4px"></div>'
      + '<div class="skel skel-sm"></div>'
      + '<div style="display:flex;gap:8px;margin:16px 0">'
      + '<div class="skel skel-metric"></div>'
      + '<div class="skel skel-metric"></div>'
      + '<div class="skel skel-metric"></div>'
      + '</div>'
      + '<div class="skel skel-card"></div>'
      + '<div class="skel skel-card"></div>'
      + '<div class="skel skel-card"></div>';
  };

  Mara.fail = function (error) {
    app.innerHTML = (Mara.state.stack.length ? Mara.backButton() : "")
      + '<div class="center"><div style="font-size:36px">😕</div>'
      + '<div style="margin-top:8px">' + Mara.esc((error && error.message) || "Не удалось загрузить") + "</div></div>";
    Mara.bind();
  };

  // Заголовки вложенных экранов: иконка в плашке, название, подпись —
  // как «Модерация / Защита и порядок» на макете. Одна таблица на все
  // экраны, чтобы шапки не расходились по стилю.
  Mara.HEADS = {
    settings: ["settings", "blue", "Настройки", "Параметры группы"],
    actions: ["zap", "gold", "Actions", "Система действий"],
    economy: ["diamond", "purple", "Экономика", "Алмазы, XP, карма, магазин"],
    diamonds: ["diamond", "purple", "Алмазы", "Балансы и операции"],
    levels: ["star", "gold", "XP и уровни", "Опыт и звания"],
    karma: ["heart", "red", "Карма", "Репутация участников"],
    achievements: ["trophy", "gold", "Достижения", "Условия, награды, статистика"],
    shop: ["bag", "pink", "Магазин", "Цены, наличие, покупки"],
    analytics: ["chart", "blue", "Аналитика", "Статистика и отчёты"],
    broadcasts: ["megaphone", "pink", "Рассылки", "Отправка сообщений"],
    journal: ["journal", "purple", "Журнал", "История событий"],
    roles: ["crown", "gold", "Администраторы", "Роли и права"],
    groups: ["group", "blue", "Группы", "Где работает Мара"],
    media: ["image", "green", "Медиа", "Коллекции картинок"],
    logs: ["file", "red", "Логи", "Только для владельца"],
    system: ["database", "blue", "Система", "Состояние бота"],
    notifications: ["bell", "red", "Уведомления", "Что требует внимания"],
    ai: ["flame", "purple", "Интенсивность и личность", "Как Мара общается"],
    memory: ["brain", "purple", "Память", "Что Мара помнит"],
    autoreplies: ["message", "blue", "Автоответы", "Ключевые слова и ответы"],
    images: ["image", "green", "Изображения", "Источники и подбор"],
    library: ["image", "green", "Моя коллекция", "Свои картинки для действий"],
    games: ["game", "green", "Игры", "Крокодил и мини-игры"],
    fishing: ["game", "blue", "Рыбалка", "Награды, лимиты, улов"],
    arena: ["game", "gold", "Арена", "Онлайн-дурак · только владелец"],
    owners: ["crown", "gold", "Главные админы", "Права как у создателя"],
    arena_players: ["users", "gold", "Игроки Арены", "Поиск, деньги, баны"],
    arena_player: ["user", "gold", "Игрок Арены", "Карточка и действия"],
    arena_live: ["game", "green", "Столы сейчас", "Ожидающие и идущие партии"],
    arena_moderation: ["shield", "red", "Модерация Арены", "Жалобы и подозрительные пары"],
    arena_tournaments: ["trophy", "gold", "Турниры", "Создать и отменить"],
    arena_seasons: ["calendar", "blue", "Сезоны", "Сезонный рейтинг"],
    arena_shop: ["bag", "pink", "Магазин Арены", "Цены и доступность"],
    arena_broadcast: ["megaphone", "blue", "Рассылка игрокам", "Личные сообщения от бота"],
    arena_settings: ["settings", "purple", "Правила экономики", "Бонусы, комиссия, цены"]
  };

  function addScreenHead() {
    var top = Mara.state.stack[Mara.state.stack.length - 1];
    var head = top && Mara.HEADS[top.name];

    if (!head || !Mara.tile || app.querySelector(".screen-head")) return;

    var el = document.createElement("div");
    el.className = "screen-head";
    el.innerHTML = Mara.tile(head[0], head[1], 22)
      + '<div class="grow"><h1>' + Mara.esc(head[2]) + '</h1><div class="sub">' + Mara.esc(head[3]) + "</div></div>";

    var back = app.querySelector("[data-back]");

    if (back && back.parentNode === app) back.insertAdjacentElement("afterend", el);
    else app.insertBefore(el, app.firstChild);
  }

  Mara.bind = function () {
    addScreenHead();
    bindChatPick();

    Array.prototype.forEach.call(app.querySelectorAll("[data-back]"), function (el) {
      el.onclick = Mara.back;
    });

    Array.prototype.forEach.call(app.querySelectorAll("[data-open]"), function (el) {
      el.onclick = function () {
        Mara.open(el.getAttribute("data-open"), el.getAttribute("data-arg"));
      };
    });

    Mara.loadImages();

    if (Mara.fillIcons) Mara.fillIcons(app);

    Array.prototype.forEach.call(app.querySelectorAll("[data-count]"), function (el) {
      var target = parseInt(el.getAttribute("data-count"), 10) || 0;
      if (!target) return;
      el.textContent = "0";
      var start = performance.now();
      var dur = Math.min(900, 350 + target * 0.25);
      requestAnimationFrame(function tick(now) {
        var t = Math.min(1, (now - start) / dur);
        var ease = 1 - Math.pow(1 - t, 3);
        el.textContent = Mara.num(Math.round(target * ease));
        if (t < 1) requestAnimationFrame(tick);
      });
    });
  };

  Mara.render = function () {
    var top = Mara.state.stack[Mara.state.stack.length - 1];
    var name = top ? top.name : Mara.state.tab;
    var screen = Mara.screens[name];

    if (!screen) { Mara.fail({ message: "Экран не найден" }); return; }

    Mara.loading();

    try { screen(top ? top.arg : null); }
    catch (error) { Mara.fail(error); }
  };

  var nav = document.getElementById("nav");

  Array.prototype.forEach.call(nav.querySelectorAll("button"), function (button) {
    button.onclick = function () {
      Mara.haptic();
      Mara.state.tab = button.getAttribute("data-tab");
      Mara.state.stack = [];

      Array.prototype.forEach.call(nav.querySelectorAll("button"), function (b) {
        b.classList.toggle("on", b === button);
      });

      Mara.render();
      window.scrollTo(0, 0);
    };
  });

  // ---------- отметка о новой версии ----------

  var SEEN = "mara_seen_version";

  Mara.seenVersion = function () {
    try { return parseInt(localStorage.getItem(SEEN) || "0", 10); } catch (e) { return 0; }
  };

  Mara.markSeen = function (v) {
    try { localStorage.setItem(SEEN, String(v)); } catch (e) {}
    Mara.refreshDots();
  };

  Mara.hasUpdate = function () {
    return Mara.state.session && Mara.state.session.version > Mara.seenVersion();
  };

  Mara.refreshDots = function () {
    var more = nav.querySelector('[data-tab="more"]');
    var dot = more.querySelector(".dot");

    if (Mara.hasUpdate() && !dot) {
      dot = document.createElement("span");
      dot.className = "dot";
      more.appendChild(dot);
    } else if (!Mara.hasUpdate() && dot) {
      dot.remove();
    }
  };

  // ---------- старт ----------

  Mara.api("/api/admin/session").then(function (session) {
    Mara.state.session = session;

    if (session.chats.length === 1) Mara.state.chat = session.chats[0].chat_id;

    nav.classList.remove("hidden");
    Mara.refreshDots();

    return loadMe();
  }).then(function () {
    Mara.render();
  }).catch(function () {
    app.innerHTML = '<div class="center"><div style="font-size:44px">🔒</div>'
      + "<h2>Нет доступа</h2>"
      + '<div class="muted">Панель открывается из Telegram и только для '
      + "администраторов групп, где работает Мара.</div></div>";
  });
})();
