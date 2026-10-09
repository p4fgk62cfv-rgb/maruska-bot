"""
Радио: /радио (или /radio) присылает меню — страна → станция → «Слушать».
Плеер — страница /radio мини-приложения: в личке кнопка web_app,
в группе обычная ссылка (кнопки web_app Telegram в группах не даёт).

Звук идёт прямо с серверов радиостанций, бот его не пропускает через себя.
"""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

router = Router(name="radio")

COUNTRIES = {
    "ru": {"flag": "🇷🇺", "name": "Россия", "title": "Радио России"},
    "ua": {"flag": "🇺🇦", "name": "Украина", "title": "Радіо України"},
}

# id, страна, название, жанр, эмодзи, адреса потоков (плеер берёт следующий, если первый молчит).
# Все адреса — https: страница плеера открыта по https, обычный http браузер не пустит.
STATIONS: list[dict] = [
    # ── Россия ──
    {"id": "europa", "country": "ru", "name": "Европа Плюс", "genre": "Поп-хиты", "emoji": "🌍",
     "streams": ["https://ep256.hostingradio.ru:8052/europaplus256.mp3", "https://europaplus.hostingradio.ru:8014/europaplus320.mp3"]},
    {"id": "rusradio", "country": "ru", "name": "Русское Радио", "genre": "Русские хиты", "emoji": "🎤",
     "streams": ["https://rusradio.hostingradio.ru/rusradio96.aacp"]},
    {"id": "retro", "country": "ru", "name": "Ретро FM", "genre": "Хиты 70–90-х", "emoji": "📼",
     "streams": ["https://retro.hostingradio.ru:8043/retro256.mp3"]},
    {"id": "avto", "country": "ru", "name": "Авторадио", "genre": "Дискотека 80–90-х", "emoji": "🚗",
     "streams": ["https://gpm.hostingradio.ru/gpm-avtoradio495.aacp"]},
    {"id": "hitfm", "country": "ru", "name": "Хит FM", "genre": "Поп", "emoji": "🔥",
     "streams": ["https://hitfm.hostingradio.ru/hitfm96.aacp"]},
    {"id": "energy", "country": "ru", "name": "Радио Energy", "genre": "Танцевальная", "emoji": "⚡",
     "streams": ["https://gpm.hostingradio.ru/gpm-energyfm495.aacp"]},
    {"id": "dfm", "country": "ru", "name": "DFM", "genre": "Dance", "emoji": "💃",
     "streams": ["https://dfm.hostingradio.ru/dfm96.aacp"]},
    {"id": "record", "country": "ru", "name": "Радио Рекорд", "genre": "Электроника", "emoji": "🎧",
     "streams": ["https://radiorecord.hostingradio.ru/rr_main96.aacp"]},
    {"id": "record_rus", "country": "ru", "name": "Рекорд: Русские хиты", "genre": "Русский дэнс", "emoji": "🪩",
     "streams": ["https://radiorecord.hostingradio.ru/russianhits96.aacp"]},
    {"id": "superdisco", "country": "ru", "name": "Супердискотека 90-х", "genre": "Хиты 90-х", "emoji": "🕺",
     "streams": ["https://radiorecord.hostingradio.ru/sd9096.aacp"]},
    {"id": "nashe", "country": "ru", "name": "Наше Радио", "genre": "Русский рок", "emoji": "🎸",
     "streams": ["https://nashe1.hostingradio.ru/nashe-128.mp3"]},
    {"id": "maximum", "country": "ru", "name": "Maximum", "genre": "Рок и альтернатива", "emoji": "🤘",
     "streams": ["https://maximum.hostingradio.ru/maximum96.aacp"]},
    {"id": "dorognoe", "country": "ru", "name": "Дорожное радио", "genre": "Песни в дорогу", "emoji": "🛣️",
     "streams": ["https://dorognoe.hostingradio.ru/dorognoe"]},
    {"id": "chanson", "country": "ru", "name": "Радио Шансон", "genre": "Шансон", "emoji": "🎻",
     "streams": ["https://chanson.hostingradio.ru:8041/chanson256.mp3"]},
    {"id": "relax", "country": "ru", "name": "Relax FM", "genre": "Спокойная музыка", "emoji": "🌙",
     "streams": ["https://gpm.hostingradio.ru/gpm-relaxfm495.aacp"]},
    {"id": "monte", "country": "ru", "name": "Монте-Карло", "genre": "Lounge", "emoji": "🍸",
     "streams": ["https://montecarlo.hostingradio.ru/montecarlo96.aacp"]},
    {"id": "jazz", "country": "ru", "name": "Радио JAZZ", "genre": "Джаз", "emoji": "🎷",
     "streams": ["https://nashe1.hostingradio.ru/jazz-128.mp3"]},
    {"id": "humor", "country": "ru", "name": "Юмор FM", "genre": "Юмор и хиты", "emoji": "😂",
     "streams": ["https://gpm.hostingradio.ru/gpm-humorfm495.aacp"]},
    {"id": "comedy", "country": "ru", "name": "Comedy Radio", "genre": "Юмор", "emoji": "🤣",
     "streams": ["https://gpm.hostingradio.ru/gpm-comedyradio495.aacp"]},
    {"id": "vesti", "country": "ru", "name": "Вести FM", "genre": "Новости", "emoji": "📰",
     "streams": ["https://icecast-vgtrk.cdnvideo.ru/vestifm_mp3_192kbps"]},
    {"id": "mayak", "country": "ru", "name": "Маяк", "genre": "Разговорное", "emoji": "🗼",
     "streams": ["https://icecast-vgtrk.cdnvideo.ru/mayakfm_mp3_192kbps"]},
    # ── Украина ──
    {"id": "ua_hitfm", "country": "ua", "name": "Хіт FM", "genre": "Поп-хіти", "emoji": "🔥",
     "streams": ["https://online.hitfm.ua/HitFM"]},
    {"id": "ua_hitfm_ukr", "country": "ua", "name": "Хіт FM: Українські хіти", "genre": "Українська музика", "emoji": "💙",
     "streams": ["https://online.hitfm.ua/HitFM_Ukr"]},
    {"id": "ua_kiss", "country": "ua", "name": "Kiss FM", "genre": "Танцювальна", "emoji": "💋",
     "streams": ["https://online.kissfm.ua/KissFM"]},
    {"id": "ua_kiss_deep", "country": "ua", "name": "Kiss FM Deep", "genre": "Deep house", "emoji": "🌊",
     "streams": ["https://online.kissfm.ua/KissFM_Deep"]},
    {"id": "ua_roks", "country": "ua", "name": "Radio ROKS", "genre": "Рок", "emoji": "🎸",
     "streams": ["https://online.radioroks.ua/RadioROKS"]},
    {"id": "ua_roks_ukr", "country": "ua", "name": "ROKS Українською", "genre": "Український рок", "emoji": "🤘",
     "streams": ["https://online.radioroks.ua/RadioROKS_Ukr"]},
    {"id": "ua_lux", "country": "ua", "name": "Lux FM", "genre": "Поп", "emoji": "✨",
     "streams": ["https://lux.radio.tvstitch.com/kyiv/lux_adv_sd"]},
    {"id": "ua_melodia", "country": "ua", "name": "Мелодія FM", "genre": "Ліричні хіти", "emoji": "🎼",
     "streams": ["https://online.melodiafm.ua/MelodiaFM"]},
    {"id": "ua_relax", "country": "ua", "name": "Radio Relax", "genre": "Спокійна музика", "emoji": "🌙",
     "streams": ["https://online.radiorelax.ua/RadioRelax"]},
    {"id": "ua_nashe", "country": "ua", "name": "Наше Радіо", "genre": "Хіти", "emoji": "🎤",
     "streams": ["https://online.nasheradio.ua/NasheRadio"]},
    {"id": "ua_avto", "country": "ua", "name": "Авторадіо", "genre": "Хіти в дорогу", "emoji": "🚗",
     "streams": ["https://cast.mediaonline.net.ua/avtoradio"]},
    {"id": "ua_perec", "country": "ua", "name": "Перець FM", "genre": "Розважальне", "emoji": "🌶️",
     "streams": ["https://radio.perec.fm/radio-stilnoe"]},
    {"id": "ua_jazz", "country": "ua", "name": "Radio Jazz", "genre": "Джаз", "emoji": "🎷",
     "streams": ["https://online.radiojazz.ua/RadioJazz"]},
    {"id": "ua_bayraktar", "country": "ua", "name": "Radio Bayraktar", "genre": "Українська музика", "emoji": "🎶",
     "streams": ["https://online.radiobayraktar.ua/RadioBayraktar"]},
    {"id": "ua_ur1", "country": "ua", "name": "Українське радіо", "genre": "Новини та розмови", "emoji": "📻",
     "streams": ["https://radio.ukr.radio/ur1-mp3"]},
    {"id": "ua_promin", "country": "ua", "name": "Радіо Промінь", "genre": "Музика", "emoji": "☀️",
     "streams": ["https://radio.ukr.radio/ur2-mp3"]},
    {"id": "ua_kultura", "country": "ua", "name": "Радіо Культура", "genre": "Культура", "emoji": "🎭",
     "streams": ["https://radio.ukr.radio/ur3-mp3"]},
]

BY_ID = {s["id"]: s for s in STATIONS}


def stations_of(country: str) -> list[dict]:
    return [s for s in STATIONS if s["country"] == country]


def public_stations() -> list[dict]:
    """Список для плеера."""
    return [
        {**{k: s[k] for k in ("id", "country", "name", "genre", "emoji", "streams")},
         "flag": COUNTRIES[s["country"]]["flag"]}
        for s in STATIONS
    ]


# ── меню в чате ──

def plural_stations(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} станция"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} станции"
    return f"{n} станций"


def countries_menu() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "📻 <b>Радио Маруськи</b>\n\n"
        "Живой эфир любимых станций прямо в Telegram.\n"
        "Выберите страну 👇"
    )
    rows = [
        [InlineKeyboardButton(text=f"{c['flag']} {c['name']} · {plural_stations(len(stations_of(code)))}", callback_data=f"radio:c:{code}")]
        for code, c in COUNTRIES.items()
    ]
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def stations_menu(country: str) -> tuple[str, InlineKeyboardMarkup]:
    c = COUNTRIES[country]
    text = f"{c['flag']} <b>{c['title']}</b>\n\nВыберите станцию 👇"
    buttons = [InlineKeyboardButton(text=f"{s['emoji']} {s['name']}", callback_data=f"radio:s:{s['id']}") for s in stations_of(country)]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text="‹ Страны", callback_data="radio:home")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def player_url(station_id: str) -> str | None:
    from webapp.server import public_url

    base = public_url()
    return f"{base}/radio?s={station_id}" if base else None


def station_card(station: dict, private: bool) -> tuple[str, InlineKeyboardMarkup]:
    c = COUNTRIES[station["country"]]
    text = (
        f"{station['emoji']} <b>{escape(station['name'])}</b>\n"
        f"{c['flag']} {c['name']} · {escape(station['genre'])}\n\n"
        "🎧 Нажмите «Слушать» — откроется плеер с живым эфиром. "
        "Там же можно переключать станции."
    )
    url = player_url(station["id"])
    rows = []
    if url:
        listen = (
            InlineKeyboardButton(text="▶️ Слушать", web_app=WebAppInfo(url=url))
            if private
            else InlineKeyboardButton(text="▶️ Слушать", url=url)
        )
        rows.append([listen])
    else:
        text += "\n\n⚠️ Плеер пока недоступен: у бота не настроен публичный адрес."
    rows.append([
        InlineKeyboardButton(text="‹ Станции", callback_data=f"radio:c:{station['country']}"),
        InlineKeyboardButton(text="🌍 Страны", callback_data="radio:home"),
    ])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def is_radio_command(message: Message) -> bool:
    """«/радио» — Telegram не считает кириллицу командой, ловим текстом (и «/радио@бот»)."""
    text = (message.text or "").strip().lower()
    head = text.split(maxsplit=1)[0] if text else ""
    return head == "/радио" or head.startswith("/радио@")


@router.message(Command("radio"))
@router.message(is_radio_command)
async def radio_command(message: Message):
    text, markup = countries_menu()
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("radio:"))
async def radio_navigate(callback: CallbackQuery):
    parts = (callback.data or "").split(":")
    private = callback.message is not None and callback.message.chat.type == "private"
    if parts[1] == "home":
        text, markup = countries_menu()
    elif parts[1] == "c" and len(parts) > 2 and parts[2] in COUNTRIES:
        text, markup = stations_menu(parts[2])
    elif parts[1] == "s" and len(parts) > 2 and parts[2] in BY_ID:
        text, markup = station_card(BY_ID[parts[2]], private)
    else:
        await callback.answer("Это меню устарело — наберите /радио ещё раз")
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        # Сообщение не изменилось (двойное нажатие) или слишком старое.
        pass
    await callback.answer()
