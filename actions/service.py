import os
from urllib.parse import urlencode

import httpx

from actions.catalog import Action
from database.repository import (
    get_unused_action_image,
    get_last_action_page,
    add_action_image,
    reset_action_images,
)


UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
UNSPLASH_API_URL = "https://api.unsplash.com/search/photos"
APP_NAME = "maruska_telegram_bot"


PAIR_SEARCHES = {
    "male_female": {
        "hug": "man woman hugging together",
        "kiss": "man woman kissing",
        "highfive": "man woman high five",
        "handshake": "man woman handshake",
        "support": "man woman supporting each other",
        "congratulations": "man woman celebrating together",
        "party": "man woman party together",
        "movie": "man woman watching movie together",
        "music": "man woman listening to music together",
        "dance": "man woman dancing together",
    },
    "male_male": {
        "hug": "two men hugging",
        "kiss": "two men kissing",
        "highfive": "two men high five",
        "handshake": "two men handshake",
        "support": "two men supporting each other",
        "congratulations": "two men celebrating together",
        "party": "two men at a party",
        "movie": "two men watching movie together",
        "music": "two men listening to music together",
        "dance": "two men dancing together",
    },
    "female_female": {
        "hug": "two women hugging",
        "kiss": "two women kissing",
        "highfive": "two women high five",
        "handshake": "two women handshake",
        "support": "two women supporting each other",
        "congratulations": "two women celebrating together",
        "party": "two women at a party",
        "movie": "two women watching movie together",
        "music": "two women listening to music together",
        "dance": "two women dancing together",
    },
    "neutral": {
        "hug": "two people hugging",
        "kiss": "two people kissing",
        "highfive": "two people high five",
        "handshake": "two people handshake",
        "support": "two people supporting each other",
        "congratulations": "two people celebrating together",
        "party": "two people at a party",
        "movie": "two people watching movie together",
        "music": "two people listening to music together",
        "dance": "two people dancing together",
    },
}


async def search_unsplash(action: Action, page: int, search_query: str | None = None):
    if not UNSPLASH_ACCESS_KEY:
        raise RuntimeError("UNSPLASH_ACCESS_KEY is not set")

    params = {
        "query": search_query or action.search,
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


def get_search_query(action: Action, pair_key: str) -> str:
    if action.category == "pair":
        return PAIR_SEARCHES.get(pair_key, {}).get(
            action.key,
            action.search,
        )
    return action.search


async def fill_action_images(
    action: Action,
    image_key: str,
    pair_key: str = "neutral",
):
    last_page = await get_last_action_page(image_key)
    start_page = last_page + 1
    search_query = get_search_query(action, pair_key)
    added = 0

    for page in range(start_page, start_page + 3):
        try:
            data = await search_unsplash(
                action,
                page,
                search_query=search_query,
            )
        except Exception as error:
            print(
                "UNSPLASH SEARCH ERROR:",
                type(error).__name__,
                str(error),
            )
            break

        results = data.get("results", [])
        if not results:
            break

        for photo in results:
            photo_id = photo.get("id")
            urls = photo.get("urls", {})
            image_url = urls.get("regular")

            user = photo.get("user", {})
            photographer_name = (
                user.get("name")
                or user.get("username")
                or "Unsplash photographer"
            )

            photographer_username = user.get("username")
            if photographer_username:
                photographer_url = (
                    "https://unsplash.com/@"
                    + photographer_username
                    + "?"
                    + urlencode({
                        "utm_source": APP_NAME,
                        "utm_medium": "referral",
                    })
                )
            else:
                photographer_url = (
                    "https://unsplash.com/?"
                    + urlencode({
                        "utm_source": APP_NAME,
                        "utm_medium": "referral",
                    })
                )

            unsplash_url = (
                photo.get("links", {}).get("html")
            )

            if not photo_id or not image_url or not unsplash_url:
                continue

            if "?" in unsplash_url:
                unsplash_url += "&" + urlencode({
                    "utm_source": APP_NAME,
                    "utm_medium": "referral",
                })
            else:
                unsplash_url += "?" + urlencode({
                    "utm_source": APP_NAME,
                    "utm_medium": "referral",
                })

            if await add_action_image(
                action=image_key,
                photo_id=photo_id,
                image_url=image_url,
                photographer_name=photographer_name,
                photographer_url=photographer_url,
                unsplash_url=unsplash_url,
                source_page=page,
            ):
                added += 1

    return added


async def get_image_for_action(
    action: Action,
    image_key: str | None = None,
    pair_key: str = "neutral",
):
    # Для парных действий отдельная коллекция на каждую комбинацию пола.
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

    # Если новых результатов больше нет — начинаем новый цикл.
    await reset_action_images(collection_key)
    return await get_unused_action_image(collection_key)
