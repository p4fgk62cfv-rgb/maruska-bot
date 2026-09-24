/*
 * Живой запуск панели в Node с имитацией браузера.
 * Грузит все модули в порядке из admin.html и вызывает каждый экран.
 * Ловит ошибки выполнения, которых не видно при разборе синтаксиса.
 * Запускается из test_webapp.py.
 */
const fs = require("fs"), vm = require("vm");
const dir = "webapp/static/admin/";
const shell = fs.readFileSync("webapp/static/admin.html", "utf8");
const order = [...shell.matchAll(/admin-assets\/(\w+\.js)/g)].map(m => m[1]);

function el() {
  return {
    innerHTML: "", value: "", style: {}, dataset: {}, children: [],
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    querySelector() { return el(); }, querySelectorAll() { return []; },
    appendChild(x) { return x; }, insertBefore(x) { return x; }, insertAdjacentElement() {},
    getAttribute() { return null; }, removeAttribute() {}, setAttribute() {}, remove() {},
    addEventListener() {}, set onclick(f) {}, focus() {}, setSelectionRange() {}
  };
}

const document = { getElementById: el, createElement: el, querySelector: el, querySelectorAll: () => [], body: el() };
const ctx = {
  window: {}, document, console, setTimeout, clearTimeout, Promise, JSON, Math, Date, parseInt, String, Array, Object, URL: { createObjectURL: () => "" },
  localStorage: { getItem: () => null, setItem() {} },
  fetch: () => new Promise(() => {}),   // запросы не завершаются — проверяем только загрузку
  FileReader: function () {}
};
ctx.window = ctx;
vm.createContext(ctx);

for (const file of order) {
  try { vm.runInContext(fs.readFileSync(dir + file, "utf8"), ctx, { filename: file }); }
  catch (e) { console.log("ОШИБКА при загрузке " + file + ": " + e.message); process.exit(1); }
}

const screens = Object.keys(ctx.Mara.screens).sort();
console.log("Загружено модулей:", order.length, "| экранов зарегистрировано:", screens.length);
console.log(screens.join(" "));

// Каждый экран вызывается — синхронная часть до запроса не должна падать
let bad = 0;
for (const name of screens) {
  try { ctx.Mara.state.session = { chats: [], user: { owner: true }, version: 1 }; ctx.Mara.state.me = { permissions: ["*"] }; ctx.Mara.screens[name]("x"); }
  catch (e) { bad++; console.log("  экран " + name + ": " + e.message); }
}
console.log(bad ? "Упало экранов: " + bad : "Все экраны запускаются без ошибок");
if (bad) process.exit(1);
