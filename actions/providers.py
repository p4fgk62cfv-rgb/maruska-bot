"""
Источники картинок для действий.

Pixabay — основной:
  - атрибуция не требуется, подписи под фото нет;
  - лимит 100 запросов за 60 секунд на ключ;
  - постоянный хотлинк запрещён, поэтому картинку скачиваем
    и заливаем в Telegram байтами. После первой отправки
    живём на telegram_file_id и к Pixabay больше не ходим.

Unsplash — необязательный запасной источник. Включается только
если явно перечислен в IMAGE_PROVIDERS. Его лицензия ТРЕБУЕТ
атрибуцию, поэтому у таких картинок подпись остаётся.
"""

import os
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx


APP_NAME = "maruska_telegram_bot"

# Порядок источников: "pixabay" или "pixabay,unsplash"
IMAGE_PROVIDERS = [
    name.strip().lower()
    for name in os.getenv("IMAGE_PROVIDERS", "pixabay").split(",")
    if name.strip()
]

PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
PIXABAY_API_URL = "https://pixabay.com/api/"

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
UNSPLASH_API_URL = "https://api.unsplash.com/search/photos"

PER_PAGE = 50
REQUEST_TIMEOUT = 20

# Без User-Agent Pixabay отвечает 400 на скачивание
DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MaruskaBot/1.0; "
        "+https://t.me/BotMaruska_bot)"
    ),
    "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*",
}

# Telegram принимает фото до 10 МБ, но лучше держаться ниже.
MAX_PHOTO_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class RemotePhoto:
    provider: str
    photo_id: str
    image_url: str
    tags: str = ""
    fallback_url: str | None = None
    photographer_name: str | None = None
    photographer_url: str | None = None
    source_url: str | None = None


def _with_utm(url: str) -> str:
    separator = "&" if "?" in url else "?"
    return url + separator + urlencode({
        "utm_source": APP_NAME,
        "utm_medium": "referral",
    })


# ---------------------------------------------------------
# Pixabay
# ---------------------------------------------------------

def matches_tags(
    tags: str,
    required: tuple[str, ...],
    excluded: tuple[str, ...] = (),
) -> bool:
    """
    Картинка подходит, если хотя бы один обязательный фрагмент
    есть в её тегах. Теги приходят от источника; привязка идёт
    к самому действию, а не к первому слову запроса — иначе по
    "couple kissing" засчитывается свадебный пейзаж без поцелуя.
    """
    haystack = tags.lower()

    if any(fragment.lower() in haystack for fragment in excluded):
        return False

    if not required:
        return True

    return any(fragment.lower() in haystack for fragment in required)


async def search_pixabay(
    query: str,
    page: int,
    required: tuple[str, ...] = (),
    excluded: tuple[str, ...] = (),
) -> list[RemotePhoto]:
    if not PIXABAY_API_KEY:
        raise RuntimeError("PIXABAY_API_KEY is not set")

    params = {
        "key": PIXABAY_API_KEY,
        "q": query,
        "image_type": "photo",
        "orientation": "horizontal",
        "safesearch": "true",
        "order": "popular",
        "per_page": PER_PAGE,
        "page": page,
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(PIXABAY_API_URL, params=params)
        response.raise_for_status()
        data = response.json()

    photos = []

    for hit in data.get("hits", []):
        photo_id = hit.get("id")
        large = hit.get("largeImageURL")
        web = hit.get("webformatURL")
        tags = hit.get("tags") or ""

        if not photo_id or not (large or web):
            continue

        if not matches_tags(tags, required, excluded):
            continue

        photos.append(
            RemotePhoto(
                provider="pixabay",
                photo_id=str(photo_id),
                image_url=large or web,
                tags=tags,
                fallback_url=web,
            )
        )

    return photos


# ---------------------------------------------------------
# Unsplash (запасной, с обязательной атрибуцией)
# ---------------------------------------------------------

async def search_unsplash(
    query: str,
    page: int,
    required: tuple[str, ...] = (),
    excluded: tuple[str, ...] = (),
) -> list[RemotePhoto]:
    if not UNSPLASH_ACCESS_KEY:
        raise RuntimeError("UNSPLASH_ACCESS_KEY is not set")

    params = {
        "query": query,
        "page": page,
        "per_page": 30,
        "orientation": "landscape",
        "content_filter": "high",
    }

    headers = {
        "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}",
        "Accept-Version": "v1",
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.get(
            UNSPLASH_API_URL,
            params=params,
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

    photos = []

    for item in data.get("results", []):
        photo_id = item.get("id")
        image_url = item.get("urls", {}).get("regular")
        page_url = item.get("links", {}).get("html")

        if not photo_id or not image_url or not page_url:
            continue

        tags = " ".join(
            tag.get("title", "")
            for tag in (item.get("tags") or [])
            if isinstance(tag, dict)
        )

        description = " ".join(
            filter(None, (
                item.get("description"),
                item.get("alt_description"),
            ))
        )

        haystack = f"{tags} {description}".strip()

        if haystack and not matches_tags(haystack, required, excluded):
            continue

        user = item.get("user", {}) or {}
        username = user.get("username")

        photographer_url = (
            _with_utm(f"https://unsplash.com/@{username}")
            if username
            else _with_utm("https://unsplash.com/")
        )

        photos.append(
            RemotePhoto(
                provider="unsplash",
                photo_id=photo_id,
                image_url=image_url,
                tags=haystack,
                photographer_name=(
                    user.get("name")
                    or username
                    or "Unsplash photographer"
                ),
                photographer_url=photographer_url,
                source_url=_with_utm(page_url),
            )
        )

    return photos


SEARCH_FUNCTIONS = {
    "pixabay": search_pixabay,
    "unsplash": search_unsplash,
}


KNOWN_PROVIDERS = ("pixabay", "unsplash")

# Порядок из панели владельца. None — берём из IMAGE_PROVIDERS.
_order_override: list[str] | None = None


def set_provider_order(order: list[str] | None) -> None:
    """
    Задаёт порядок внешних провайдеров.

    Пустой список — это валидная настройка: внешние провайдеры
    выключены, а бот продолжает работать на своей библиотеке/Telegram-кэше.
    None означает «настройка не задана — использовать IMAGE_PROVIDERS».
    """
    global _order_override

    if order is None:
        _order_override = None
        return

    clean = [name for name in order if name in KNOWN_PROVIDERS]
    _order_override = list(dict.fromkeys(clean))


def provider_order() -> list[str]:
    """Порядок опроса внешних источников."""
    return IMAGE_PROVIDERS if _order_override is None else list(_order_override)


def available_providers() -> list[str]:
    ready = []

    for name in provider_order():
        if name == "pixabay" and PIXABAY_API_KEY:
            ready.append(name)
        elif name == "unsplash" and UNSPLASH_ACCESS_KEY:
            ready.append(name)

    return ready


async def search_photos(
    provider: str,
    query: str,
    page: int,
    required: tuple[str, ...] = (),
    excluded: tuple[str, ...] = (),
) -> list[RemotePhoto]:
    search = SEARCH_FUNCTIONS.get(provider)

    if search is None:
        return []

    return await search(query, page, required, excluded)


# ---------------------------------------------------------
# Скачивание
# ---------------------------------------------------------

async def download_photo(
    url: str,
    fallback_url: str | None = None,
) -> bytes | None:
    """
    Скачивает картинку.

    ВАЖНО: ссылки Pixabay подписаны и живут около суток. Хранить их
    в базе и использовать позже нельзя — придёт 400. Поэтому
    скачивание происходит сразу после поиска, а в базу кладётся
    уже telegram_file_id, который не протухает.
    """
    urls = [url]

    if fallback_url and fallback_url != url:
        urls.append(fallback_url)

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
        headers=DOWNLOAD_HEADERS,
    ) as client:

        for candidate in urls:
            try:
                response = await client.get(candidate)
                response.raise_for_status()
            except Exception as error:
                print(
                    "PHOTO DOWNLOAD ERROR:",
                    type(error).__name__,
                    str(error),
                )
                continue

            content_type = response.headers.get("content-type", "")

            if not content_type.startswith("image/"):
                continue

            content = response.content

            if not content:
                continue

            if len(content) > MAX_PHOTO_BYTES:
                # Слишком тяжёлая — пробуем версию поменьше.
                continue

            return content

    return None
