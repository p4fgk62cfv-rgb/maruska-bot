import os

from google import genai
from google.genai import types

from ai.prompts import build_prompt


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set")


# Модель вынесена в переменную окружения: когда Google выкатит
# следующую версию, перекатывать код не придётся.
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "1000"))
TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.8"))

# У Gemini 3 по умолчанию thinking_level=HIGH: модель подолгу
# "думает" перед ответом, и в чате это выливается в 5-6 секунд
# ожидания. Для болтовни рассуждения не нужны.
#   minimal — самый быстрый (Gemini 3 Flash)
#   low     — быстрый, чуть осмысленнее
#   off     — не передавать параметр вообще
THINKING_LEVEL = os.getenv("GEMINI_THINKING", "low").strip().lower()

# Если модель или версия SDK не знает про thinking_level,
# выключаем его на весь процесс после первой же ошибки.
_thinking_supported = THINKING_LEVEL not in ("", "off", "none")


client = genai.Client(api_key=GEMINI_API_KEY)


def _build_config(tools, with_thinking: bool, persona: str | None = None):
    options = dict(
        system_instruction=build_prompt(persona),
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        tools=tools,
    )

    if with_thinking:
        options["thinking_config"] = types.ThinkingConfig(
            thinking_level=THINKING_LEVEL
        )

    return types.GenerateContentConfig(**options)


async def _generate(prompt: str, tools, persona: str | None = None):
    global _thinking_supported

    if _thinking_supported:
        try:
            return await client.aio.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=_build_config(tools, True, persona),
            )
        except Exception as error:
            message = str(error).lower()
            unsupported = (
                "thinking" in message
                or "unknown field" in message
                or "not supported" in message
                or isinstance(error, (TypeError, AttributeError, ValueError))
            )

            if not unsupported:
                raise

            print(
                "GEMINI: thinking_level не поддерживается, отключаю —",
                type(error).__name__,
            )
            _thinking_supported = False

    return await client.aio.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=_build_config(tools, False, persona),
    )


SENTENCE_ENDS = ".!?…"


def trim_to_sentence(text: str) -> str:
    """
    Обрезает хвост до последнего законченного предложения.
    Если законченных нет — отдаёт как есть с многоточием.
    """
    cut = max(text.rfind(char) for char in SENTENCE_ENDS)

    # Эмодзи и закрывающие кавычки после точки сохраняем
    if cut != -1:
        tail = text[cut + 1:]
        if len(tail) <= 3 and not tail.strip(" \"»)"):
            return text

        trimmed = text[:cut + 1].strip()
        if len(trimmed) >= 20:
            return trimmed

    return text.rstrip(" ,-—") + "…"


def _hit_token_limit(response) -> bool:
    try:
        candidate = (getattr(response, "candidates", None) or [None])[0]
        reason = getattr(candidate, "finish_reason", None)
        return "MAX_TOKENS" in str(reason).upper()
    except Exception:
        return False


async def ask_gemini(
    prompt: str,
    use_search: bool = True,
    persona: str | None = None,
) -> tuple[str, list[dict]]:
    """
    Отправляет запрос в Gemini.

    use_search=True — модель может пользоваться Google Search.

    Возвращает (текст ответа, список источников).
    """
    tools = []

    if use_search:
        tools.append(
            types.Tool(google_search=types.GoogleSearch())
        )

    response = await _generate(prompt, tools, persona)

    answer = (response.text or "").strip()

    # Если модель упёрлась в лимит токенов, обрываем по последнему
    # законченному предложению — лучше короче, чем на полуслове.
    if answer and _hit_token_limit(response):
        answer = trim_to_sentence(answer)

    sources: list[dict] = []

    try:
        candidates = getattr(response, "candidates", None) or []

        if candidates:
            grounding = getattr(candidates[0], "grounding_metadata", None)
            chunks = getattr(grounding, "grounding_chunks", None) or []

            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if not web:
                    continue

                uri = getattr(web, "uri", None)
                if not uri:
                    continue

                sources.append({
                    "title": getattr(web, "title", None) or "Источник",
                    "url": uri,
                })

    except Exception as error:
        print("SOURCE PARSE ERROR:", type(error).__name__, str(error))

    return answer, sources
