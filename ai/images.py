"""
Рисунки Маруськи: «Мара, нарисуй кота в шляпе».

Художники (каждый включается и выключается в админке, основной выбирается там же):

    gemini        — Gemini (gemini-2.5-flash-image и др.). На бесплатном
                    ключе Google лимит картинок нулевой — нужен платный тариф.
    pollinations  — бесплатно. Без ключа — общая очередь, часто занята;
                    с ключом POLLINATIONS_TOKEN (enter.pollinations.ai) надёжнее.
    huggingface   — FLUX.1-schnell через Hugging Face, бесплатный ключ HF_TOKEN.

Сначала основной, потом остальные включённые по порядку.

Защита от 18+ (тумблер «Защита от 18+», включена по умолчанию):
  1. запрос с откровенными словами не отправляется никому;
  2. к запросу ничего не дописываем: «одеты», «без наготы» художники
     понимают как просьбу нарисовать людей и одежду;
  3. готовую картинку проверяет Gemini-зрение. Нагота, бельё, купальники,
     дети в откровенной одежде — не показываем. Не удалось проверить —
     тоже не показываем.
"""

import logging
import os
import re
import time
from urllib.parse import quote

import httpx


logger = logging.getLogger("maruska.draw")

ARTISTS = ("gemini", "pollinations", "huggingface")
TITLES = {"gemini": "Gemini", "pollinations": "Pollinations", "huggingface": "Hugging Face"}

GEMINI_MODELS = tuple(
    m.strip() for m in (
        os.getenv("GEMINI_IMAGE_MODEL", "")
        or "gemini-2.5-flash-image,gemini-3-pro-image-preview,gemini-2.0-flash-preview-image-generation"
    ).split(",") if m.strip()
)

POLLINATIONS = ("https://image.pollinations.ai/prompt/{prompt}"
                "?width=1024&height=1024&nologo=true&safe=true&seed={seed}")
POLLINATIONS_GEN = ("https://gen.pollinations.ai/image/{prompt}"
                    "?width=1024&height=1024&safe=true&seed={seed}")
HF_MODEL = os.getenv("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
HF_URL = "https://router.huggingface.co/hf-inference/models/{model}"

# После лимита или запрета художника не дёргаем какое-то время
PAUSE = float(os.getenv("GEMINI_IMAGE_PAUSE_MINUTES", "30")) * 60
_paused: dict[str, float] = {}
_working: str | None = None

STYLE = (
    "Нарисуй яркую, красивую, детализированную картинку по запросу ниже. "
    "Без текста и надписей на картинке, если о них не просят. Запрос: "
)
# В запрос художнику НЕ дописываем «одеты», «без наготы» и т. п.: нейросети-художники
# не понимают отрицаний, и слова «одежда/нагота» сами добавляют на картинку людей.
# Так «флаг Франции» однажды превратился в людей в белье. Защита — только фильтр
# запроса до рисования и проверка готовой картинки после.
SAFE_STYLE = "Картинка для семейного чата. "


class DrawRefused(Exception):
    """Рисовать это не будем: откровенный запрос или картинка не прошла проверку."""


class DrawUnchecked(Exception):
    """Картинку не удалось проверить на 18+ — без проверки не показываем."""


class NoArtist(Exception):
    """Ни один включённый художник сейчас не может рисовать."""


# ---------------------------------------------------------
# Защита от 18+
# ---------------------------------------------------------

UNSAFE_RE = re.compile(
    r"(эрот|порн|секс|сексуальн|голая|голый|голые|голую|голенькая|обнаж|нагая|нагой|нагишом|без\s+одежд"
    r"|раздет|раздева|грудь|груди|сиськ|титьк|попк|попа\b|жоп|ягодиц|трусик|трусы|стринг|лифчик|бюстгальтер"
    r"|нижн\w*\s+бель|бельё|белье|бикини|купальник|стриптиз|интим|минет|член\b|пенис|вагин|оргазм|возбужд"
    r"|соблазн|похот|страстн|пошл|18\s*\+|хентай|nsfw|nude|naked|porn|sex|erotic|hentai|boobs|lingerie|topless|bikini)",
    re.IGNORECASE,
)


def unsafe_prompt(prompt: str) -> bool:
    return bool(UNSAFE_RE.search(prompt or ""))


def _mime(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


CHECK_QUESTION = (
    "You are a strict safety filter for a family group chat. Look at the image. "
    "Answer UNSAFE if ANY of these is true: nudity or partial nudity; exposed breasts, buttocks or genitals; "
    "people in underwear, lingerie or swimwear; any child or teenager shown undressed, in underwear, "
    "swimwear or revealing clothing; sexual, erotic or suggestive content or poses; graphic gore. "
    "Otherwise answer SAFE. Reply with exactly one word: SAFE or UNSAFE."
)


async def image_is_unsafe(data: bytes) -> bool | None:
    """
    Gemini смотрит на картинку. True — нельзя, False — можно, None — проверить не удалось.
    None тоже значит «не показывать»: картинку без проверки в чат не отправляем.
    """
    from google.genai import types

    from ai.gemini import MODEL_NAME, client

    contents = [types.Part.from_bytes(data=data, mime_type=_mime(data)), CHECK_QUESTION]

    # Gemini 3 по умолчанию долго «думает», и на маленьком лимите ответ приходил
    # пустым — поэтому запас токенов и короткое раздумье
    configs = []
    try:
        configs.append(types.GenerateContentConfig(
            temperature=0, max_output_tokens=600, thinking_config=types.ThinkingConfig(thinking_level="low"),
        ))
    except Exception:
        pass
    configs.append(types.GenerateContentConfig(temperature=0, max_output_tokens=600))

    for config in configs:
        try:
            response = await client.aio.models.generate_content(model=MODEL_NAME, contents=contents, config=config)
        except Exception as error:
            logger.warning("DRAW CHECK: ошибка проверки — %s %s", type(error).__name__, str(error)[:160])
            continue

        text = (response.text or "").strip().upper()
        # Фильтр Gemini иногда сам блокирует ответ на откровенную картинку
        blocked = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
        if blocked or "UNSAFE" in text:
            logger.info("DRAW CHECK: UNSAFE (%s)", blocked or text[:20])
            return True
        if text.startswith("SAFE"):
            logger.info("DRAW CHECK: SAFE")
            return False
        logger.warning("DRAW CHECK: непонятный ответ «%s»", text[:40])

    return None


# ---------------------------------------------------------
# Художники
# ---------------------------------------------------------

def _gone(error: Exception) -> bool:
    text = str(error).lower()
    return ("404" in text or "not found" in text or "not supported" in text
            or "does not support" in text or ("invalid" in text and "model" in text))


def _quota(error: Exception) -> bool:
    text = str(error).lower()
    return any(w in text for w in ("429", "402", "resource_exhausted", "quota", "403", "permission",
                                   "billing", "free tier", "payment"))


async def gemini_draw(prompt: str, safe: bool) -> bytes:
    from google.genai import types

    from ai.gemini import client

    global _working

    models = ([_working] if _working else []) + [m for m in GEMINI_MODELS if m != _working]
    last: Exception | None = None

    for model in models:
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=(SAFE_STYLE if safe else "") + STYLE + prompt,
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
    """Pollinations и Flux понимают только английский. Переводим запасной нейросетью, а без неё — Gemini."""
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


async def pollinations_draw(prompt: str, safe: bool) -> bytes:
    """
    Без ключа — общая бесплатная очередь («Classic API»): часто занята,
    отвечает 402/503 «at its limit, retry after 10s». С ключом
    POLLINATIONS_TOKEN (enter.pollinations.ai) — своя очередь.
    """
    import asyncio

    english = await translate(prompt)
    token = os.getenv("POLLINATIONS_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    last = ""

    for attempt in range(3):
        seed = (int(time.time()) + attempt) % 100000
        if token:
            # С ключом — новый API: своя очередь, модель можно выбрать
            url = POLLINATIONS_GEN.format(prompt=quote(english[:600]), seed=seed)
            model = os.getenv("POLLINATIONS_MODEL", "").strip()
            if model:
                url += "&model=" + quote(model)
        else:
            url = POLLINATIONS.format(prompt=quote(english[:600]), seed=seed)
        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
        if response.status_code == 200 and response.headers.get("content-type", "").startswith("image/"):
            return response.content
        last = f"Pollinations HTTP {response.status_code}"
        if response.status_code not in (402, 429, 502, 503):
            break
        # Очередь занята: Pollinations сам просит подождать 10 секунд
        await asyncio.sleep(10)

    raise RuntimeError(last)


async def huggingface_draw(prompt: str, safe: bool) -> bytes:
    token = os.getenv("HF_TOKEN", "").strip()
    if not token:
        raise NoArtist("Hugging Face: нет ключа HF_TOKEN")

    english = await translate(prompt)
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            HF_URL.format(model=HF_MODEL),
            headers={"Authorization": f"Bearer {token}", "Accept": "image/png"},
            json={"inputs": english[:600]},
        )

    if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
        raise RuntimeError(f"Hugging Face HTTP {response.status_code}: {response.text[:160]}")
    return response.content


DRAWERS = {"gemini": gemini_draw, "pollinations": pollinations_draw, "huggingface": huggingface_draw}


def available(name: str) -> bool:
    """Может ли художник рисовать вообще (есть ли ключ)."""
    if name == "huggingface":
        return bool(os.getenv("HF_TOKEN", "").strip())
    return True


def order(primary: str, enabled: set[str]) -> list[str]:
    """Основной первым, потом остальные включённые по порядку."""
    names = [primary] + [a for a in ARTISTS if a != primary]
    return [a for a in names if a in enabled and a in DRAWERS]


async def draw(prompt: str, primary: str = "gemini", enabled: set[str] | None = None,
               safe: bool = True) -> tuple[bytes, str]:
    """(картинка, кто нарисовал). DrawRefused — не рисуем; NoArtist — некому."""
    if safe and unsafe_prompt(prompt):
        raise DrawRefused("откровенный запрос")

    enabled = set(ARTISTS) if enabled is None else enabled
    tried = []

    for name in order(primary, enabled):
        if not available(name):
            continue
        if time.monotonic() < _paused.get(name, 0):
            continue
        tried.append(name)

        try:
            data = await DRAWERS[name](prompt, safe)
        except DrawRefused:
            raise
        except Exception as error:
            if _quota(error) or _gone(error):
                _paused[name] = time.monotonic() + PAUSE
                logger.warning("DRAW: %s не рисует (%s) — %d мин пропускаю его",
                               TITLES[name], str(error)[:160], PAUSE // 60)
            else:
                logger.warning("DRAW: %s не нарисовал (%s %s)", TITLES[name], type(error).__name__, str(error)[:160])
            continue

        if safe:
            verdict = await image_is_unsafe(data)
            if verdict:
                logger.warning("DRAW: картинка от %s не прошла проверку 18+ — не показываю", TITLES[name])
                raise DrawRefused("картинка не прошла проверку 18+")
            if verdict is None:
                logger.warning("DRAW: картинку от %s не удалось проверить — не показываю", TITLES[name])
                raise DrawUnchecked("проверка недоступна")

        return data, TITLES[name]

    raise NoArtist("никто не смог нарисовать: " + (", ".join(TITLES[t] for t in tried) or "все художники выключены"))


async def self_check() -> str:
    """Строка для лога на старте: какие художники доступны. Картинку не рисует — лимит не тратится."""
    parts = []
    try:
        from ai.gemini import client

        names = []
        pager = await client.aio.models.list()
        async for model in pager:
            name = (getattr(model, "name", "") or "").split("/")[-1]
            if "image" in name:
                names.append(name)
        ours = [m for m in GEMINI_MODELS if m in names]
        parts.append(f"Gemini: модель {ours[0]} (на бесплатном ключе лимит картинок 0)" if ours else "Gemini: моделей-художников нет")
    except Exception as error:
        parts.append(f"Gemini: не удалось узнать ({type(error).__name__})")
    parts.append("Pollinations: " + ("свой ключ" if os.getenv("POLLINATIONS_TOKEN", "").strip() else "без ключа, общая очередь"))
    parts.append("Hugging Face: " + ("ключ есть" if available("huggingface") else "нет ключа HF_TOKEN"))
    return "; ".join(parts)
