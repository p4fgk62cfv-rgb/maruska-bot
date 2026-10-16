"""
Запасной мозг Маруськи — бесплатные открытые модели.

Когда у Gemini кончился лимит или она не отвечает, Маруська молча
отвечает через другую нейросеть. Подключаются ключами в Railway:

    GROQ_API_KEY        — console.groq.com → API Keys (бесплатно)
    OPENROUTER_API_KEY  — openrouter.ai → Keys (бесплатные модели «:free»)

Пробуются по очереди: сначала Groq, потом OpenRouter. Модель каждого
можно сменить переменными GROQ_MODEL и OPENROUTER_MODEL — без правки кода.
Оба сервиса говорят на языке OpenAI API, поэтому клиент один.
"""

import logging
import os
import re
from dataclasses import dataclass

import httpx


logger = logging.getLogger("maruska.ai")


@dataclass(frozen=True)
class Provider:
    name: str
    url: str
    key_env: str
    model_env: str
    # Бесплатные модели появляются и исчезают: берём первую живую из списка
    default_models: tuple[str, ...]

    @property
    def key(self) -> str:
        return os.getenv(self.key_env, "").strip()

    @property
    def models(self) -> list[str]:
        own = os.getenv(self.model_env, "").strip()
        if own:
            return [own]
        good = _working.get(self.name)
        return ([good] if good else []) + [m for m in self.default_models if m != good]


# Какая модель у провайдера ответила последней — с неё и начинаем
_working: dict[str, str] = {}


PROVIDERS = (
    Provider(
        name="Groq",
        url="https://api.groq.com/openai/v1/chat/completions",
        key_env="GROQ_API_KEY",
        model_env="GROQ_MODEL",
        default_models=("llama-3.3-70b-versatile", "openai/gpt-oss-120b", "qwen/qwen3-32b", "llama-3.1-8b-instant"),
    ),
    Provider(
        name="OpenRouter",
        url="https://openrouter.ai/api/v1/chat/completions",
        key_env="OPENROUTER_API_KEY",
        model_env="OPENROUTER_MODEL",
        default_models=("google/gemma-4-31b-it:free", "google/gemma-4-26b-a4b-it:free", "nvidia/nemotron-3-super-120b-a12b:free"),
    ),
)

TIMEOUT = float(os.getenv("FALLBACK_TIMEOUT", "25"))

# Рассуждающие модели присылают «мысли» в <think>…</think> — в чат их не пускаем
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def configured() -> list[Provider]:
    return [p for p in PROVIDERS if p.key]


def clean(text: str) -> str:
    text = THINK_RE.sub("", text or "")
    # Незакрытый <think> — модель не успела додумать, ответа нет
    if "<think>" in text.lower():
        text = text[: text.lower().index("<think>")]
    return text.strip()


def _model_gone(status: int, text: str) -> bool:
    """Модель сняли или переименовали — пробуем следующую из списка."""
    text = text.lower()
    return status in (400, 404) and "model" in text and any(
        w in text for w in ("not found", "not exist", "decommission", "deprecat", "invalid", "unavailable", "no endpoints")
    )


async def _ask_one(provider: Provider, system: str, prompt: str, temperature: float, max_tokens: int) -> str:
    headers = {"Authorization": f"Bearer {provider.key}"}
    if provider.name == "OpenRouter":
        headers["X-Title"] = "Maruska bot"

    last = ""

    for model in provider.models:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(provider.url, json=payload, headers=headers)

        if response.status_code != 200:
            last = f"{provider.name} {model} HTTP {response.status_code}: {response.text[:200]}"
            if _model_gone(response.status_code, response.text):
                logger.warning("AI FALLBACK: модели %s у %s больше нет, беру следующую", model, provider.name)
                continue
            raise RuntimeError(last)

        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        answer = clean((choice.get("message") or {}).get("content") or "")

        if answer and choice.get("finish_reason") == "length":
            from ai.gemini import trim_to_sentence

            answer = trim_to_sentence(answer)

        _working[provider.name] = model
        return answer

    raise RuntimeError(last or f"{provider.name}: нет моделей")


async def ask_fallback(system: str, prompt: str, temperature: float, max_tokens: int) -> tuple[str, str]:
    """(ответ, кто ответил). Если ни один не ответил — исключение с причинами."""
    problems = []

    for provider in configured():
        try:
            answer = await _ask_one(provider, system, prompt, temperature, max_tokens)
        except Exception as error:
            problems.append(f"{provider.name}: {type(error).__name__} {error}")
            logger.warning("AI FALLBACK %s: %s %s", provider.name, type(error).__name__, error)
            continue

        if answer:
            return answer, provider.name

        problems.append(f"{provider.name}: пустой ответ")

    raise RuntimeError("; ".join(problems) or "запасные нейросети не подключены")
