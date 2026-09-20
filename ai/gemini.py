import os

from google import genai
from google.genai import types

from ai.prompts import SYSTEM_PROMPT


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set")


# Модель вынесена в переменную окружения: когда Google выкатит
# следующую версию, перекатывать код не придётся.
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "600"))
TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.8"))


client = genai.Client(api_key=GEMINI_API_KEY)


async def ask_gemini(
    prompt: str,
    use_search: bool = True,
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

    response = await client.aio.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            tools=tools,
        ),
    )

    answer = (response.text or "").strip()

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
