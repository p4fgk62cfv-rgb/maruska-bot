"""
Проверка автомодерации: ссылки и домены, стоп-слова с вариантами
написания и исключениями, спам символами, флуд, повторы.
Запуск:  python test_automod.py
"""

import pathlib
import re
from collections import deque
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).parent

source = (ROOT / "features" / "automod.py").read_text(encoding="utf-8")
start = source.index("LINK_RE = re.compile(")
end = source.index("# =========================================================\n# Состояние в памяти")

ns = {"re": re, "deque": deque, "urlparse": urlparse}
exec(source[start:end], ns)

has_link = ns["has_link"]
extract_domains = ns["extract_domains"]
link_verdict = ns["link_verdict"]
parse_list = ns["parse_list"]
normalize = ns["normalize"]
find_stop_word = ns["find_stop_word"]
is_symbol_spam = ns["is_symbol_spam"]
is_flood = ns["is_flood"]
is_repeat = ns["is_repeat"]


def main() -> int:
    failures, checks = [], 0

    def expect(label, got, want):
        nonlocal checks
        checks += 1
        if got != want:
            failures.append(f"  {label}: получили {got!r}, ждали {want!r}")

    # --- ссылки ---
    for text in ("зайди на https://spam.ru", "www.casino.com", "t.me/joinchat/abc",
                 "пиши @super_money_bot", "дешево на shop.xyz", "сайт example.com"):
        expect(f"ссылка «{text}»", has_link(text), True)

    for text in ("привет всем", "Мара, пиво", "в 10.30 встречаемся",
                 "@stanislav привет", "сколько стоит 5.99"):
        expect(f"не ссылка «{text}»", has_link(text), False)

    expect("домен из ссылки", extract_domains("глянь https://www.Spam.ru/x?y=1"), ["spam.ru"])
    expect("t.me и бот", extract_domains("t.me/abc и @money_maker_bot"), ["t.me", "t.me"])
    expect("telegram.me = t.me", extract_domains("telegram.me/x"), ["t.me"])

    white, black = ["youtube.com", "t.me"], ["bit.ly"]

    expect("чёрный список всегда", link_verdict("https://bit.ly/x", "allow", False, white, black), True)
    expect("белый список всегда можно", link_verdict("https://youtube.com/w", "everyone", True, white, black), False)
    expect("поддомен белого", link_verdict("https://m.youtube.com/w", "everyone", True, white, black), False)
    expect("поддомен чёрного", link_verdict("https://a.bit.ly/w", "allow", False, white, black), True)
    expect("всем нельзя", link_verdict("https://site.ru", "everyone", False, white, black), True)
    expect("новичкам нельзя — новичок", link_verdict("https://site.ru", "newbies", True, white, black), True)
    expect("новичкам нельзя — старожил", link_verdict("https://site.ru", "newbies", False, white, black), False)
    expect("можно всем", link_verdict("https://site.ru", "allow", True, white, black), False)
    expect("смесь белого и чужого", link_verdict("youtube.com и site.ru", "everyone", False, white, black), True)

    # --- стоп-слова ---
    words = parse_list("казино, ставки на спорт,\nзаработок; x")
    expect("разбор списка", words, ["казино", "ставки на спорт", "заработок"])

    expect("обычное", find_stop_word("Лучшее КАЗИНО тут", words), "казино")
    expect("фраза", find_stop_word("делаю ставки на спорт", words), "ставки на спорт")
    expect("окончание", find_stop_word("казиношка", words), "казино")
    expect("не внутри слова", find_stop_word("заработок", ["работ"]), None)
    expect("латиница", find_stop_word("лучшее kaзинo", words), "казино")
    expect("цифры вместо букв", find_stop_word("к@зин0 онлайн", words), "казино")
    expect("через точки", find_stop_word("к.а.з.и.н.о", words), "казино")
    expect("через пробелы", find_stop_word("к а з и н о", words), "казино")
    expect("растянутые буквы", find_stop_word("казииииино", words), "казино")
    expect("исключение", find_stop_word("смотрел казино рояль", words, ["казино рояль"]), None)
    expect("исключение не спасает другое", find_stop_word("казино рояль и казино", words, ["казино рояль"]), "казино")
    expect("чистый текст", find_stop_word("идём пить пиво", words), None)
    expect("обычные слова не склеиваются", normalize("я и ты"), "я и ты")

    # --- спам символами ---
    expect("восклицания", is_symbol_spam("!!!!!!!!!!!!!!!!!!!!"), True)
    expect("растянутая буква", is_symbol_spam("аааааааааааааааааааа"), True)
    expect("стена эмодзи", is_symbol_spam("😂" * 25), True)
    expect("мусор из символов", is_symbol_spam("$#@%^&*()_+=-[]{}|;:,.<>?/~`$#@%^&*()_+"), True)
    expect("нормальный текст", is_symbol_spam("Привет! Как дела? Идём вечером гулять?"), False)
    expect("пара эмодзи", is_symbol_spam("ахаха 😂😂😂"), False)

    # --- флуд и повторы ---
    expect("флуд", is_flood(deque([0, 0.5, 1, 1.5, 2, 2.5, 3]), 3, 6, 10), True)
    expect("не флуд", is_flood(deque([0, 10, 20, 30, 40, 50, 60]), 60, 6, 10), False)
    expect("граница флуда", is_flood(deque([0, 1, 2, 3, 4, 5]), 5, 6, 10), False)
    expect("повтор", is_repeat(deque(["купи слона"] * 3), "Купи  слона"), True)
    expect("мало повторов", is_repeat(deque(["а тут", "а тут"]), "а тут"), False)
    expect("короткое не считается", is_repeat(deque(["ок"] * 3), "ок"), False)

    if failures:
        print(f"❌ {len(failures)} проблем:\n")
        print("\n".join(failures))
        return 1

    print(f"✅ Все {checks} проверок автомодерации прошли.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
