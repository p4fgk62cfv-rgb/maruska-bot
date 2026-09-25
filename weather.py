"""
Погода через Open-Meteo.

Ключ не нужен, лимитов для нормального использования нет,
данные бесплатны для некоммерческого применения.

Два запроса: геокодинг названия города и сам прогноз.
"""

import os
import re

import httpx


GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Прага")

REQUEST_TIMEOUT = 15


# Коды WMO -> эмодзи и описание
WEATHER_CODES = {
    0: ("☀️", "ясно"),
    1: ("🌤", "малооблачно"),
    2: ("⛅", "переменная облачность"),
    3: ("☁️", "пасмурно"),
    45: ("🌫", "туман"),
    48: ("🌫", "изморозь"),
    51: ("🌦", "морось"),
    53: ("🌦", "морось"),
    55: ("🌦", "сильная морось"),
    56: ("🌧", "ледяная морось"),
    57: ("🌧", "ледяная морось"),
    61: ("🌦", "небольшой дождь"),
    63: ("🌧", "дождь"),
    65: ("🌧", "сильный дождь"),
    66: ("🌧", "ледяной дождь"),
    67: ("🌧", "ледяной дождь"),
    71: ("🌨", "небольшой снег"),
    73: ("🌨", "снег"),
    75: ("❄️", "сильный снег"),
    77: ("🌨", "снежная крупа"),
    80: ("🌦", "ливень"),
    81: ("🌧", "ливень"),
    82: ("⛈", "сильный ливень"),
    85: ("🌨", "снегопад"),
    86: ("❄️", "сильный снегопад"),
    95: ("⛈", "гроза"),
    96: ("⛈", "гроза с градом"),
    99: ("⛈", "сильная гроза с градом"),
}


# Разбор фразы вида "Мара, погода Казань" / "какая погода в Праге сегодня"

WEATHER_RE = re.compile(r"погод\w*", re.IGNORECASE)

WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z\-]*")

# Предлоги перед городом — просто отбрасываем
PREPOSITIONS = {"в", "во", "на", "по", "у"}

# Слова, которые городом быть не могут: на них разбор останавливается
NOT_A_CITY = {
    "мара", "маруся", "маруська", "маня", "бот",
    "какая", "какой", "каково", "что", "как", "там", "тут", "здесь",
    "сегодня", "сейчас", "завтра", "послезавтра", "вчера",
    "утром", "днем", "днём", "вечером", "ночью",
    "будет", "была", "было", "есть", "скажи", "покажи", "глянь",
    "пожалуйста", "плиз", "пж", "а", "и", "но", "ну", "же",
    "нас", "вас", "меня", "тебя", "нам", "мне",
    "градус", "градусов", "тепло", "холодно", "дождь", "снег",
}

MAX_CITY_WORDS = 3


def mentions_weather(text: str | None) -> bool:
    return bool(text and WEATHER_RE.search(text))


def _clean_city(words: list[str]) -> str:
    result = []

    for word in words:
        lowered = word.lower()

        if lowered in PREPOSITIONS:
            if result:          # предлог уже после названия — конец
                break
            continue            # ведущий предлог просто пропускаем

        if lowered in NOT_A_CITY:
            if result:
                break
            continue

        result.append(word)

        if len(result) >= MAX_CITY_WORDS:
            break

    return " ".join(result).strip(" -")


def extract_city(text: str) -> str:
    """
    Город берётся из части фразы ПОСЛЕ слова "погода".
    Предлог необязателен: "погода Казань" работает так же,
    как "погода в Казани".

    Если после слова ничего осмысленного нет, пробуем то,
    что стояло перед ним.
    """
    match = WEATHER_RE.search(text or "")

    if not match:
        return DEFAULT_CITY

    after = _clean_city(WORD_RE.findall(text[match.end():]))

    if after:
        return after

    before = WORD_RE.findall(text[:match.start()])
    before = _clean_city(list(reversed(before)))

    if before:
        # разворачиваем обратно: "в Нижнем Новгороде" не должно стать
        # "Новгороде Нижнем"
        return " ".join(reversed(before.split()))

    return DEFAULT_CITY


def describe(code: int | None) -> tuple[str, str]:
    return WEATHER_CODES.get(code, ("🌡", "погода как погода"))


async def geocode(city: str) -> dict | None:
    params = {
        "name": city,
        "count": 1,
        "language": "ru",
        "format": "json",
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(GEOCODE_URL, params=params)
        response.raise_for_status()
        data = response.json()

    results = data.get("results") or []

    return results[0] if results else None


async def fetch_forecast(latitude: float, longitude: float) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,apparent_temperature,"
            "relative_humidity_2m,wind_speed_10m,weather_code"
        ),
        "daily": "temperature_2m_max,temperature_2m_min,weather_code",
        "timezone": "auto",
        "forecast_days": 2,
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(FORECAST_URL, params=params)
        response.raise_for_status()
        return response.json()


def _round(value) -> str:
    try:
        return f"{round(float(value)):+d}"
    except (TypeError, ValueError):
        return "?"


async def get_weather_text(city: str | None = None) -> str:
    target = (city or DEFAULT_CITY).strip()

    try:
        place = await geocode(target)
    except Exception as error:
        print("GEOCODE ERROR:", type(error).__name__, str(error))
        return "Не дотянулась до погодного сервиса 🌧"

    if place is None:
        return f"Не нашла город «{target}» 🤷‍♀️"

    try:
        data = await fetch_forecast(place["latitude"], place["longitude"])
    except Exception as error:
        print("FORECAST ERROR:", type(error).__name__, str(error))
        return "Не дотянулась до погодного сервиса 🌧"

    current = data.get("current", {}) or {}
    daily = data.get("daily", {}) or {}

    emoji, text = describe(current.get("weather_code"))

    name = place.get("name") or target
    country = place.get("country")
    where = f"{name}, {country}" if country else name

    temp = _round(current.get("temperature_2m"))
    feels = _round(current.get("apparent_temperature"))
    humidity = current.get("relative_humidity_2m")
    wind = current.get("wind_speed_10m")

    lines = [
        f"{emoji} <b>{where}</b> — {text}",
        f"🌡 Сейчас {temp}°, ощущается как {feels}°",
    ]

    if humidity is not None:
        lines.append(f"💧 Влажность {humidity}%")

    if wind is not None:
        lines.append(f"💨 Ветер {round(float(wind))} км/ч")

    highs = daily.get("temperature_2m_max") or []
    lows = daily.get("temperature_2m_min") or []
    codes = daily.get("weather_code") or []

    if len(highs) > 1 and len(lows) > 1:
        tomorrow_emoji, tomorrow_text = describe(
            codes[1] if len(codes) > 1 else None
        )
        lines.append(
            f"\n{tomorrow_emoji} Завтра: {_round(lows[1])}°…"
            f"{_round(highs[1])}°, {tomorrow_text}"
        )

    return "\n".join(lines)
