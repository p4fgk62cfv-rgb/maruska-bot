"""
Радио: меню строится, данные кнопок влезают в 64 байта, станции уникальны,
все потоки по https (иначе плеер в Telegram их не сыграет).
Запуск:  python test_radio.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from features import radio  # noqa: E402

errors = []


def check(ok, what):
    if not ok:
        errors.append(what)


ids = [s["id"] for s in radio.STATIONS]
check(len(ids) == len(set(ids)), "id станций повторяются")
for s in radio.STATIONS:
    check(s["country"] in radio.COUNTRIES, f"{s['id']}: неизвестная страна")
    check(bool(s["streams"]), f"{s['id']}: нет потоков")
    for url in s["streams"]:
        check(url.startswith("https://"), f"{s['id']}: поток не https: {url}")

markups = [radio.countries_menu()[1]]
for code in radio.COUNTRIES:
    check(len(radio.stations_of(code)) > 0, f"{code}: нет станций")
    markups.append(radio.stations_menu(code)[1])
radio.player_url = lambda sid: f"https://example.org/radio?s={sid}"
for s in radio.STATIONS:
    for private in (True, False):
        text, markup = radio.station_card(s, private)
        markups.append(markup)
        listen = markup.inline_keyboard[0][0]
        check((listen.web_app is not None) == private, f"{s['id']}: кнопка «Слушать» не того вида")
for markup in markups:
    for row in markup.inline_keyboard:
        for b in row:
            if b.callback_data:
                check(len(b.callback_data.encode()) <= 64, f"длинные данные кнопки: {b.callback_data}")
                check(b.callback_data.startswith("radio:"), f"чужие данные кнопки: {b.callback_data}")

check(radio.plural_stations(21) == "21 станция", "21 станция")
check(radio.plural_stations(17) == "17 станций", "17 станций")
check(radio.plural_stations(3) == "3 станции", "3 станции")


class Msg:
    def __init__(self, text):
        self.text = text


for t, want in [("/радио", True), ("/Радио@maruska_bot", True), ("/радио украина", True), ("/радиола", False), ("радио", False), (None, False)]:
    check(radio.is_radio_command(Msg(t)) == want, f"is_radio_command({t!r})")

check(len(radio.public_stations()) == len(radio.STATIONS), "public_stations")

if errors:
    print("❌ " + "\n❌ ".join(errors))
    sys.exit(1)
print(f"✅ Радио: {len(radio.STATIONS)} станций, все проверки прошли.")
