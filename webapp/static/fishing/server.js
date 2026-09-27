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
    if (p.catalog && p.catalog.boats) boats = p.catalog.boats.map(function (b) {
      var local = boats.find(function (x) { return x.id === b.key; }) || {};
      return Object.assign({}, local, { id: b.key, name: b.name, price: b.price, control: b.control, reward: b.reward, level: b.level });
    });
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
    setEnergy(p.energy);
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

    var e = energyNow();
    if (e && e.value < e.cost) {
      toast("⚡ Нет сил: нужно " + e.cost + ", есть " + e.value);
      showEnergy();
      return;
    }

    server.busy = true;

    api("/api/fishing/cast", {}).then(function (r) {
      server.castId = r.cast_id;
      server.castAt = Date.now();
      server.biteDelay = r.bite_delay;
      server.fish = r.fish;
      setEnergy(r.energy);

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
      var text = p.kind === "coins" ? "+" + p.amount + " 💎" : p.kind === "bait" ? "+" + p.amount + " " + p.name : p.kind === "energy" ? "+" + p.amount + " ⚡" : "+" + p.amount + " XP";
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

  // ---------- энергия: считает сервер, телефон только ведёт таймер ----------

  var energy = { enabled: false }, energyAt = 0;

  function setEnergy(e) {
    if (e) { energy = e; energyAt = Date.now(); }
    drawEnergy();
  }

  function energyNow() {
    if (!energy.enabled) return null;
    var t = (Date.now() - energyAt) / 1000, v = energy.value, next = 0;
    if (v < energy.max) {
      if (t >= energy.next_in) {
        v = Math.min(energy.max, v + 1 + Math.floor((t - energy.next_in) / energy.regen));
        next = v >= energy.max ? 0 : energy.regen - ((t - energy.next_in) % energy.regen);
      } else {
        next = energy.next_in - t;
      }
    }
    var cost = (energy.costs && energy.costs[LOC_KEYS[state.loc]]) || energy.cost;
    var full = v >= energy.max ? 0 : next + (energy.max - v - 1) * energy.regen;
    return { value: v, max: energy.max, next: Math.ceil(next), full: Math.ceil(full), cost: cost };
  }

  function clock(sec) {
    var m = Math.floor(sec / 60), s = sec % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  function longTime(sec) {
    var h = Math.floor(sec / 3600), m = Math.ceil((sec % 3600) / 60);
    if (m === 60) { h += 1; m = 0; }
    return (h ? h + " ч " : "") + (m || !h ? m + " мин" : "");
  }

  function drawEnergy() {
    var chip = document.getElementById("energyChip");
    if (!energy.enabled) { if (chip) chip.remove(); return; }
    if (!chip) {
      chip = document.createElement("button");
      chip.id = "energyChip";
      chip.className = "energy-chip";
      chip.onclick = showEnergy;
      document.getElementById("scene").appendChild(chip);
    }
    var e = energyNow(), pct = Math.min(100, Math.round(e.value * 100 / e.max));
    chip.classList.toggle("low", e.value < e.cost);
    chip.innerHTML = '<b>⚡ ' + e.value + "<small>/" + e.max + "</small></b>"
      + '<i><s style="width:' + pct + '%"></s></i>'
      + (e.value < e.max ? "<em>+1 через " + clock(e.next) + "</em>" : "<em>" + (e.value > e.max ? "сверх запаса" : "полная") + "</em>");

    var val = document.getElementById("enVal");
    if (val) {
      val.innerHTML = e.value + "<small>/" + e.max + "</small>";
      document.getElementById("enBar").style.width = pct + "%";
      document.getElementById("enNext").textContent = e.value < e.max
        ? "+1 через " + clock(e.next) + " · полная через " + longTime(e.full)
        : (e.value > e.max ? "Бодрость сверх запаса — восстановление начнётся ниже " + e.max : "Силы полные");
    }
  }

  setInterval(drawEnergy, 1000);

  function showEnergy() {
    if (!energy.enabled) return;
    var m = $("modal"), c = $("modalContent"), e = energyNow();
    var costs = locations.map(function (l, i) {
      var cost = energy.costs ? energy.costs[LOC_KEYS[i]] : energy.cost;
      return '<div class="energy-cost' + (i === state.loc ? " here" : "") + '"><span>' + l.name + "</span><b>−" + cost + " ⚡</b></div>";
    }).join("");
    var left = energy.refills_left, can = left > 0 && e.value < e.max;
    c.innerHTML = '<div class="level-hero energy-hero"><span>⚡ ЭНЕРГИЯ</span><b id="enVal"></b>'
      + '<div class="track"><i id="enBar"></i></div><small id="enNext"></small></div>'
      + "<h2>Силы рыбака</h2><p class=\"muted\">Каждый заброс тратит энергию, дальние водоёмы — больше. "
      + "Силы возвращаются сами: +1 каждые " + Math.round(energy.regen / 60) + " мин, даже когда игра закрыта. "
      + "С каждым уровнем запас больше.</p>"
      + '<div class="energy-costs">' + costs + "</div>"
      + '<button class="primary full" id="teaBtn"' + (can ? "" : " disabled") + ">☕ Термос чая +" + energy.refill_amount + " ⚡ · "
      + energy.refill_price.toLocaleString("ru-RU") + " 💎</button>"
      + '<p class="muted energy-note">' + (left > 0 ? "Сегодня осталось термосов: " + left : "Термос на сегодня выпит — завтра снова") + "</p>";
    m.classList.remove("hidden");
    drawEnergy();
    var tea = document.getElementById("teaBtn");
    if (tea && can) tea.onclick = buyEnergy;
  }

  function buyEnergy() {
    api("/api/fishing/buy", { kind: "energy", key: "" }).then(function (r) {
      apply(r.profile);
      toast("☕ +" + energy.refill_amount + " ⚡ — силы вернулись");
      showEnergy();
    }).catch(fail_toast);
  }

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
