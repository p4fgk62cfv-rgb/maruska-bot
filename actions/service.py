"""
Подбор картинок для действий.

Коллекция хранится отдельно для каждого источника и каждой
комбинации пола: "pixabay/hug:male_female".

Пока в коллекции есть неиспользованные картинки — берём оттуда.
Кончились — дозапрашиваем следующую страницу у источника.
Источник больше ничего не отдаёт — сбрасываем цикл и идём по кругу.
"""

from actions.catalog import Action
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
        "hug": "couple hugging happy",
        "kiss": "couple kissing happy",
        "highfive": "man woman high five",
        "handshake": "man woman handshake",
        "support": "couple smiling together",
        "congratulations": "couple celebrating confetti",
        "party": "couple party celebration",
        "movie": "couple watching movie",
        "music": "couple listening music",
        "dance": "couple dancing happy",
    },
    "male_male": {
        "hug": "friends hugging men",
        "kiss": "couple kissing happy",
        "highfive": "men high five",
        "handshake": "men handshake smiling",
        "support": "friends laughing men",
        "congratulations": "friends celebrating confetti",
        "party": "friends party celebration",
        "movie": "friends watching movie",
        "music": "friends listening music",
        "dance": "friends dancing happy",
    },
    "female_female": {
        "hug": "friends hugging women",
        "kiss": "women couple happy",
        "highfive": "women high five",
        "handshake": "women handshake smiling",
        "support": "friends laughing women",
        "congratulations": "friends celebrating confetti",
        "party": "friends party celebration",
        "movie": "friends watching movie",
        "music": "friends listening music",
        "dance": "women dancing happy",
    },
    "neutral": {
        "hug": "friends hugging happy",
        "kiss": "couple kissing happy",
        "highfive": "friends high five",
        "handshake": "handshake smiling",
        "support": "friends laughing together",
        "congratulations": "celebrating confetti happy",
        "party": "party celebration friends",
        "movie": "watching movie popcorn",
        "music": "listening music happy",
        "dance": "dancing happy people",
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


def collection_key(provider: str, action: Action, pair_key: str) -> str:
    base = action.key

    if action.category == "pair":
        base = f"{action.key}:{pair_key}"

    return f"{provider}/{base}"


async def fill_collection(
    provider: str,
    action: Action,
    key: str,
    pair_key: str,
) -> int:
    last_page = await get_last_action_page(key)
    start_page = last_page + 1

    query = get_search_query(action, pair_key)
    added = 0

    for variant in query_variants(query):
        for page in range(start_page, start_page + PAGES_PER_FILL):
            try:
                photos = await search_photos(provider, variant, page)
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
