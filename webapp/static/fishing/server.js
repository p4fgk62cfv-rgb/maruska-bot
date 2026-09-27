/*
 * Рыбалка ↔ сервер Мары.
 *
 * Подключается ПОСЛЕ app.js и перехватывает только логику: заброс,
 * поимку, обрыв, покупки, сундук, выбор места и наживки, кошелёк.
 * Визуал, анимации и панели — из app.js без изменений.
 *
 * Сервер главный: рыбу, вес, трофей, алмазы и опыт решает он.
 * Алмазы и уровень — общие с Марой. Локально награды больше не
 * сохраняются, «+100 💎 за тест» больше нет.
 */
(function () {
  "use strict";

  var LOC_KEYS = locations.map(function (l) { return l.id; });
  var BAIT_KEYS = ["worm", "maggots", "corn", "bread", "livebait", "fly", "wobbler", "spinner", "softbait"];
  var BASE_ACH = achievements.map(function (a) { return a.reward; });

  var server = { castId: null, castAt: 0, biteDelay: 0, fish: null, settings: { reward_percent: 10, min_fight: 2 }, busy: false };

  // ---------- запросы ----------

  function api(path, body) {
    var headers = { "X-Telegram-Init-Data": fishingInitData() };
    var options = { headers: headers };

    if (body !== undefined) {
      options.method = "POST";
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }

    return fetch(path, options).then(function (r) {
      if (r.status === 401) throw new Error("Открой рыбалку через Telegram");
      if (r.status === 429) throw new Error("Не так быстро 🙂");
      return r.json().catch(function () { return { ok: false, error: "Ошибка сервера (" + r.status + ")" }; })
        .then(function (data) {
          if (!r.ok || data.ok === false) throw new Error(data.error || "Ошибка сервера");
          return data;
        });
    });
  }

  function scaled(value) {
    return Math.round(value * (server.settings.reward_percent || 0) / 100);
  }

  // ---------- профиль с сервера → состояние игры ----------

  function apply(p) {
    if (!p) return;

    server.settings = p.settings || server.settings;

    state.diamonds = p.diamonds;
    state.level = p.level;
    state.xp = p.xp;
    state._levelPct = p.level_progress;
    state.caught = p.caught;
    state.best = p.best;
    state.legendary = p.legendary;
    state.nightCatches = p.night;
    state.inventory = p.species || {};
    state.owned = p.owned_rods;
    state.rod = p.rod;
    state.rodLevels = p.rod_levels;
    state.reel = p.reel;
    state.ownedReels = p.owned_reels;
    state.bobber = p.bobber;
    state.ownedBobbers = p.owned_bobbers;
    if (p.catalog) tackle = p.catalog;
    state.boat = p.boat;
    state.ownedBoats = p.owned_boats;
    // Червь бесплатный и бесконечный
    state.baitStock = Object.assign({}, p.bait_stock, { worm: 999 });
    state.bait = Math.max(0, BAIT_KEYS.indexOf(p.bait));
    state.loc = Math.max(0, LOC_KEYS.indexOf(p.location));
    state.streak = p.streak;
    state.lastFishDay = p.last_day;
    state.quests = (p.quests || []).map(function (q) { return Object.assign({}, q, { reward: scaled(q.reward) }); });
    state.questsDay = new Date().toISOString().slice(0, 10);
    state.chests = p.chests;
    state.openedChests = p.opened_chests;
    state.unlockedAchievements = p.achievements || [];
    state.lifetimeWeight = p.lifetime_weight;
    state.fishedToday = p.fished_today;

    // Награды за достижения — в масштабе экономики Мары
    achievements.forEach(function (a, i) { a.reward = scaled(BASE_ACH[i]); });

    render();
    var cc = document.getElementById("chestCount");
    if (cc) cc.textContent = state.chests;
  }

  function refresh() {
    return api("/api/fishing/profile").then(apply);
  }

  function fail_toast(error) { toast("⚠️ " + error.message); }

  // ---------- локальное сохранение: только оформление ----------

  var lastSelection = null;

  save = function () {
    // Наживку выбирают в панели снаряжения: app.js меняет state.bait и зовёт save()
    var bait = BAIT_KEYS[state.bait] || "worm";
    if (lastSelection !== null && bait !== lastSelection) {
      api("/api/fishing/select", { bait: bait }).then(function (r) { apply(r.profile); }).catch(fail_toast);
    }
    lastSelection = bait;
    try { localStorage.setItem("maruskaFishingUi", JSON.stringify({ weatherIndex: state.weatherIndex })); } catch (e) {}
  };
  v4save = function () {};
  addXP = function () {};
  checkAchievements = function () {};
  updateStreak = function () {};
  maybeChest = function () {};
  updateQuests = function () {};
  ensureDailyQuests = function () {};
  consumeBait = function () { return true; };
  grantBait = function () {};

  // События с бонусами считались на телефоне — теперь награды считает сервер
  rollEvent = function () {};
  currentEvent = function () { return null; };

  if (window.FishingBackend) window.FishingBackend.save = function () { return Promise.resolve({ ok: true }); };
  if (window.FishingSecure) window.FishingSecure.save = function () { return Promise.resolve({ ok: true }); };

  levelProgress = function () { return state._levelPct || 0; };

  // ---------- заброс: рыбу выбирает сервер ----------

  cast = function () {
    if (state.phase !== "idle" || server.busy) return;
    server.busy = true;

    api("/api/fishing/cast", {}).then(function (r) {
      server.castId = r.cast_id;
      server.castAt = Date.now();
      server.biteDelay = r.bite_delay;
      server.fish = r.fish;

      var stock = state.baitStock || {};
      if (r.bait !== "worm" && stock[r.bait]) stock[r.bait] -= 1;

      __v3Cast();
    }).catch(fail_toast).then(function () { server.busy = false; });
  };

  chooseFish = function () { return server.fish || "perch"; };

  // Бонусы v4 (лодка, задания, сундук) начислял телефон — теперь сервер
  fight = function (type) { __v3Fight(type); };

  // ---------- поимка ----------

  function landLater(success) {
    // Сервер не засчитает рыбу раньше, чем её реально можно вытащить
    var ready = (server.biteDelay + (server.settings.min_fight || 0)) * 1000 + 300;
    var wait = Math.max(0, ready - (Date.now() - server.castAt));
    var castId = server.castId;
    server.castId = null;

    return new Promise(function (resolve) { setTimeout(resolve, wait); })
      .then(function () { return api("/api/fishing/land", { cast_id: castId, success: success }); });
  }

  catchFish = function () {
    scene.classList.remove("is-casting", "is-fighting");
    state.phase = "landing";
    $("fightCard").classList.add("hidden");
    $("statusPill").textContent = "🎣 Вытаскиваю...";

    landLater(true).then(function (r) {
      var f = fish[r.fish];
      state.phase = "catch";
      FX.reset();
      $("catchImage").src = AS + (r.trophy && f.trophy ? f.trophy : f.img);
      $("catchName").textContent = f.name;
      $("catchRarity").textContent = r.trophy ? "👑 ТРОФЕЙНЫЙ • " + f.rarity : f.rarity;
      $("catchWeight").textContent = Number(r.weight).toFixed(2) + " кг";
      $("catchLength").textContent = r.length + " см";
      $("catchReward").textContent = "+" + r.reward;
      $("catchCard").classList.remove("hidden");
      $("statusPill").textContent = r.trophy ? "👑 ТРОФЕЙНЫЙ УЛОВ!" : "🎉 Рыба поймана!";

      try { window.Telegram.WebApp.HapticFeedback.notificationOccurred("success"); } catch (e) {}

      var notes = [];
      if (r.capped) notes.push("💎 Дневной лимит алмазов с рыбалки исчерпан");
      if (r.streak_bonus) notes.push("🔥 Серия " + (r.profile && r.profile.streak) + " дн. • +" + r.streak_bonus + " 💎");
      (r.quests_done || []).forEach(function (q) { notes.push("✅ " + q.title + " • +" + q.reward + " 💎"); });
      (r.achievements || []).forEach(function (a) { notes.push(a.icon + " " + a.name); });
      if (r.chest) notes.push("🎁 Ты нашёл сундук рыбака!");
      if (r.level_up) notes.push("⭐ Новый уровень: " + r.level_up);

      notes.forEach(function (text, i) { setTimeout(function () { toast(text); }, 900 + i * 1600); });

      apply(r.profile);
    }).catch(function (error) {
      state.phase = "idle";
      FX.reset();
      $("castBtn").classList.remove("hidden");
      $("statusPill").textContent = "Готов к забросу";
      fail_toast(error);
    });
  };

  var originalFail = fail;
  fail = function () {
    originalFail();
    if (server.castId) {
      var castId = server.castId;
      server.castId = null;
      api("/api/fishing/land", { cast_id: castId, success: false }).catch(function () {});
    }
  };

  // ---------- магазин и снаряжение ----------

  function shop(kind, key, done) {
    return api("/api/fishing/buy", { kind: kind, key: key || "" }).then(function (r) {
      apply(r.profile);
      if (done) toast(done);
      openPanel("gear");
    }).catch(fail_toast);
  }

  buyRod = function (id) { shop("rod", id, "🎣 Удочка готова"); };
  upgradeRod = function () { shop("upgrade", "", "⬆️ Удочка улучшена"); };
  buyReel = function (id) { shop("reel", id, "🎣 Катушка готова"); };
  buyBobber = function (id) { shop("bobber", id, "🎈 Поплавок готов"); };
  buyBait = function (id) { shop("bait", id, "🪱 +5 наживки"); };
  buyBoat = function (id) {
    api("/api/fishing/buy", { kind: "boat", key: id }).then(function (r) {
      apply(r.profile);
      toast("🛶 Лодка готова");
      if (typeof showBoats === "function") showBoats();
    }).catch(fail_toast);
  };

  openChest = function () {
    api("/api/fishing/chest", {}).then(function (r) {
      var p = r.prize;
      var text = p.kind === "coins" ? "+" + p.amount + " 💎" : p.kind === "bait" ? "+" + p.amount + " " + p.name : "+" + p.amount + " XP";
      apply(r.profile);
      toast("🎁 Сундук открыт: " + text);
    }).catch(fail_toast);
  };

  setLocation = function (i) {
    if (state.phase !== "idle") { toast("Сначала закончи текущую рыбалку"); return; }
    var index = (i + locations.length) % locations.length;
    api("/api/fishing/select", { location: LOC_KEYS[index] }).then(function (r) { apply(r.profile); }).catch(fail_toast);
  };

  // ---------- кошелёк и уровень: общие с Марой ----------

  showWallet = function () {
    var m = $("modal"), c = $("modalContent");
    var cap = server.settings.daily_cap;
    c.innerHTML = '<div class="wallet-big">💎<b>' + state.diamonds.toLocaleString("ru-RU") + "</b></div>"
      + "<h2>Кошелёк</h2><p class=\"muted\">Алмазы общие с Маруськой: трать их в магазине бота и здесь.</p>"
      + (cap ? "<p class=\"muted\">С рыбалки сегодня: " + (state.fishedToday || 0) + " из " + cap + " 💎</p>" : "");
    m.classList.remove("hidden");
  };

  showProgress = function () {
    var m = $("modal"), c = $("modalContent");
    c.innerHTML = '<div class="level-hero"><span>⭐ УРОВЕНЬ</span><b>' + state.level + '</b><div class="track"><i style="width:'
      + (state._levelPct || 0) + '%"></i></div><small>' + (state._levelPct || 0) + "% до следующего</small></div>"
      + "<h2>Прогресс</h2><p class=\"muted\">Уровень общий с Маруськой: опыт за рыбу идёт в твой профиль. "
      + "Уровень открывает водоёмы, удочки и лодки.</p>";
    m.classList.remove("hidden");
  };

  // ---------- старт ----------

  function bind() {
    $("castBtn").onclick = cast;
    $("hookBtn").onclick = hook;
    $("continueBtn").onclick = continueCast;
    $("pullBtn").onclick = function () { fight("pull"); };
    $("relaxBtn").onclick = function () { fight("relax"); };
    $("reelBtn").onclick = function () { fight("reel"); };
    $("walletBtn").onclick = showWallet;
    var chest = document.getElementById("chestBtn");
    if (chest) chest.onclick = openChest;
  }

  bind();
  $("statusPill").textContent = "Загружаю профиль…";

  refresh().then(function () {
    lastSelection = BAIT_KEYS[state.bait] || "worm";
    $("statusPill").textContent = "Готов к забросу";
  }).catch(function (error) {
    $("statusPill").textContent = "⚠️ " + error.message;
    $("castBtn").classList.add("hidden");
  });
})();
