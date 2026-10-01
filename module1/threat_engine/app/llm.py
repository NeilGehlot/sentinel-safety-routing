"""One provider-agnostic LLM client.

Provider, model, and API key come from the environment. No key means no call.
Every network call uses the configured timeout. MOCK_MODE never opens a socket.
Callers validate the JSON and fall back themselves when this returns None.
"""

import json
from collections.abc import Callable
from contextvars import ContextVar, Token
from typing import Any

import httpx
from cachetools import TTLCache

from app import config

CompleteFn = Callable[[str, str], str]

NEWS_SYSTEM = (
    "Extract one incident from the supplied news snippet. "
    "Return only JSON with keys incident_type, severity_0_to_1, location_text, and hours_old. "
    "severity_0_to_1 is a number from 0 to 1. hours_old is a number of hours and is 0 or greater. "
    "Use only the snippet. Do not invent a place or an incident that is not in the snippet. "
    "Do not apply distance or recency math. Those are applied in code."
)

EXPLAIN_SYSTEM = (
    "Phrase a short safety summary and at most 3 recommendations. "
    "Return only JSON with keys summary and recommendations. "
    "Use only the supplied data. Never invent places or incidents. "
    "Use a calm tone. Never claim the user is being followed or attacked. "
    "Do not change the numeric score or the contributor points."
)

ASSISTANT_SYSTEM = (
    "You are a calm, concise safety assistant inside a personal-safety app. "
    "You are given the user's current risk score (0-100, higher is riskier), risk level, "
    "route safety score if available, and a short list of nearby safe places if available. "
    "Answer the user's question using only this data. "
    "Never invent an incident, a location, or a statistic that was not supplied. "
    "Never claim the user is being followed or attacked. "
    "Keep answers to 2-3 sentences. "
    "Return only JSON with a single key: answer."
)

ASSISTANT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer"],
    "properties": {"answer": {"type": "string", "minLength": 1}},
}

NEWS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["incident_type", "severity_0_to_1", "location_text", "hours_old"],
    "properties": {
        "incident_type": {"type": "string", "minLength": 1},
        "severity_0_to_1": {"type": "number", "minimum": 0, "maximum": 1},
        "location_text": {"type": "string"},
        "hours_old": {"type": "number", "minimum": 0},
    },
}

_OVERRIDE: CompleteFn | None = None
_FORBIDDEN = ("follow", "attack")
_EXPLAIN_MODE: ContextVar[str | None] = ContextVar("explain_mode", default=None)
_LLM_CALLS: ContextVar[int] = ContextVar("llm_calls", default=0)
_EXPLAIN_CACHE: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=128, ttl=600)


def bind_explain(mode: str | None) -> tuple[Token[str | None], Token[int]]:
    """Remember whether this request asked for explain=llm. Reset after it."""
    return _EXPLAIN_MODE.set(mode or None), _LLM_CALLS.set(0)


def reset_explain(tokens: tuple[Token[str | None], Token[int]]) -> None:
    mode_token, call_token = tokens
    _EXPLAIN_MODE.reset(mode_token)
    _LLM_CALLS.reset(call_token)


def explain_mode() -> str | None:
    return _EXPLAIN_MODE.get()


def may_phrase() -> bool:
    """The model may phrase a summary only for explain=llm while USE_LLM is on."""
    return config.USE_LLM and _EXPLAIN_MODE.get() == "llm"


def clear_explain_cache() -> None:
    _EXPLAIN_CACHE.clear()


def _explain_key(payload: dict[str, Any]) -> str:
    score = int(round(float(payload.get("current_score", 0)) / 5.0) * 5)
    ranked = sorted(
        payload.get("contributors") or [],
        key=lambda item: abs(int(item.get("points", 0))),
        reverse=True,
    )[:3]
    names = ",".join(str(item.get("signal", "")) for item in ranked)
    return f"{score}:{names}"


def explanation_schema() -> dict[str, Any]:
    """JSON schema for the phrased summary. The item cap comes from config."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "recommendations"],
        "properties": {
            "summary": {"type": "string", "minLength": 1},
            "recommendations": {
                "type": "array",
                "maxItems": config.MAX_RECOMMENDATIONS,
                "items": {"type": "string", "minLength": 1},
            },
        },
    }


def wire_complete(fn: CompleteFn | None) -> None:
    """Tests install a fake completion. None restores the real client path."""
    global _OVERRIDE
    _OVERRIDE = fn


def ready() -> bool:
    """True when provider, model, and key are all set. An empty key is not ready."""
    provider = config.LLM_PROVIDER.strip().lower()
    if provider == "grok":
        api_key = config.GROK_API_KEY
    elif provider == "groq":
        api_key = config.GROQ_API_KEY
    else:
        api_key = config.LLM_API_KEY
    return bool(
        provider
        and config.LLM_MODEL.strip()
        and api_key.strip()
    )


def extract_news(snippet: str) -> dict[str, Any] | None:
    """Validated news JSON, or None when the call cannot be used."""
    if not snippet.strip():
        return None
    return _complete_json(NEWS_SYSTEM, snippet, NEWS_SCHEMA)


def phrase_explanation(payload: dict[str, Any]) -> dict[str, Any] | None:
    """One cached call for the summary and the tips, or None."""
    if not may_phrase():
        return None
    key = _explain_key(payload)
    cached = _EXPLAIN_CACHE.get(key)
    if cached is not None:
        return cached
    parsed = _complete_json(EXPLAIN_SYSTEM, json.dumps(payload), explanation_schema())
    if parsed is None:
        return None
    text = parsed["summary"] + " ".join(parsed["recommendations"])
    lowered = text.lower()
    if any(token in lowered for token in _FORBIDDEN):
        return None
    _EXPLAIN_CACHE[key] = parsed
    return parsed


def answer_assistant_question(question: str, context: dict[str, Any]) -> str | None:
    """One safety-assistant answer, or None when the call cannot be used."""
    if not ready() or not question.strip():
        return None
    if config.MOCK_MODE:
        return None
    user_payload = json.dumps({"question": question.strip(), "context": context})
    try:
        raw = (
            _OVERRIDE(ASSISTANT_SYSTEM, user_payload)
            if _OVERRIDE is not None
            else _http_complete(ASSISTANT_SYSTEM, user_payload)
        )
        parsed = _parse_json(raw)
    except Exception:
        return None
    validated = _validate(parsed, ASSISTANT_SCHEMA)
    if validated is None:
        return None
    if any(token in validated["answer"].lower() for token in _FORBIDDEN):
        return None
    return validated["answer"]


def _complete_json(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any] | None:
    """Call the model once. Timeout, bad JSON, or a missing key return None."""
    if not may_phrase() or not ready() or _LLM_CALLS.get() >= 1:
        return None
    _LLM_CALLS.set(_LLM_CALLS.get() + 1)
    try:
        if _OVERRIDE is not None:
            raw = _OVERRIDE(system, user)
        elif config.MOCK_MODE:
            return None
        else:
            raw = _http_complete(system, user)
        parsed = _parse_json(raw)
    except Exception:
        return None
    return _validate(parsed, schema)


def _parse_json(raw: str) -> object:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def _validate(payload: object, schema: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    properties: dict[str, Any] = schema["properties"]
    if schema.get("additionalProperties") is False and any(key not in properties for key in payload):
        return None
    for name in schema.get("required", []):
        if name not in payload:
            return None
    cleaned: dict[str, Any] = {}
    for name, rules in properties.items():
        if name not in payload:
            continue
        value = _validate_value(payload[name], rules)
        if value is None:
            return None
        cleaned[name] = value
    return cleaned


def _validate_value(value: object, rules: dict[str, Any]) -> Any | None:
    kind = rules.get("type")
    if kind == "string":
        if not isinstance(value, str):
            return None
        text = value.strip()
        minimum = int(rules.get("minLength", 0))
        if len(text) < minimum:
            return None
        return text
    if kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        number = float(value)
        if "minimum" in rules and number < float(rules["minimum"]):
            return None
        if "maximum" in rules and number > float(rules["maximum"]):
            return None
        return number
    if kind == "array":
        if not isinstance(value, list):
            return None
        if "maxItems" in rules and len(value) > int(rules["maxItems"]):
            return None
        item_rules = rules.get("items", {})
        items: list[Any] = []
        for item in value:
            checked = _validate_value(item, item_rules)
            if checked is None:
                return None
            items.append(checked)
        return items
    return None


def _http_complete(system: str, user: str) -> str:
    provider = config.LLM_PROVIDER.strip().lower()
    timeout = httpx.Timeout(config.LLM_TIMEOUT_SECONDS)
    if provider == "openai":
        return _openai(system, user, timeout)
    if provider == "anthropic":
        return _anthropic(system, user, timeout)
    if provider == "grok":
        return _grok(system, user, timeout)
    if provider == "groq":
        return _groq(system, user, timeout)
    raise RuntimeError("LLM provider is not supported.")


def _openai(system: str, user: str, timeout: httpx.Timeout) -> str:
    return _openai_compatible(
        system,
        user,
        timeout,
        url="https://api.openai.com/v1/chat/completions",
        api_key=config.LLM_API_KEY,
    )


def _grok(system: str, user: str, timeout: httpx.Timeout) -> str:
    return _openai_compatible(
        system,
        user,
        timeout,
        url="https://api.x.ai/v1/chat/completions",
        api_key=config.GROK_API_KEY,
    )


def _groq(system: str, user: str, timeout: httpx.Timeout) -> str:
    return _openai_compatible(
        system,
        user,
        timeout,
        url="https://api.groq.com/openai/v1/chat/completions",
        api_key=config.GROQ_API_KEY,
    )


def _openai_compatible(
    system: str,
    user: str,
    timeout: httpx.Timeout,
    *,
    url: str,
    api_key: str,
) -> str:
    headers = {"Authorization": f"Bearer {api_key}"}
    body = {
        "model": config.LLM_MODEL,
        "temperature": 0,
        "max_tokens": config.LLM_MAX_TOKENS,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()
    return str(payload["choices"][0]["message"]["content"])


def _anthropic(system: str, user: str, timeout: httpx.Timeout) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": config.LLM_API_KEY,
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": config.LLM_MODEL,
        "max_tokens": config.LLM_MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()
    return str(payload["content"][0]["text"])
