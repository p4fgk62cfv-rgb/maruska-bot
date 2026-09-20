"""
Подбор картинок для действий.

Коллекция хранится отдельно для каждого источника и каждой
комбинации пола: "pixabay/hug:male_female".

Пока в коллекции есть неиспользованные картинки — берём оттуда.
Кончились — дозапрашиваем следующую страницу у источника.
Источник больше ничего не отдаёт — сбрасываем цикл и идём по кругу.
"""

import hashlib

from actions.catalog import Action, excluded_tags, required_tags
from actions.providers import (
    available_providers,
    search_photos,
)
from database.repository import (
    get_unused_action_image,
    get_last_action_page,
    add_action_image,
    reset_action_images,
    count_action_images,
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
        (action.search,) + tuple(action.tags) + tuple(action.exclude)
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()
    return digest[:6]


def collection_key(provider: str, action: Action, pair_key: str) -> str:
    base = action.key

    if action.category == "pair":
        base = f"{action.key}:{pair_key}"

    return f"{provider}/{base}#{rules_version(action)}"


async def fill_collection(
    provider: str,
    action: Action,
    key: str,
    pair_key: str,
) -> int:
    """
    Фильтр по тегам НЕ отключается ни при каких условиях.

    Раньше при пустой строгой выдаче включался запасной проход
    без фильтра — именно он приносил ягоды по запросу "бургер".
    Теперь при неудаче просто упрощается запрос, а требование
    к тегам остаётся.
    """
    tags = required_tags(action)
    banned = excluded_tags(action)
    last_page = await get_last_action_page(key)
    start_page = last_page + 1
    added = 0

    query = get_search_query(action, pair_key)

    # От точной фразы к широкой, в конце — само ключевое слово.
    variants = query_variants(query)

    for tag in tags[:2]:
        if tag not in variants:
            variants.append(tag)

    for variant in variants:
        for page in range(start_page, start_page + PAGES_PER_FILL):
            try:
                photos = await search_photos(
                    provider,
                    variant,
                    page,
                    required=tags,
                    excluded=banned,
                )
            except Exception as error:
                print(
                    f"{provider.upper()} SEARCH ERROR:",
                    type(error).__name__,
                    str(error),
                )
                return added

            if not photos:
                break

            for photo in photos:
                if await add_action_image(
                    action=key,
                    provider=photo.provider,
                    photo_id=photo.photo_id,
                    image_url=photo.image_url,
                    fallback_url=photo.fallback_url,
                    photographer_name=photo.photographer_name,
                    photographer_url=photo.photographer_url,
                    source_url=photo.source_url,
                    source_page=page,
                ):
                    added += 1

        if added:
            break

    if not added:
        print(f"IMAGES: ничего не найдено для {key} (запрос: {query})")

    return added


async def get_image_for_action(
    action: Action,
    pair_key: str = "neutral",
):
    providers = available_providers()

    if not providers:
        print("IMAGE PROVIDERS: ни один источник не настроен")
        return None

    for provider in providers:
        key = collection_key(provider, action, pair_key)

        image = await get_unused_action_image(key)
        if image is not None:
            return image

        added = await fill_collection(provider, action, key, pair_key)

        if added:
            image = await get_unused_action_image(key)
            if image is not None:
                return image

        # Новых картинок нет — крутим по кругу уже собранные.
        if await count_action_images(key):
            await reset_action_images(key)
            image = await get_unused_action_image(key)
            if image is not None:
                return image

    return None
