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
IMAGE_VERSION = "v2"

PAIR_SEARCHES = {
    "male_female": {
        "hug": "man woman hugging together photo", "kiss": "man woman kissing together photo",
        "highfive": "man woman high five together photo", "handshake": "man woman handshake photo",
        "support": "man woman supporting each other photo", "congratulations": "man woman celebrating together photo",
        "party": "man woman at a party together photo", "movie": "man woman watching movie together photo",
        "music": "man woman listening to music together photo", "dance": "man woman dancing together photo",
    },
    "male_male": {
        "hug": "two men hugging together photo", "kiss": "two men kissing together photo",
        "highfive": "two men high five together photo", "handshake": "two men handshake photo",
        "support": "two men supporting each other photo", "congratulations": "two men celebrating together photo",
        "party": "two men at a party together photo", "movie": "two men watching movie together photo",
        "music": "two men listening to music together photo", "dance": "two men dancing together photo",
    },
    "female_female": {
        "hug": "two women hugging together photo", "kiss": "two women kissing together photo",
        "highfive": "two women high five together photo", "handshake": "two women handshake photo",
        "support": "two women supporting each other photo", "congratulations": "two women celebrating together photo",
        "party": "two women at a party together photo", "movie": "two women watching movie together photo",
        "music": "two women listening to music together photo", "dance": "two women dancing together photo",
    },
    "neutral": {
        "hug": "two people hugging together photo", "kiss": "two people kissing together photo",
        "highfive": "two people high five together photo", "handshake": "two people handshake photo",
        "support": "two people supporting each other photo", "congratulations": "two people celebrating together photo",
        "party": "two people at a party together photo", "movie": "two people watching movie together photo",
        "music": "two people listening to music together photo", "dance": "two people dancing together photo",
    },
}

# Отсекаем очевидно неправильные результаты Unsplash. Это особенно важно для
# фруктов: запрос banana может вернуть пальмы, банановый хлеб, листья и т.п.
FORBIDDEN_TERMS = {
    "banana": ("banana bread", "banana cake", "banana muffin", "banana smoothie", "banana tree", "banana plant", "plantation", "leaves", "leaf", "palm tree"),
    "strawberry": ("strawberry cake", "strawberry dessert", "strawberry smoothie", "plant", "leaf"),
    "watermelon": ("watermelon juice", "watermelon smoothie", "plant", "field"),
    "apple": ("apple pie", "apple cake", "apple juice", "apple tree", "tree"),
    "orange": ("orange juice", "orange cake", "orange tree", "plant"),
    "grapes": ("grape vineyard", "vineyard", "wine bottle", "wine glass", "wine"),
    "rose": ("rose tattoo", "rose illustration", "rose drawing", "single rose"),
    "tulips": ("tulip field", "tulip garden", "single tulip"),
    "sunflowers": ("sunflower field", "single sunflower", "sunflower field landscape"),
    "flowers": ("flower field", "garden landscape", "single flower"),
    "orchid": ("single orchid", "orchid plant"),
    "lily": ("single lily", "lily pond"),
}


def _photo_text(photo: dict) -> str:
    parts = [
        photo.get("alt_description") or "",
        photo.get("description") or "",
    ]
    for tag in photo.get("tags") or []:
        if isinstance(tag, dict):
            parts.extend([tag.get("title") or "", tag.get("type") or ""])
    return " ".join(parts).lower()


def _looks_valid(action: Action, photo: dict) -> bool:
    text = _photo_text(photo)
    forbidden = FORBIDDEN_TERMS.get(action.key, ())
    return not any(term in text for term in forbidden)


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
        response = await client.get(UNSPLASH_API_URL, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


def get_search_query(action: Action, pair_key: str) -> str:
    if action.category == "pair":
        return PAIR_SEARCHES.get(pair_key, {}).get(action.key, action.search)
    return action.search


async def fill_action_images(action: Action, image_key: str, pair_key: str = "neutral"):
    last_page = await get_last_action_page(image_key)
    start_page = last_page + 1
    search_query = get_search_query(action, pair_key)
    added = 0

    for page in range(start_page, start_page + 3):
        try:
            data = await search_unsplash(action, page, search_query=search_query)
        except Exception as error:
            print("UNSPLASH SEARCH ERROR:", type(error).__name__, str(error))
            break

        results = data.get("results", [])
        if not results:
            break

        for photo in results:
            if not _looks_valid(action, photo):
                continue
            photo_id = photo.get("id")
            image_url = (photo.get("urls") or {}).get("regular")
            user = photo.get("user") or {}
            photographer_name = user.get("name") or user.get("username") or "Unsplash photographer"
            photographer_username = user.get("username")
            photographer_url = (
                "https://unsplash.com/@" + photographer_username + "?" + urlencode({"utm_source": APP_NAME, "utm_medium": "referral"})
                if photographer_username else
                "https://unsplash.com/?" + urlencode({"utm_source": APP_NAME, "utm_medium": "referral"})
            )
            unsplash_url = (photo.get("links") or {}).get("html")
            if not photo_id or not image_url or not unsplash_url:
                continue
            sep = "&" if "?" in unsplash_url else "?"
            unsplash_url += sep + urlencode({"utm_source": APP_NAME, "utm_medium": "referral"})
            if await add_action_image(action=image_key, photo_id=photo_id, image_url=image_url, photographer_name=photographer_name, photographer_url=photographer_url, unsplash_url=unsplash_url, source_page=page):
                added += 1
    return added


async def get_image_for_action(action: Action, image_key: str | None = None, pair_key: str = "neutral"):
    collection_key = image_key or action.key
    image = await get_unused_action_image(collection_key)
    if image is not None:
        return image

    added = await fill_action_images(action, collection_key, pair_key)
    if added:
        image = await get_unused_action_image(collection_key)
        if image is not None:
            return image

    await reset_action_images(collection_key)
    return await get_unused_action_image(collection_key)
