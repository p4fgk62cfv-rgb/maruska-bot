"""
Подбор картинок для действий.

Коллекция хранится отдельно для каждого источника и каждой
комбинации пола: "pixabay/hug:male_female".

Пока в коллекции есть неиспользованные картинки — берём оттуда.
Кончились — дозапрашиваем следующую страницу у источника.
Источник больше ничего не отдаёт — сбрасываем цикл и идём по кругу.
"""

import hashlib
import logging
import random
from dataclasses import dataclass

from actions.catalog import Action, excluded_tags, required_tags
from actions.providers import (
    available_providers,
    download_photo,
    search_photos,
)
from database.repository import (
    count_cached_images,
    get_cached_action_image,
    known_photo_ids,
    reset_cached_images,
)


PAGES_PER_FILL = 2


# ---------------------------------------------------------
# Поисковые запросы для парных действий.
#
# Намеренно тёплые и позитивные: нейтральное
# "people supporting each other" сток отдаёт как
# депрессивную документалку.
#
# Короткие: Pixabay ищет по всем словам сразу, длинная фраза
# легко даёт ноль результатов.
# ---------------------------------------------------------

PAIR_SEARCHES = {
    "male_female": {
        "hug": "hugging couple happy",
        "kiss": "kissing couple",
        "highfive": "high five man woman",
        "handshake": "handshake man woman",
        "support": "smiling couple together",
        "congratulations": "celebration confetti couple",
        "party": "party couple celebration",
        "movie": "movie popcorn couple",
        "music": "music couple headphones",
        "dance": "dancing couple happy",
    },
    "male_male": {
        "hug": "hugging friends men",
        "kiss": "kissing couple",
        "highfive": "high five men",
        "handshake": "handshake men smiling",
        "support": "laughing friends men",
        "congratulations": "celebration confetti friends",
        "party": "party friends celebration",
        "movie": "movie popcorn friends",
        "music": "music friends headphones",
        "dance": "dancing friends happy",
    },
    "female_female": {
        "hug": "hugging friends women",
        "kiss": "kissing women couple",
        "highfive": "high five women",
        "handshake": "handshake women smiling",
        "support": "laughing friends women",
        "congratulations": "celebration confetti friends",
        "party": "party friends celebration",
        "movie": "movie popcorn friends",
        "music": "music friends headphones",
        "dance": "dancing women happy",
    },
    "neutral": {
        "hug": "hugging friends happy",
        "kiss": "kissing couple",
        "highfive": "high five friends",
        "handshake": "handshake smiling people",
        "support": "laughing friends together",
        "congratulations": "celebration confetti happy",
        "party": "party celebration friends fun",
        "movie": "movie popcorn cinema",
        "music": "music headphones happy",
        "dance": "dancing people happy",
    },
}


def get_search_query(action: Action, pair_key: str) -> str:
    if action.category == "pair":
        return PAIR_SEARCHES.get(pair_key, PAIR_SEARCHES["neutral"]).get(
            action.key,
            action.search,
        )
    return action.search


def query_variants(query: str) -> list[str]:
    """
    От точной фразы к широкой: "cold beer glass pub" -> "cold beer" -> "cold".
    Нужно, чтобы длинный запрос не давал пустую выдачу.
    """
    words = query.split()
    variants: list[str] = []

    for size in (len(words), 3, 2, 1):
        if size < 1 or size > len(words):
            continue
        variant = " ".join(words[:size])
        if variant not in variants:
            variants.append(variant)

    return variants


def rules_version(action: Action) -> str:
    """
    Отпечаток правил подбора: запрос + обязательные теги.

    Как только правила для действия меняются, ключ коллекции
    становится другим и картинки, набранные по старым правилам,
    просто перестают использоваться. Чистить базу руками не нужно.
    """
    payload = "|".join(
        (action.search,)
        + tuple(required_tags(action))
        + tuple(excluded_tags(action))
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return digest[:6]


def collection_key(provider: str, action: Action, pair_key: str) -> str:
    base = action.key

    if action.category == "pair":
        base = f"{action.key}:{pair_key}"

    return f"{provider}/{base}#{rules_version(action)}"



logger = logging.getLogger("maruska.images")

@dataclass
class Picked:
    """
    Что вернул подбор картинки.

    cached — уже лежит в Telegram, отправляем по file_id.
    fresh  — только что скачали, отправляем байтами и запоминаем
             полученный file_id.
    """
    kind: str
    collection: str
    provider: str = "pixabay"
    photo_id: str = ""
    file_id: str | None = None
    content: bytes | None = None
    image_id: int | None = None
    photographer_name: str | None = None
    photographer_url: str | None = None
    source_url: str | None = None


# Сколько страниц источника считаем доступными для случайного выбора
MAX_RANDOM_PAGE = 6

# Сколько картинок пробуем скачать, прежде чем сдаться
DOWNLOAD_ATTEMPTS = 3


async def fetch_fresh(
    provider: str,
    action: Action,
    collection: str,
    pair_key: str,
) -> Picked | None:
    """
    Ищет картинку в источнике и сразу скачивает её.

    Ссылки Pixabay живут около суток, поэтому между поиском и
    отправкой не должно проходить времени.
    """
    tags = required_tags(action)
    banned = excluded_tags(action)
    query = get_search_query(action, pair_key)

    seen = await known_photo_ids(collection)

    variants = query_variants(query)

    for tag in tags[:2]:
        if tag not in variants:
            variants.append(tag)

    for variant in variants:
        page = random.randint(1, MAX_RANDOM_PAGE)

        try:
            photos = await search_photos(
                provider,
                variant,
                page,
                required=tags,
                excluded=banned,
            )
        except Exception as error:
            logger.error("IMAGE %s SEARCH ERROR: %s %s", provider.upper(), type(error).__name__, error)
            continue

        if not photos:
            continue

        # Сначала то, чего ещё не показывали
        fresh_first = [p for p in photos if p.photo_id not in seen]
        candidates = fresh_first or photos

        random.shuffle(candidates)

        for photo in candidates[:DOWNLOAD_ATTEMPTS]:
            content = await download_photo(photo.image_url, photo.fallback_url)

            if not content:
                continue

            return Picked(
                kind="fresh",
                collection=collection,
                provider=photo.provider,
                photo_id=photo.photo_id,
                content=content,
                photographer_name=photo.photographer_name,
                photographer_url=photo.photographer_url,
                source_url=photo.source_url,
            )

    return None


async def get_image_for_action(
    action: Action,
    pair_key: str = "neutral",
) -> Picked | None:
    """
    Порядок такой:

    1. Берём из коллекции то, что уже загружено в Telegram —
       это мгновенно и не тратит запросы к источнику.
    2. Коллекция кончилась — идём в источник и качаем свежую.
    3. Источник молчит — прокручиваем коллекцию по кругу.
    """
    # Уже скачанные картинки — наша локальная библиотека. Они должны
    # продолжать работать даже если Pixabay/Unsplash выключены в панели.
    from actions.providers import KNOWN_PROVIDERS
    from database.repository import (
        count_cached_action_images_from_providers,
        get_cached_action_image_from_providers,
        reset_cached_action_images_from_providers,
    )

    local_collections = [
        collection_key(provider, action, pair_key)
        for provider in KNOWN_PROVIDERS
    ]

    cached = await get_cached_action_image_from_providers(local_collections)
    if cached is not None:
        return Picked(
            kind="cached",
            collection=cached.action,
            provider=cached.provider or "library",
            photo_id=cached.photo_id,
            file_id=cached.telegram_file_id,
            image_id=cached.id,
            photographer_name=cached.photographer_name,
            photographer_url=cached.photographer_url,
            source_url=cached.unsplash_url,
        )

    # Если локальный Telegram-кэш закончился, запускаем его по кругу.
    if await count_cached_action_images_from_providers(local_collections):
        await reset_cached_action_images_from_providers(local_collections)
        cached = await get_cached_action_image_from_providers(local_collections)
        if cached is not None:
            return Picked(
                kind="cached",
                collection=cached.action,
                provider=cached.provider or "library",
                photo_id=cached.photo_id,
                file_id=cached.telegram_file_id,
                image_id=cached.id,
                photographer_name=cached.photographer_name,
                photographer_url=cached.photographer_url,
                source_url=cached.unsplash_url,
            )

    providers = available_providers()

    if not providers:
        logger.info("IMAGE PROVIDERS: внешние источники выключены, работаем на локальной библиотеке")
        return None

    for provider in providers:
        collection = collection_key(provider, action, pair_key)

        cached = await get_cached_action_image(collection)

        if cached is not None:
            return Picked(
                kind="cached",
                collection=collection,
                provider=cached.provider or provider,
                photo_id=cached.photo_id,
                file_id=cached.telegram_file_id,
                image_id=cached.id,
                photographer_name=cached.photographer_name,
                photographer_url=cached.photographer_url,
                source_url=cached.unsplash_url,
            )

        picked = await fetch_fresh(provider, action, collection, pair_key)

        if picked is not None:
            return picked

        # Свежего нет — пускаем по кругу уже собранное
        if await count_cached_images(collection):
            await reset_cached_images(collection)

            cached = await get_cached_action_image(collection)

            if cached is not None:
                return Picked(
                    kind="cached",
                    collection=collection,
                    provider=cached.provider or provider,
                    photo_id=cached.photo_id,
                    file_id=cached.telegram_file_id,
                    image_id=cached.id,
                    photographer_name=cached.photographer_name,
                    photographer_url=cached.photographer_url,
                    source_url=cached.unsplash_url,
                )

    return None
