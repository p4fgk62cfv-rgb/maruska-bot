import os
from urllib.parse import urlencode

import httpx

from actions.catalog import Action
from database.repository import (
    get_unused_action_image,
    get_last_action_page,
    add_action_image,
    reset_action_images,
    count_action_images,
)


UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
UNSPLASH_API_URL = "https://api.unsplash.com/search/photos"
APP_NAME = "maruska_telegram_bot"

PAGES_PER_FILL = 3

UTM = {
    "utm_source": APP_NAME,
    "utm_medium": "referral",
}


# ---------------------------------------------------------
# Поисковые запросы для парных действий.
#
# Важно: запросы намеренно "тёплые" и позитивные.
# Нейтральные формулировки вроде "people supporting each other"
# Unsplash отдаёт как депрессивную документалку.
# ---------------------------------------------------------

PAIR_SEARCHES = {
    "male_female": {
        "hug": "happy couple hugging smiling bright",
        "kiss": "happy couple kissing joyful",
        "highfive": "man woman high five laughing",
        "handshake": "man woman handshake smiling office",
        "support": "man woman cheering each other up smiling",
        "congratulations": "man woman celebrating confetti happy",
        "party": "man woman party celebration fun",
        "movie": "couple watching movie popcorn cozy",
        "music": "couple listening music headphones happy",
        "dance": "man woman dancing happy",
    },
    "male_male": {
        "hug": "two men friendly hug smiling",
        "kiss": "two men happy couple",
        "highfive": "two men high five laughing",
        "handshake": "two men handshake smiling",
        "support": "two men cheering each other up laughing",
        "congratulations": "two men celebrating confetti happy",
        "party": "two men party celebration fun",
        "movie": "two friends watching movie popcorn",
        "music": "two men listening music happy",
        "dance": "two men dancing happy",
    },
    "female_female": {
        "hug": "two women friendly hug smiling",
        "kiss": "two women happy couple",
        "highfive": "two women high five laughing",
        "handshake": "two women handshake smiling",
        "support": "two women cheering each other up laughing",
        "congratulations": "two women celebrating confetti happy",
        "party": "two women party celebration fun",
        "movie": "two friends watching movie popcorn",
        "music": "two women listening music happy",
        "dance": "two women dancing happy",
    },
    "neutral": {
        "hug": "friends hugging smiling happy",
        "kiss": "happy couple kissing joyful",
        "highfive": "friends high five laughing",
        "handshake": "friendly handshake smiling",
        "support": "friends cheering each other up smiling",
        "congratulations": "friends celebrating confetti happy",
        "party": "friends party celebration fun",
        "movie": "friends watching movie popcorn cozy",
        "music": "friends listening music happy",
        "dance": "friends dancing happy",
    },
}


def get_search_query(action: Action, pair_key: str) -> str:
    if action.category == "pair":
        return PAIR_SEARCHES.get(pair_key, PAIR_SEARCHES["neutral"]).get(
            action.key,
            action.search,
        )
    return action.search


async def search_unsplash(
    page: int,
    search_query: str,
):
    if not UNSPLASH_ACCESS_KEY:
        raise RuntimeError("UNSPLASH_ACCESS_KEY is not set")

    params = {
        "query": search_query,
        "page": page,
        "per_page": 30,
        "orientation": "landscape",
        "content_filter": "high",
    }

    headers = {
        "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}",
        "Accept-Version": "v1",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            UNSPLASH_API_URL,
            params=params,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()


def _with_utm(url: str) -> str:
    separator = "&" if "?" in url else "?"
    return url + separator + urlencode(UTM)


async def fill_action_images(
    action: Action,
    image_key: str,
    pair_key: str = "neutral",
) -> int:
    last_page = await get_last_action_page(image_key)
    start_page = last_page + 1
    search_query = get_search_query(action, pair_key)
    added = 0

    for page in range(start_page, start_page + PAGES_PER_FILL):
        try:
            data = await search_unsplash(page, search_query)
        except Exception as error:
            print("UNSPLASH SEARCH ERROR:", type(error).__name__, str(error))
            break

        results = data.get("results", [])
        if not results:
            break

        for photo in results:
            photo_id = photo.get("id")
            image_url = photo.get("urls", {}).get("regular")
            unsplash_url = photo.get("links", {}).get("html")

            if not photo_id or not image_url or not unsplash_url:
                continue

            user = photo.get("user", {}) or {}

            photographer_name = (
                user.get("name")
                or user.get("username")
                or "Unsplash photographer"
            )

            username = user.get("username")

            if username:
                photographer_url = _with_utm(
                    f"https://unsplash.com/@{username}"
                )
            else:
                photographer_url = _with_utm("https://unsplash.com/")

            if await add_action_image(
                action=image_key,
                photo_id=photo_id,
                image_url=image_url,
                photographer_name=photographer_name,
                photographer_url=photographer_url,
                unsplash_url=_with_utm(unsplash_url),
                source_page=page,
            ):
                added += 1

    return added


async def get_image_for_action(
    action: Action,
    image_key: str | None = None,
    pair_key: str = "neutral",
):
    # У парных действий отдельная коллекция на каждую комбинацию пола.
    collection_key = image_key or action.key

    image = await get_unused_action_image(collection_key)
    if image is not None:
        return image

    added = await fill_action_images(
        action,
        image_key=collection_key,
        pair_key=pair_key,
    )

    if added:
        image = await get_unused_action_image(collection_key)
        if image is not None:
            return image

    # Новых результатов нет — начинаем цикл заново.
    if await count_action_images(collection_key):
        await reset_action_images(collection_key)
        return await get_unused_action_image(collection_key)

    return None
