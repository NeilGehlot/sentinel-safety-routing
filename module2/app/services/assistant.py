"""Provider-agnostic safety assistant owned entirely by Module 2."""

import json
import re
from typing import Any

import httpx

from app.config import settings

SYSTEM_PROMPT = (
    "You are a calm, concise safety assistant inside a personal-safety app. "
    "Use only the supplied risk context. Never invent incidents, locations, or statistics. "
    "Never claim the user is being followed or attacked. Keep answers to 2-3 sentences. "
    "Return only JSON with a single key: answer."
)
FALLBACK_ANSWER = (
    "I can't reach the assistant service right now. Your current risk level is shown "
    "on the dashboard - please rely on that and contact your guardians directly if "
    "you're concerned."
)
SUPPORTED_PROVIDERS = {"openai", "anthropic", "grok", "groq"}
FORBIDDEN = ("follow", "attack")
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"


def _api_key(provider: str) -> str:
    if provider == "grok":
        return settings.grok_api_key
    if provider == "groq":
        return settings.groq_api_key
    return settings.llm_api_key


def provider_status() -> dict[str, Any]:
    provider = settings.llm_provider.strip().lower()
    supported = provider in SUPPORTED_PROVIDERS
    return {
        "provider": provider or "unconfigured",
        "supported": supported,
        "mock_mode": settings.mock_mode,
        "model_configured": bool(_model(provider)),
        "key_configured": bool(_api_key(provider)),
        "ready": (
            supported
            and not settings.mock_mode
            and bool(_model(provider))
            and bool(_api_key(provider))
        ),
    }


def ask(question: str, context: dict[str, Any]) -> dict[str, str]:
    provider = settings.llm_provider.strip().lower()
    status = _preflight_status(provider, question)
    if status is not None:
        return {"answer": FALLBACK_ANSWER, "provider_status": status}

    try:
        raw = _complete(provider, question.strip(), context)
        try:
            payload = _parse_json(raw)
        except (json.JSONDecodeError, ValueError):
            payload = {"answer": raw.strip()}
    except httpx.TimeoutException:
        return {"answer": FALLBACK_ANSWER, "provider_status": "timeout"}
    except httpx.HTTPStatusError as exc:
        return {"answer": FALLBACK_ANSWER, "provider_status": _http_error_status(exc)}
    except Exception:
        return {"answer": FALLBACK_ANSWER, "provider_status": "provider_error"}

    answer = payload.get("answer") if isinstance(payload, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        return {"answer": FALLBACK_ANSWER, "provider_status": "invalid_response"}
    answer = answer.strip()
    if any(token in answer.lower() for token in FORBIDDEN):
        return {"answer": FALLBACK_ANSWER, "provider_status": "unsafe_response"}
    return {"answer": answer, "provider_status": "ok"}


def _preflight_status(provider: str, question: str) -> str | None:
    if not question.strip():
        return "empty_question"
    if provider not in SUPPORTED_PROVIDERS:
        return "unsupported_provider" if provider else "missing_provider"
    if not _model(provider):
        return "missing_model"
    if not _api_key(provider):
        return "missing_key"
    if settings.mock_mode:
        return "mock_mode"
    return None


def _model(provider: str) -> str:
    return settings.llm_model or (DEFAULT_GROQ_MODEL if provider == "groq" else "")


def _http_error_status(exc: httpx.HTTPStatusError) -> str:
    status = exc.response.status_code
    category = "authentication" if status == 401 else "rate_limited" if status == 429 else ""
    try:
        error = exc.response.json().get("error", {})
        code = error.get("code") or error.get("type") or ""
        message = str(error.get("message") or "")
        lowered = f"{code} {message}".lower()
        if "model" in lowered and any(token in lowered for token in ("not found", "not_found", "does not exist", "decommission")):
            category = "model_not_found"
        elif code:
            category = re.sub(r"[^a-z0-9_]+", "_", str(code).lower()).strip("_")[:48]
    except Exception:
        category = ""
    return f"http_{status}:{category}" if category else f"http_{status}"


def _complete(provider: str, question: str, context: dict[str, Any]) -> str:
    if provider == "anthropic":
        return _anthropic(question, context)
    urls = {
        "openai": "https://api.openai.com/v1/chat/completions",
        "grok": "https://api.x.ai/v1/chat/completions",
        "groq": "https://api.groq.com/openai/v1/chat/completions",
    }
    return _openai_compatible(
        urls[provider],
        _api_key(provider),
        question,
        context,
        provider=provider,
    )


def _openai_compatible(
    url: str,
    api_key: str,
    question: str,
    context: dict[str, Any],
    *,
    provider: str,
) -> str:
    body = {
        "model": _model(provider),
        "temperature": 0,
        "max_tokens": settings.llm_max_tokens,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps({"question": question, "context": context}),
            },
        ],
    }
    if provider != "groq":
        body["response_format"] = {"type": "json_object"}
    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        response = client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
    return str(payload["choices"][0]["message"]["content"])


def _anthropic(question: str, context: dict[str, Any]) -> str:
    body = {
        "model": settings.llm_model,
        "max_tokens": settings.llm_max_tokens,
        "system": SYSTEM_PROMPT,
        "messages": [
            {
                "role": "user",
                "content": json.dumps({"question": question, "context": context}),
            }
        ],
    }
    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        response = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.llm_api_key,
                "anthropic-version": "2023-06-01",
            },
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
    return str(payload["content"][0]["text"])


def _parse_json(raw: str) -> object:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)
