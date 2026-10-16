"""
Рисунки Маруськи: «Мара, нарисуй кота в шляпе».

Сначала Gemini (модель-художник из списка ниже). Если у Gemini нет
доступа к рисованию, кончился лимит или она отказалась — запасной
вариант Pollinations: бесплатно и без ключа, но попроще.

Модель Gemini можно задать переменной GEMINI_IMAGE_MODEL.
Pollinations выключается FREE_IMAGES=off.
"""

import logging
import os
import time
from urllib.parse import quote

import httpx


logger = logging.getLogger("maruska.draw")

GEMINI_MODELS = tuple(
    m.strip() for m in (
        os.getenv("GEMINI_IMAGE_MODEL", "")
        or "gemini-2.5-flash-image,gemini-3-pro-image-preview,gemini-2.0-flash-preview-image-generation"
    ).split(",") if m.strip()
)

FREE_ON = os.getenv("FREE_IMAGES", "on").strip().lower() not in ("off", "0", "no", "false")
POLLINATIONS = "https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true&safe=true&seed={seed}"

# После лимита или запрета Gemini-художника не дёргаем какое-то время
PAUSE = float(os.getenv("GEMINI_IMAGE_PAUSE_MINUTES", "30")) * 60
_paused_until = 0.0
_working: str | None = None

STYLE = (
    "Нарисуй яркую, красивую, детализированную картинку по запросу ниже. "
    "Без текста и надписей на картинке, если о них не просят. Запрос: "
)


class DrawRefused(Exception):
    """Модель отказалась рисовать (фильтр безопасности)."""


def _gone(error: Exception) -> bool:
    text = str(error).lower()
    return ("404" in text or "not found" in text or "not supported" in text
            or "does not support" in text or "invalid" in text and "model" in text)


def _quota(error: Exception) -> bool:
    text = str(error).lower()
    return any(w in text for w in ("429", "resource_exhausted", "quota", "403", "permission", "billing", "free tier"))


async def gemini_draw(prompt: str) -> bytes:
    from google.genai import types

    from ai.gemini import client

    global _working

    models = ([_working] if _working else []) + [m for m in GEMINI_MODELS if m != _working]
    last: Exception | None = None

    for model in models:
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=STYLE + prompt,
                config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
            )
        except Exception as error:
            last = error
            if _gone(error):
                logger.warning("DRAW: модели %s нет — пробую следующую", model)
                continue
            raise

        for candidate in getattr(response, "candidates", None) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                inline = getattr(part, "inline_data", None)
                if inline is not None and getattr(inline, "data", None):
                    _working = model
                    return inline.data

        # Картинки нет — обычно это отказ фильтра безопасности
        raise DrawRefused(f"{model}: без картинки ({(response.text or '')[:120]})")

    raise last or RuntimeError("нет моделей-художников")


async def translate(prompt: str) -> str:
    """Pollinations понимает только английский. Переводим запасной нейросетью, а без неё — Gemini."""
    if prompt.isascii():
        return prompt

    system = "Translate the image request to English. Reply with the translation only, no quotes."

    try:
        from ai import fallback

        if fallback.configured():
            answer, _who = await fallback.ask_fallback(system, prompt, temperature=0.2, max_tokens=200)
            if answer.strip():
                return answer.strip().strip('"«»')
    except Exception as error:
        logger.info("DRAW TRANSLATE fallback: %s", error)

    try:
        from google.genai import types

        from ai.gemini import MODEL_NAME, client

        response = await client.aio.models.generate_content(
            model=MODEL_NAME, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system, temperature=0.2, max_output_tokens=200),
        )
        if (response.text or "").strip():
            return response.text.strip().strip('"«»')
    except Exception as error:
        logger.info("DRAW TRANSLATE gemini: %s", error)

    return prompt


async def free_draw(prompt: str) -> bytes:
    english = await translate(prompt)
    url = POLLINATIONS.format(prompt=quote(english[:500]), seed=int(time.time()) % 100000)

    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        response = await client.get(url)

    if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
        raise RuntimeError(f"Pollinations HTTP {response.status_code}")
    return response.content


async def draw(prompt: str) -> tuple[bytes, str]:
    """(картинка, кто нарисовал). DrawRefused — если запрос не прошёл фильтр."""
    global _paused_until

    if time.monotonic() >= _paused_until:
        try:
            return await gemini_draw(prompt), "Gemini"
        except DrawRefused:
            raise
        except Exception as error:
            if _quota(error) or _gone(error):
                _paused_until = time.monotonic() + PAUSE
                logger.warning("DRAW: Gemini не рисует (%s) — %d мин рисует запасной художник",
                               str(error)[:160], PAUSE // 60)
            else:
                logger.warning("DRAW: Gemini не нарисовала (%s %s)", type(error).__name__, str(error)[:160])
            if not FREE_ON:
                raise

    if not FREE_ON:
        raise RuntimeError("Gemini-художник на паузе, запасной выключен")

    return await free_draw(prompt), "Pollinations"


async def self_check() -> str:
    """Строка для лога на старте: какие художники Gemini доступны. Картинку не рисует — лимит не тратится."""
    from ai.gemini import client

    try:
        names = []
        pager = await client.aio.models.list()
        async for model in pager:
            name = (getattr(model, "name", "") or "").split("/")[-1]
            if "image" in name:
                names.append(name)
    except Exception as error:
        return f"не удалось узнать модели Gemini ({type(error).__name__}); запасной — {'Pollinations' if FREE_ON else 'выключен'}"

    ours = [m for m in GEMINI_MODELS if m in names]
    if ours:
        return f"Gemini рисует моделью {ours[0]}; запасной — {'Pollinations' if FREE_ON else 'выключен'}"
    return (f"у Gemini нет моделей из списка ({', '.join(GEMINI_MODELS)}); есть: {', '.join(names[:6]) or 'никаких'}; "
            f"рисует {'Pollinations' if FREE_ON else 'никто'}")
