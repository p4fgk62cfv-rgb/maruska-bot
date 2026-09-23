"""
Проверка веб-панели.

Появилась после того, как правка молча не применилась: у строк в
списке людей пропали метки для клика и фото, а проверка считала
метки в других местах и ничего не заметила. Здесь каждая важная
метка ищется там, где она должна быть, а не где-нибудь в файле.

Запуск:  python test_webapp.py
"""

import pathlib
import re
import shutil
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).parent

ADMIN_HTML = ROOT / "webapp" / "static" / "admin.html"
DRAW_HTML = ROOT / "webapp" / "static" / "draw.html"
ADMIN_PY = ROOT / "webapp" / "admin.py"
SERVER_PY = ROOT / "webapp" / "server.py"


def function_body(source: str, name: str) -> str:
    """
    Текст JS-функции по имени — до следующего объявления функции
    на том же уровне.
    """
    start = source.find(f"function {name}(")

    if start == -1:
        return ""

    rest = source[start + 1:]
    end = re.search(r"\n  function \w+\(", rest)

    return source[start: start + 1 + end.start()] if end else source[start:]


def main() -> int:
    failures = []
    checks = 0

    html = ADMIN_HTML.read_text(encoding="utf-8")
    script = re.findall(r"<script>(.*?)</script>", html, re.S)[-1]

    # 1. Синтаксис JavaScript обеих страниц
    node = shutil.which("node")

    for page in (ADMIN_HTML, DRAW_HTML):
        checks += 1

        if not node:
            print(f"   (node не найден, синтаксис {page.name} не проверен)")
            continue

        code = re.findall(
            r"<script>(.*?)</script>",
            page.read_text(encoding="utf-8"),
            re.S,
        )[-1]

        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tmp:
            tmp.write(code)

        result = subprocess.run(
            [node, "--check", tmp.name],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            failures.append(
                f"  [js] синтаксис {page.name}: {result.stderr.strip()[:200]}"
            )

    # 2. Метки стоят там, где должны
    placements = [
        ("renderUsers", "data-user=", "строки людей должны нажиматься"),
        ("renderUsers", "data-avatar=", "у людей должны грузиться фото"),
        ("renderUsers", "loadAvatars(", "список должен запускать загрузку фото"),
        ("renderGroups", "data-group=", "группы должны нажиматься"),
        ("renderGroups", "data-avatar=", "у групп должны грузиться фото"),
        ("renderUserCard", "data-mod=", "в карточке нужны кнопки модерации"),
        ("renderUserCard", "data-avatar=", "в карточке нужно фото"),
        ("renderGroupCard", "lockChat", "в карточке группы нужно закрытие чата"),
        ("renderMore", "OWNER_ONLY", "логи и система только владельцу"),
        ("renderChangelog", "markSeen(", "просмотр должен гасить отметку «новое»"),
        ("renderChangelog", "timeline", "обновления показываются лентой"),
    ]

    for function, marker, why in placements:
        checks += 1
        body = function_body(script, function)

        if not body:
            failures.append(f"  [экран] нет функции {function}")
        elif marker not in body:
            failures.append(f"  [экран] {function}: нет «{marker}» — {why}")

    # 3. Каждый адрес, который зовёт страница, существует на сервере
    routes_source = ADMIN_PY.read_text(encoding="utf-8") + SERVER_PY.read_text(
        encoding="utf-8"
    )

    registered = set(
        re.findall(r'add_(?:get|post)\("([^"]+)"', routes_source)
    )

    called = set(re.findall(r'"(/api/admin/[a-z_]+)', script))

    for path in sorted(called):
        checks += 1

        if path not in registered:
            failures.append(f"  [api] страница зовёт {path}, а на сервере его нет")

    # 4. Логи и система закрыты для не-владельцев и на сервере тоже
    admin_source = ADMIN_PY.read_text(encoding="utf-8")

    for handler in ("api_logs", "api_system"):
        checks += 1

        match = re.search(
            rf"async def {handler}\(.*?\n(.*?)(?=\nasync def |\ndef )",
            admin_source,
            re.S,
        )

        if not match or "require_owner" not in match.group(1):
            failures.append(
                f"  [права] {handler} должен требовать владельца на сервере"
            )

    # 5. Шапка показывает Мару, а не того, кто открыл панель
    checks += 1

    if "/api/admin/bot_photo" not in script:
        failures.append("  [шапка] рядом с «Мара» должна быть её аватарка")

    # 6. Журнал обновлений
    import sys

    sys.path.insert(0, str(ROOT))

    import changelog

    versions = [release.version for release in changelog.RELEASES]

    checks += 1
    if versions != sorted(versions, reverse=True):
        failures.append("  [обновления] версии должны идти от новой к старой")

    checks += 1
    if len(versions) != len(set(versions)):
        failures.append("  [обновления] повторяющиеся номера версий")

    dates = [release.date for release in changelog.RELEASES]

    checks += 1
    if dates != sorted(dates, reverse=True):
        failures.append("  [обновления] даты должны идти от новой к старой")

    for release in changelog.RELEASES:
        checks += 1

        if not release.items:
            failures.append(f"  [обновления] v{release.version} без пунктов")

        for kind, text in release.items:
            if kind not in changelog.KINDS:
                failures.append(
                    f"  [обновления] v{release.version}: неизвестный вид «{kind}»"
                )
            if not text.strip():
                failures.append(f"  [обновления] v{release.version}: пустой пункт")

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(
        f"✅ Все {checks} проверок прошли. "
        f"Эндпоинтов на сервере: {len(registered)}, "
        f"страница вызывает: {len(called)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
