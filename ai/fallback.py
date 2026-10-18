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
import time
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
        now = time.monotonic()
        alive = [m for m in self.default_models if now - _gone.get((self.name, m), -1e12) > GONE_FOR]
        ordered = ([good] if good in alive else []) + [m for m in alive if m != good]
        # Все модели «пропали» — всё равно пробуем: вдруг вернулись
        return ordered or list(self.default_models)


# Какая модель у провайдера ответила последней — с неё и начинаем
_working: dict[str, str] = {}

# Модели, которых у провайдера больше нет (404) — сутки их не трогаем
_gone: dict[tuple[str, str], float] = {}
GONE_FOR = 24 * 3600


PROVIDERS = (
    Provider(
        name="Groq",
        url="https://api.groq.com/openai/v1/chat/completions",
        key_env="GROQ_API_KEY",
        model_env="GROQ_MODEL",
        # Llama и Qwen3-32B Groq убрал из бесплатного тарифа (август 2026) —
        # у каждой из оставшихся свой суточный лимит
        default_models=("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"),
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


def _try_next(status: int, text: str) -> bool:
    """Эту модель сейчас не получить, но у провайдера есть другие.

    429/503 у бесплатных моделей — перегружена именно эта модель, а не ключ.
    401/403 — плохой ключ: остальные модели тоже не ответят.
    """
    return _model_gone(status, text) or status in (408, 429, 500, 502, 503, 504)


def _payload(model: str, system: str, prompt: str, temperature: float, max_tokens: int) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # «Думающие» модели тратят токены на рассуждения: без запаса ответ
    # приходит пустым. Просим думать поменьше и даём место на ответ.
    name = model.lower()
    if "gpt-oss" in name:
        payload["reasoning_effort"] = "low"
        payload["max_tokens"] = max(max_tokens, 1500)
    elif "qwen3" in name:
        payload["reasoning_format"] = "hidden"
        payload["max_tokens"] = max(max_tokens, 1500)
    elif "reasoning" in name or "deepseek-r1" in name:
        payload["max_tokens"] = max(max_tokens, 1500)

    return payload


async def _ask_one(provider: Provider, system: str, prompt: str, temperature: float, max_tokens: int) -> str:
    headers = {"Authorization": f"Bearer {provider.key}"}
    if provider.name == "OpenRouter":
        headers["X-Title"] = "Maruska bot"

    last = ""

    for model in provider.models:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                provider.url, json=_payload(model, system, prompt, temperature, max_tokens), headers=headers,
            )

        from ai import usage

        if response.status_code != 200:
            usage.record(provider.name, model, "limit" if response.status_code == 429 else "error")
            last = f"{provider.name} {model} HTTP {response.status_code}: {response.text[:200]}"
            if _model_gone(response.status_code, response.text):
                _gone[(provider.name, model)] = time.monotonic()
            if _try_next(response.status_code, response.text):
                logger.warning("AI FALLBACK: %s у %s сейчас недоступна (HTTP %s), беру следующую",
                               model, provider.name, response.status_code)
                continue
            raise RuntimeError(last)

        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        answer = clean((choice.get("message") or {}).get("content") or "")

        spent = (data.get("usage") or {}).get("total_tokens") or 0

        if not answer:
            usage.record(provider.name, model, "error", spent)
            last = f"{provider.name} {model}: пустой ответ ({choice.get('finish_reason')})"
            logger.warning("AI FALLBACK: %s", last)
            continue

        if choice.get("finish_reason") == "length":
            from ai.gemini import trim_to_sentence

            answer = trim_to_sentence(answer)

        usage.record(provider.name, model, "ok", spent)
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


async def self_check() -> list[str]:
    """Строки для лога на старте: кто из запасных реально отвечает. Ключи не печатаются."""
    lines = []
    for provider in PROVIDERS:
        if not provider.key:
            lines.append(f"{provider.name}: ключ не задан ({provider.key_env})")
            continue
        try:
            answer = await _ask_one(provider, "Ответь коротко, по-русски.", "Скажи одним словом: работает", 0.0, 300)
            lines.append(f"{provider.name}: отвечает ({_working.get(provider.name, '?')}) — «{answer[:40]}»")
        except Exception as error:
            lines.append(f"{provider.name}: НЕ ОТВЕЧАЕТ — {type(error).__name__} {str(error)[:160]}")
    return lines
