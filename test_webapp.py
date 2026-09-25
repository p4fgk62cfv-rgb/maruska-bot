"""
Проверка веб-панели (модульная версия).

Каждая важная метка ищется ВНУТРИ экрана, где она должна быть:
так ловятся правки, которые молча не применились.

Запуск:  python test_webapp.py
"""

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = pathlib.Path(__file__).parent
STATIC = ROOT / "webapp" / "static"
MODULES = sorted((STATIC / "admin").glob("*.js"))

# Порядок подключения: ядро → иконки → общие элементы → разделы
BASE_MODULES = ("core.js", "icons.js", "ui.js")
SECTION_MODULES = (
    "dashboard.js", "moderation.js", "users.js", "maruska.js", "actions.js",
    "games.js", "economy.js", "analytics.js", "broadcasts.js", "journal.js",
    "settings.js", "admins.js", "system.js",
)
STYLES = ("theme.css", "components.css", "mobile.css")


def screen_body(source: str, name: str) -> str:
    start = source.find(f'M.screen("{name}"')

    if start == -1:
        return ""

    rest = source[start + 10:]
    end = re.search(r'\n  M\.screen\("|\n  // =====', rest)

    return source[start: start + 10 + end.start()] if end else source[start:]


def python_function(source: str, name: str) -> str:
    match = re.search(rf"async def {name}\(.*?(?=\nasync def |\ndef |\Z)", source, re.S)
    return match.group(0) if match else ""


def main() -> int:
    failures, checks = [], 0
    node = shutil.which("node")

    # 1. Синтаксис всех скриптов
    scripts = [(p.name, p.read_text(encoding="utf-8")) for p in MODULES]
    draw = (STATIC / "draw.html").read_text(encoding="utf-8")
    scripts.append(("draw.html", re.findall(r"<script>(.*?)</script>", draw, re.S)[-1]))

    for name, code in scripts:
        checks += 1

        if not node:
            continue

        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tmp:
            tmp.write(code)

        result = subprocess.run([node, "--check", tmp.name], capture_output=True, text=True)

        if result.returncode:
            failures.append(f"  [js] {name}: {result.stderr.strip()[:200]}")

    js = "\n".join(p.read_text(encoding="utf-8") for p in MODULES)

    # 1б. Живой запуск: все модули грузятся, каждый экран вызывается
    if node:
        checks += 1

        result = subprocess.run(
            [node, str(ROOT / "webapp" / "smoke_test.js")],
            capture_output=True, text=True, cwd=str(ROOT),
        )

        if result.returncode:
            failures.append("  [запуск] " + (result.stdout + result.stderr).strip().replace("\n", "\n  ")[:600])

    # 2. Оболочка подключает все модули, и они существуют
    shell = (STATIC / "admin.html").read_text(encoding="utf-8")

    for module in STYLES + BASE_MODULES + SECTION_MODULES:
        checks += 1

        if f"/admin-assets/{module}" not in shell:
            failures.append(f"  [оболочка] admin.html не подключает {module}")

        if not (STATIC / "admin" / module).exists():
            failures.append(f"  [оболочка] нет файла webapp/static/admin/{module}")

    positions = [shell.find(f"/admin-assets/{m}") for m in BASE_MODULES]
    first_section = min(shell.find(f"/admin-assets/{m}") for m in SECTION_MODULES)

    checks += 1
    if positions != sorted(positions) or max(positions) > first_section:
        failures.append("  [оболочка] порядок: core.js → icons.js → ui.js → файлы разделов")

    # Лишние модули на диске, которые никто не подключает — мёртвый груз
    for path in MODULES:
        checks += 1
        if f"/admin-assets/{path.name}" not in shell:
            failures.append(f"  [оболочка] {path.name} лежит в папке, но не подключён — удалить или подключить")

    # 2б. Файл раздела не должен звать локальную функцию другого файла:
    # после разделения на модули это ReferenceError в момент клика
    def local_names(src):
        names = set(re.findall(r"^  function (\w+)\(", src, re.M))
        for line in re.findall(r"^  var (.+);$", src, re.M):
            names |= set(re.findall(r"(?:^|, )(\w+) =", line))
        for params in re.findall(r"function\s*\w*\s*\(([^)]*)\)", src):
            names |= {p.strip() for p in params.split(",") if p.strip()}
        names |= set(re.findall(r"\bvar (\w+)", src))
        return names

    sources = {p.name: p.read_text(encoding="utf-8") for p in MODULES}
    top_level = {
        name: set(re.findall(r"^  function (\w+)\(", src, re.M))
        | {n for line in re.findall(r"^  var (.+);$", src, re.M) for n in re.findall(r"(?:^|, )(\w+) =", line)}
        for name, src in sources.items()
    }
    everywhere = set().union(*top_level.values())

    for name, src in sources.items():
        code = re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", "''", src)
        code = re.sub(r"//.*", "", code)
        used = set(re.findall(r"(?<![\w.])([A-Za-z_]\w*)\b", code))

        for helper in sorted((used & everywhere) - local_names(src)):
            checks += 1
            owners = [m for m, d in top_level.items() if helper in d]
            failures.append(f"  [модули] {name} зовёт {helper}(), а она определена только в {owners}")

    # 3. Каждая вкладка навигации имеет экран
    for tab in re.findall(r'data-tab="(\w+)"', shell):
        checks += 1
        if f'M.screen("{tab}"' not in js:
            failures.append(f"  [навигация] вкладка «{tab}» без экрана")

    # 4. Каждый data-open ведёт на существующий экран
    for target in set(re.findall(r'data-open="(\w+)"', js)):
        checks += 1
        if f'M.screen("{target}"' not in js:
            failures.append(f"  [переход] data-open=\"{target}\" — экрана нет")

    for target in set(re.findall(r'row\("[^"]*", "[^"]*", "[^"]*", "(\w+)"', js)):
        checks += 1
        if f'M.screen("{target}"' not in js:
            failures.append(f"  [переход] row(…, \"{target}\") — экрана нет")

    # 5. Метки стоят в своих экранах
    placements = [
        ("users", 'data-open="profile"', "строки людей должны открывать профиль"),
        ("users", "M.avatar(", "у людей должны грузиться фото"),
        ("users", "data-filter=", "фильтры участников"),
        ("users", "data-sort", "сортировка участников"),
        ("users", "data-more", "догрузка списка"),
        ("profile", "data-vip", "отметка VIP"),
        ('profile', 'data-eco="karma"', "изменение кармы"),
        ("profile", "historyRow", "история событий человека"),
        ("profile", "achievements", "достижения в профиле"),
        ("profile", "data-mod=", "в профиле нужны кнопки модерации"),
        ("profile", "data-eco=", "в профиле нужно изменение баланса"),
        ("profile", "level-ring", "в профиле кольцо уровня как в макете"),
        ("home", "/api/admin/dashboard", "главная — командный центр"),
        ("home", "Требует внимания", "на главной блок «Требует внимания»"),
        ("moderation", "data-automod", "переключатель автомодерации"),
        ("moderation", "data-q=", "кнопки Мут/Бан/Предупр. в списке нарушителей"),
        ("moderation", "data-rule=", "конструктор «условие → действие»"),
        ("moderation", "canRestrict", "мут и бан скрыты без прав бота"),
        ("profile", "data-warn", "ручное предупреждение в профиле"),
        ("profile", 'data-mod="tempban"', "временный бан в профиле"),
        ("profile", "canRestrict", "мут и бан скрыты без прав бота"),
        ("group", "data-lock=", "закрытие чата в карточке группы"),
        ("groups", "chat_photo", "фото групп"),
        ("more", "r[4]", "логи и система скрыты от не-владельцев"),
        ("changelog", "markSeen(", "просмотр гасит отметку «новое»"),
        ("broadcasts", 'data-media="photo"', "рассылка с фото"),
        ("broadcasts", 'data-media="video"', "рассылка с видео"),
        ("broadcasts", 'data-media="animation"', "рассылка с GIF"),
        ("broadcasts", "data-badd", "несколько кнопок"),
        ("broadcasts", "data-bc-test", "тест себе"),
        ("broadcasts", 'data-tab-bc', "вкладки новое/запланированные/история"),
        ("analytics", "hourBars(", "активность по часам"),
        ("analytics", "delta(", "сравнение с прошлым периодом"),
        ("analytics", "returning", "возвращающиеся"),
        ("journal", "data-jwho", "фильтр по администратору"),
        ("journal", "data-juser", "фильтр «над кем»"),
        ("home", "sys(\"База данных\"", "реальный статус базы на главной"),
        ("home", "data-quick=", "быстрые действия с человеком"),
        ("home", 'M.metric("star", num(t.xp)', "выданный XP за сегодня"),
        ("action", "data-hide-alias", "скрыть встроенное слово"),
        ("action", "data-hide-phrase", "скрыть встроенную фразу"),
        ("action", "data-replace", "заменить свою картинку"),
        ("images", "data-up", "порядок источников"),
        ("group", "data-save-title", "переименование группы"),
        ("moderation", "canDelete", "предупреждение без права удаления"),
        ("moderation", "bindCustomRules(res[2])", "свои правила подключены после загрузки"),
        ("moderation", "customRules(", "блок своих правил на экране"),
        ("broadcasts", 'data-mode="dm"', "рассылка в личку"),
        ("library", "data-open=\"library_tag\"", "список коллекций открывает коллекцию"),
        ("library", "Что догрузить", "подсказка, каким действиям не хватает картинок"),
        ("library", "data-new-col", "создание категории в панели"),
        ("library_tag", "data-link", "привязка коллекции к действию"),
        ("library_tag", "data-del-img", "удаление фото из коллекции"),
        ("library_tag", "data-lib-more", "большие коллекции — постранично"),
        ("library_tag", "actionCard(", "коллекция как своё действие"),
        ("broadcasts", "/api/admin/broadcasts/audience", "подсчёт получателей до отправки"),
        ("search", "d.groups", "поиск по группам"),
        ("search", "d.events", "поиск по событиям"),
        ("journal", "data-jfrom", "фильтр по дате"),
        ("economy", '"diamonds")', "раздел алмазов"),
        ("economy", '"levels")', "раздел XP и уровней"),
        ("economy", '"karma")', "раздел кармы"),
        ("diamonds", "massForm(", "массовая корректировка алмазов"),
        ("shop", "data-price", "редактирование цены"),
        ("shop", "data-stock", "склад товара"),
        ("shop", "data-enabled", "снять с продажи"),
        ("broadcasts", "data-bc-when", "рассылка по расписанию"),
        ("analytics", "heat", "тепловая карта"),
        ("actions", "action_image", "картинки действий"),
        ("action", 'data-add="alias"', "добавление слова-триггера"),
        ("action", 'data-add="phrase"', "добавление фразы"),
        ("action", "data-img-file", "загрузка своей картинки"),
        ("action", "data-hide=", "скрытие картинки из коллекции"),
        ("action", "data-cooldown", "cooldown действия"),
        ("action", "data-test", "кнопка «Протестировать»"),
        ("action", "esc(p.male)", "превью фразы экранируется"),
        ("roles", "/api/admin/roles", "экран ролей"),
        ("mara", '"autoreplies")', "автоответы в хабе Маруськи"),
        ("mara", '"memory")', "память в хабе Маруськи"),
        ("mara", '"games")', "игры в хабе Маруськи"),
        ("ai", "MODE_HINTS", "режимы интенсивности"),
        ("ai", '"persona"', "выбор личности"),
        ("memory", "data-clear", "очистка памяти"),
        ("memory", "data-except", "исключения памяти"),
        ("autoreplies", "data-f-prob", "вероятность автоответа"),
        ("autoreplies", "data-f-cd", "пауза автоответа"),
        ("images", "data-cat-toggle", "вкл/выкл категории целиком"),
        ("games", "game_crocodile", "переключатель крокодила"),
        ("games", "game_dice", "переключатель мини-игр"),
    ]

    for screen, marker, why in placements:
        checks += 1
        body = screen_body(js, screen)

        if not body:
            failures.append(f"  [экран] нет экрана «{screen}»")
        elif marker not in body:
            failures.append(f"  [экран] {screen}: нет «{marker}» — {why}")

    checks += 1
    if "confirm_strict: true" not in (STATIC / "admin" / "moderation.js").read_text(encoding="utf-8"):
        failures.append("  [опасно] бан за первое нарушение должен требовать подтверждения (confirm_strict)")

    checks += 1
    if "/api/admin/bot_photo" not in js:
        failures.append("  [шапка] рядом с «Мара» должна быть её аватарка")

    # 6. Все вызываемые адреса существуют на сервере
    server = "".join(
        (ROOT / "webapp" / f).read_text(encoding="utf-8")
        for f in ("admin.py", "admin_v2.py", "server.py")
    )
    registered = set(re.findall(r'add_(?:get|post)\("([^"]+)"', server))

    for path in sorted(set(re.findall(r'"(/api/admin/[a-z_/]+)', js))):
        checks += 1
        if path not in registered:
            failures.append(f"  [api] панель зовёт {path}, а на сервере его нет")

    # 7. Права на сервере
    admin_py = (ROOT / "webapp" / "admin.py").read_text(encoding="utf-8")
    admin_v2 = (ROOT / "webapp" / "admin_v2.py").read_text(encoding="utf-8")

    for handler in ("api_logs", "api_system"):
        checks += 1
        if "require_owner" not in python_function(admin_py, handler):
            failures.append(f"  [права] {handler} должен требовать владельца")

    for source, handler in ((admin_py, "api_user"), (admin_py, "api_user_action"),
                            (admin_py, "api_moderate"), (admin_v2, "api_undo")):
        checks += 1
        if "await ensure_target_access(" not in python_function(source, handler):
            failures.append(f"  [права] {handler} не проверяет, чей это человек")

    for handler, perm in (("api_action_toggle", "content"), ("api_roles", "roles"),
                          ("api_clear_warnings", "moderation"), ("api_broadcasts", "broadcast")):
        checks += 1
        if f'"{perm}"' not in python_function(admin_v2, handler):
            failures.append(f"  [права] {handler} должен требовать право «{perm}»")

    # 7а. Запрос нельзя «заготовить» в переменную: fetch уходит в момент
    # вызова M.post, и подтверждение опасного действия стало бы фикцией.
    # Так чуть не случилось с баном из быстрых действий.
    for path in MODULES:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if re.search(r"\b\w+\s*=\s*M\.post\(", line):
                checks += 1
                failures.append(
                    f"  [опасно] {path.name}:{number} запрос сохранён в переменную — "
                    "он уже отправлен; оберни в функцию и вызывай после подтверждения"
                )
    checks += 1

    # 7б. Каждый жест разложен по теме, у каждой категории есть название
    from actions.catalog import ACTIONS

    themes_src = admin_v2[admin_v2.index("PAIR_THEMES = {"):admin_v2.index("THEME_BY_KEY =")]
    theme_ns = {}
    exec(themes_src, theme_ns)
    themed = [k for keys in theme_ns["PAIR_THEMES"].values() for k in keys]

    for action in ACTIONS:
        if action.category == "pair":
            checks += 1
            if themed.count(action.key) != 1:
                failures.append(f"  [темы] жест {action.key!r} должен быть ровно в одной теме PAIR_THEMES")

    ui_src = (STATIC / "admin" / "ui.js").read_text(encoding="utf-8")
    titles = set(re.findall(r"(\w+): \"", ui_src[ui_src.index("M.CATEGORY_TITLES"):ui_src.index("M.THEME_ORDER")]))

    for category in {a.category for a in ACTIONS} | set(theme_ns["PAIR_THEMES"]) | {"humor"}:
        checks += 1
        if category not in titles:
            failures.append(f"  [темы] нет русского названия для категории {category!r} в M.CATEGORY_TITLES")

    # 8. Журнал обновлений
    sys.path.insert(0, str(ROOT))
    import changelog

    versions = [r.version for r in changelog.RELEASES]
    dates = [r.date for r in changelog.RELEASES]

    checks += 3
    if versions != sorted(versions, reverse=True):
        failures.append("  [обновления] версии должны идти от новой к старой")
    if len(versions) != len(set(versions)):
        failures.append("  [обновления] повторяющиеся номера версий")
    if dates != sorted(dates, reverse=True):
        failures.append("  [обновления] даты должны идти от новой к старой")

    for release in changelog.RELEASES:
        checks += 1
        if not release.items:
            failures.append(f"  [обновления] v{release.version} без пунктов")
        for kind, text in release.items:
            if kind not in changelog.KINDS or not text.strip():
                failures.append(f"  [обновления] v{release.version}: плохой пункт")

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок прошли. Модулей: {len(MODULES)}, эндпоинтов: {len(registered)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
