import os

from google import genai
from google.genai import types

from ai.prompts import SYSTEM_PROMPT


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set")


MODEL_NAME = "gemini-3.6-flash"


client = genai.Client(
    api_key=GEMINI_API_KEY
)


async def ask_gemini(
    prompt: str,
    use_search: bool = True,
):
    """
    Отправляет запрос в Gemini.

    use_search=True:
        Gemini получает возможность использовать Google Search.

    Возвращает:
        answer — текст ответа
        sources — найденные источники
    """

    tools = []

    if use_search:
        tools.append(
            types.Tool(
                google_search=types.GoogleSearch()
            )
        )

    response = await client.aio.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
            max_output_tokens=1000,
            tools=tools,
        ),
    )

    answer = (
        response.text or ""
    ).strip()

    sources = []

    try:
        candidate = response.candidates[0]
        grounding_metadata = getattr(
            candidate,
            "grounding_metadata",
            None,
        )

        if grounding_metadata:

            chunks = getattr(
                grounding_metadata,
                "grounding_chunks",
                []
            )

            for chunk in chunks:

                web = getattr(
                    chunk,
                    "web",
                    None,
                )

                if not web:
                    continue

                title = getattr(
                    web,
                    "title",
                    None,
                )

                uri = getattr(
                    web,
                    "uri",
                    None,
                )

                if uri:
                    sources.append({
                        "title": title or "Источник",
                        "url": uri,
                    })

    except Exception as e:
        print(
            "SOURCE PARSE ERROR:",
            type(e).__name__,
            str(e),
        )

    return answer, sources
