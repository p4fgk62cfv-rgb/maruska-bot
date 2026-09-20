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


UNSPLASH_ACCESS_KEY = os.getenv(
    "UNSPLASH_ACCESS_KEY"
)

UNSPLASH_API_URL = (
    "https://api.unsplash.com/search/photos"
)

APP_NAME = "maruska_telegram_bot"


async def search_unsplash(
    action: Action,
    page: int,
):

    if not UNSPLASH_ACCESS_KEY:
        raise RuntimeError(
            "UNSPLASH_ACCESS_KEY is not set"
        )

    params = {
        "query": action.search,
        "page": page,
        "per_page": 30,
        "orientation": "landscape",
        "content_filter": "high",
    }

    headers = {
        "Authorization": (
            f"Client-ID {UNSPLASH_ACCESS_KEY}"
        ),
        "Accept-Version": "v1",
    }

    async with httpx.AsyncClient(
        timeout=20
    ) as client:

        response = await client.get(
            UNSPLASH_API_URL,
            params=params,
            headers=headers,
        )

        response.raise_for_status()

        return response.json()


async def fill_action_images(
    action: Action,
):

    last_page = await get_last_action_page(
        action.key
    )

    start_page = last_page + 1

    added = 0

    # Пытаемся найти новые фотографии
    # максимум на трёх страницах.
    for page in range(
        start_page,
        start_page + 3,
    ):

        try:

            data = await search_unsplash(
                action,
                page,
            )

        except Exception as error:

            print(
                "UNSPLASH SEARCH ERROR:",
                type(error).__name__,
                str(error),
            )

            break

        results = data.get(
            "results",
            [],
        )

        if not results:
            break

        for photo in results:

            photo_id = photo.get("id")

            urls = photo.get(
                "urls",
                {},
            )

            image_url = urls.get(
                "regular"
            )

            user = photo.get(
                "user",
                {},
            )

            photographer_name = (
                user.get("name")
                or user.get("username")
                or "Unsplash photographer"
            )

            photographer_username = (
                user.get("username")
            )

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

            unsplash_url = photo.get(
                "links",
                {},
            ).get(
                "html"
            )

            if not photo_id:
                continue

            if not image_url:
                continue

            if not unsplash_url:
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

            was_added = await add_action_image(
                action=action.key,
                photo_id=photo_id,
                image_url=image_url,
                photographer_name=photographer_name,
                photographer_url=photographer_url,
                unsplash_url=unsplash_url,
                source_page=page,
            )

            if was_added:
                added += 1

    return added


async def get_image_for_action(
    action: Action,
):

    # Сначала используем уже загруженную
    # в базу, но ещё не использованную фотографию.
    image = await get_unused_action_image(
        action.key
    )

    if image is not None:
        return image

    # Все текущие фотографии использованы.
    # Ищем следующую партию.
    added = await fill_action_images(
        action
    )

    if added:

        image = await get_unused_action_image(
            action.key
        )

        if image is not None:
            return image

    # Если Unsplash дал только уже существующие
    # фотографии — начинаем новый цикл.
    await reset_action_images(
        action.key
    )

    return await get_unused_action_image(
        action.key
    )
