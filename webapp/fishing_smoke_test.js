/*
 * Проверка мини-приложения «Рыбалка» целиком: app.js + server.js
 * на поддельной странице и поддельном сервере.
 *
 * Сценарий: профиль → заброс → поклёвка → вываживание → поимка → магазин.
 * Проверяется, что улов и алмазы на экране — те, что прислал сервер, а
 * телефон ничего не начисляет сам.
 *
 * Запуск:  node webapp/fishing_smoke_test.js
 */
const fs = require("fs");
const vm = require("vm");

const dir = __dirname + "/static/fishing/";
const failures = [];
let checks = 0;

function expect(label, got, want) {
  checks++;
  if (got !== want) failures.push(`  ${label}: получили ${JSON.stringify(got)}, ждали ${JSON.stringify(want)}`);
}

// ---------- поддельная страница: элементы помнят текст, классы, стили ----------

const elements = {};

function makeEl(id) {
  const classes = new Set();
  const el = {
    id, textContent: "", innerHTML: "", src: "", value: "", dataset: {}, children: [], onclick: null,
    style: { setProperty() {} },
    classList: {
      add: (...c) => c.forEach((x) => classes.add(x)), remove: (...c) => c.forEach((x) => classes.delete(x)),
      toggle: (c, on) => (on === undefined ? (classes.has(c) ? classes.delete(c) : classes.add(c)) : on ? classes.add(c) : classes.delete(c)),
      contains: (c) => classes.has(c),
    },
    hasClass: (c) => classes.has(c),
    querySelector: () => makeEl("_q"), querySelectorAll: () => [],
    addEventListener() {}, animate() { return { onfinish: null, finished: Promise.resolve() }; },
    after() {}, before() {}, appendChild() {}, insertAdjacentHTML() {}, insertAdjacentElement() {}, remove() {},
    closest: () => null, setAttribute() {}, getAttribute: () => null,
  };
  return el;
}

function byId(id) {
  if (!elements[id]) elements[id] = makeEl(id);
  return elements[id];
}

const document = {
  getElementById: byId, createElement: () => makeEl("_new"), querySelector: () => makeEl("_q"),
  querySelectorAll: () => [], body: makeEl("body"), addEventListener() {},
};

// ---------- поддельный сервер ----------

const calls = [];
let profile = {
  diamonds: 500, level: 3, xp: 400, level_progress: 40, caught: 0, best: 0, legendary: 0, night: 0,
  species: {}, owned_rods: ["starter"], rod: "starter", rod_levels: { starter: 1 }, boat: "shore",
  owned_boats: ["shore"], bait_stock: { maggots: 5 }, bait: "worm", location: "quiet", streak: 0,
  last_day: "", quests: [{ id: "q_catch", title: "Первый улов", desc: "Поймай 5 рыб", target: 5, reward: 180, type: "catch", progress: 0, done: false }],
  chests: 0, opened_chests: 0, achievements: [], lifetime_weight: 0, fished_today: 0,
  settings: { reward_percent: 10, min_fight: 0, daily_cap: 800 },
};

function respond(path, body) {
  calls.push({ path, body });
  if (path === "/api/fishing/profile") return { ok: true, ...profile };
  if (path === "/api/fishing/cast") return { ok: true, cast_id: "c1", fish: "pike", power: 78, rarity: "Редкая", bite_delay: 0, bait: "worm" };
  if (path === "/api/fishing/land") {
    if (!body.success) return { ok: true, success: false };
    profile = { ...profile, diamonds: 532, caught: 1, species: { pike: 1 }, best: 4.2 };
    return { ok: true, success: true, fish: "pike", weight: 4.2, length: 60, trophy: false, reward: 32, xp: 11,
             capped: false, streak_bonus: 15, quests_done: [], achievements: [{ name: "Первая рыба", icon: "🐟" }],
             chest: false, level_up: null, profile };
  }
  if (path === "/api/fishing/buy") {
    if (body.kind === "rod" && body.key === "premium") return { ok: false, error: "🔒 Нужен 9 уровень" };
    profile = { ...profile, diamonds: profile.diamonds - 90, bait_stock: { maggots: 10 } };
    return { ok: true, profile };
  }
  return { ok: false, error: "unknown " + path };
}

function fetch(path, options = {}) {
  const body = options.body ? JSON.parse(options.body) : undefined;
  const data = respond(path, body);
  return Promise.resolve({ ok: data.ok !== false, status: data.ok === false ? 400 : 200, json: () => Promise.resolve(data) });
}

// ---------- окружение ----------

const timers = [];
const toasts = [];
const storage = {};

const ctx = {
  document, fetch, console,
  window: { Telegram: { WebApp: { initData: "signed", ready() {}, expand() {}, HapticFeedback: { impactOccurred() {}, notificationOccurred() {} } } } },
  localStorage: { getItem: (k) => storage[k] || null, setItem: (k, v) => { storage[k] = String(v); }, removeItem() {} },
  setTimeout: (fn, ms) => { timers.push(fn); return timers.length; }, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, navigator: {}, location: { origin: "https://x" }, Math, Date, JSON, Promise, Object, Array, Number, String,
};
ctx.window.location = ctx.location;
ctx.globalThis = ctx;
vm.createContext(ctx);

for (const file of ["app.js", "server.js"]) {
  vm.runInContext(fs.readFileSync(dir + file, "utf8"), ctx, { filename: file });
}

// toast из app.js пишет в элемент — перехватим, чтобы видеть сообщения
vm.runInContext("toast = function (t) { __toasts.push(t); };", Object.assign(ctx, { __toasts: toasts }));

const flush = () => new Promise((r) => setImmediate(r));
const runTimers = () => { while (timers.length) timers.shift()(); };
const run = (code) => vm.runInContext(code, ctx);

(async () => {
  await flush(); await flush(); runTimers(); await flush();

  // --- профиль ---
  expect("алмазы с сервера", run("state.diamonds"), 500);
  expect("уровень Мары", run("state.level"), 3);
  expect("прогресс уровня", run("levelProgress()"), 40);
  expect("награда задания в масштабе экономики", run("state.quests[0].reward"), 18);
  expect("награда достижения в масштабе", run("achievements[0].reward"), 10);
  expect("червь бесконечный", run("state.baitStock.worm"), 999);
  expect("на экране алмазы", byId("diamonds").textContent.replace(/\s/g, ""), "500");

  // --- заброс → поклёвка → подсечка ---
  run("cast()");
  await flush(); await flush();
  expect("заброс запрошен у сервера", calls.some((c) => c.path === "/api/fishing/cast"), true);
  runTimers(); await flush();
  expect("поклёвка", run("state.phase"), "bite");
  run("hook()");
  expect("на крючке рыба, выбранная сервером", run("state.fish"), "pike");

  // --- вываживание до победы ---
  let guard = 0;
  run("state.fishPower = 1; state.line = 10;");
  while (run("state.phase") === "fight" && guard++ < 50) { run("fight('reel')"); run("if (state.phase==='fight') { state.fishPower = 0.5; state.line = 10; }"); }
  for (let i = 0; i < 5; i++) { runTimers(); await flush(); await flush(); }

  expect("улов засчитан сервером", calls.some((c) => c.path === "/api/fishing/land" && c.body.success === true && c.body.cast_id === "c1"), true);
  expect("фаза «улов»", run("state.phase"), "catch");
  expect("вес с сервера", byId("catchWeight").textContent, "4.20 кг");
  expect("награда с сервера", byId("catchReward").textContent, "+32");
  expect("алмазы обновились с сервера", run("state.diamonds"), 532);
  expect("телефон не начислил сам", run("state.diamonds") === 532 + 32, false);
  expect("серия дней показана", toasts.some((t) => t.includes("+15")), true);
  expect("достижение показано", toasts.some((t) => t.includes("Первая рыба")), true);

  // --- магазин ---
  run("continueCast()");
  run("buyBait('maggots')"); await flush(); await flush();
  expect("покупка через сервер", calls.some((c) => c.path === "/api/fishing/buy" && c.body.kind === "bait"), true);
  expect("баланс после покупки — с сервера", run("state.diamonds"), 442);
  run("buyRod('premium')"); await flush(); await flush();
  expect("отказ сервера показан игроку", toasts.some((t) => t.includes("Нужен 9 уровень")), true);

  // --- тестовых алмазов больше нет ---
  run("showWallet()");
  expect("нет кнопки «+100 за тест»", byId("modalContent").innerHTML.includes("demoReward"), false);

  // --- награды не пишутся в localStorage ---
  run("save()");
  const saved = Object.entries(storage).filter(([k]) => k !== "maruskaFishingUi").map(([, v]) => v).join("");
  expect("алмазы не сохраняются на телефоне", /"diamonds":532/.test(saved), false);

  if (failures.length) {
    console.log(`❌ ${failures.length} проблем:\n`);
    console.log(failures.join("\n"));
    process.exit(1);
  }
  console.log(`✅ Все ${checks} проверок мини-приложения рыбалки прошли.`);
})().catch((e) => { console.log("❌ Падение:", e && e.stack || e); process.exit(1); });
