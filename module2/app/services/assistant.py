"""Provider-agnostic safety assistant owned entirely by Module 2."""

import json
import re
from typing import Any

import httpx

from app.config import settings

SYSTEM_PROMPT = (
    "You are a calm, concise safety assistant inside a personal-safety app. "
    "Answer the user's question first using the supplied situation. "
    "Never invent incidents, locations, statistics, or numeric scores. "
    "Never claim the user is being followed or attacked. "
    "If emergency_active is true, talk about SOS and guardian alerts, not route scores, unless the user asked about the route. "
    "help_on_the_way means guardians were emailed; this app does not dispatch police by itself. "
    "route_safety and factor scores are 0-100 (higher is safer). "
    "risk_score is SOS distress 0-100 (higher is more concerning). "
    "If a field is missing, say it is not available instead of guessing. "
    "Keep answers to 2-3 sentences unless the user asked for a specific length. "
    "Return only JSON with a single key: answer."
)
FALLBACK_ANSWER = (
    "I can't reach the assistant service right now. Your current risk level is shown "
    "on the dashboard - please rely on that and contact your guardians directly if "
    "you're concerned."
)
SUPPORTED_PROVIDERS = {"openai", "anthropic", "grok", "groq", "ollama"}
FORBIDDEN = ("follow", "attack")
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"
DEFAULT_OLLAMA_MODEL = "qwen3:4b"
DEFAULT_OLLAMA_CHAT_URL = "http://127.0.0.1:11434/v1/chat/completions"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 120.0
OLLAMA_ANSWER_PREFIX = '{"answer":"'
_ANSWER_VALUE = re.compile(r'\{\s*"answer"\s*:\s*"((?:\\.|[^"\\])*)"')


def _api_key(provider: str) -> str:
    if provider == "ollama":
        return settings.llm_api_key or "ollama"
    if provider == "grok":
        return settings.grok_api_key
    if provider == "groq":
        return settings.groq_api_key
    return settings.llm_api_key


def _requires_key(provider: str) -> bool:
    return provider != "ollama"


def provider_status() -> dict[str, Any]:
    provider = settings.llm_provider.strip().lower()
    supported = provider in SUPPORTED_PROVIDERS
    key_configured = True if not _requires_key(provider) else bool(_api_key(provider))
    return {
        "provider": provider or "unconfigured",
        "supported": supported,
        "mock_mode": settings.mock_mode,
        "model_configured": bool(_model(provider)),
        "key_configured": key_configured,
        "ready": (
            supported
            and not settings.mock_mode
            and bool(_model(provider))
            and key_configured
        ),
    }


_CLIENT_CONTEXT_KEYS = (
    "user_name",
    "safety_monitor_active",
    "sos_status",
    "risk_score",
    "risk_level",
    "destination_name",
    "origin",
    "route_safety",
    "route_factors",
    "eta_min",
    "distance_m",
    "progress_m",
    "journey_status",
    "incidents_ahead",
    "nearby_safe_places",
    "live_location_label",
    "navigation_active",
    "emergency_active",
    "sos_trigger",
    "email_status",
    "help_on_the_way",
    "guardian_count",
    "trigger_reasons",
)
_HELP_QUESTION = re.compile(
    r"\b(help|sos|guardian|police|coming|on the way|on-the-way|alerted|alert|rescue|emergency|contacted)\b",
    re.I,
)
_ROUTE_QUESTION = re.compile(
    r"\b(route|score|eta|destination|traffic|incident|safe place|lighting|crowd)\b",
    re.I,
)
_FACTOR_KEYS = (
    "lighting",
    "crowd",
    "traffic",
    "connectivity",
    "safe_locations",
    "historical_crime",
)


def compose_context(
    *,
    sos_journey_id: str | None = None,
    nav_journey_id: str | None = None,
    route_id: str | None = None,
    client: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge dashboard snapshot with live SOS/navigation store state."""
    from app.services import navigation_service as nav_svc
    from app.services import store

    ctx: dict[str, Any] = {}
    for key in _CLIENT_CONTEXT_KEYS:
        value = (client or {}).get(key)
        if value is not None:
            ctx[key] = value

    sos = store.sos_journeys.get(sos_journey_id) if sos_journey_id else None
    if sos:
        ctx["safety_monitor_active"] = True
        ctx["risk_score"] = sos.get("risk_score")
        ctx["risk_level"] = sos.get("risk_level")
        ctx["sos_status"] = sos.get("status")
        ctx["trigger_reasons"] = list(sos.get("trigger_reasons") or [])
        if sos.get("user_name"):
            ctx["user_name"] = sos.get("user_name")
        ctx["emergency_active"] = sos.get("status") == "EMERGENCY_ACTIVE"
        if sos.get("sos_trigger"):
            ctx["sos_trigger"] = sos.get("sos_trigger")
        if sos.get("email_status"):
            ctx["email_status"] = sos.get("email_status")
        if sos.get("guardian_count") is not None:
            ctx["guardian_count"] = sos.get("guardian_count")
        emergency = store.emergencies.get(sos.get("emergency_id")) if sos.get("emergency_id") else None
        if emergency:
            ctx["sos_trigger"] = emergency.get("trigger_type") or ctx.get("sos_trigger")
            ctx["emergency_reasons"] = list(emergency.get("trigger_reasons") or [])
            if emergency.get("status") == "ACTIVE":
                ctx["risk_score"] = emergency.get("risk_score")
                ctx["risk_level"] = emergency.get("risk_level")
        ctx["help_on_the_way"] = bool(
            ctx.get("emergency_active")
            and (sos.get("help_alerted") or ctx.get("email_status") == "sent")
        )

    profile = (store.guardian_settings or {}).get("emergency_profile") or {}
    if profile.get("name") and not ctx.get("user_name"):
        ctx["user_name"] = profile.get("name")

    nav = None
    if nav_journey_id and nav_journey_id in store.journeys:
        nav = nav_svc.status(nav_journey_id)

    rid = (nav or {}).get("route_id") or route_id
    route = store.routes.get(rid) if rid else None

    if nav:
        ctx["navigation_active"] = True
        ctx["route_safety"] = nav.get("safety")
        ctx["eta_min"] = nav.get("eta_min")
        ctx["distance_m"] = nav.get("distance_m")
        ctx["progress_m"] = nav.get("progress_m")
        ctx["journey_status"] = nav.get("status")
        ctx["current_position"] = nav.get("position")
        ctx["incidents_ahead"] = [
            {
                "title": item.get("title"),
                "type": item.get("type"),
                "distance_ahead_m": item.get("distance_ahead_m"),
                "eta_min": item.get("eta_min"),
            }
            for item in (nav.get("incidents_ahead") or [])[:5]
        ]
        factors = nav.get("factors") or {}
        ctx["route_factors"] = {key: factors[key] for key in _FACTOR_KEYS if key in factors}
    elif route:
        ctx.setdefault("navigation_active", False)
        ctx.setdefault("route_safety", route.get("safety"))
        ctx.setdefault("eta_min", route.get("eta_min"))
        ctx.setdefault("distance_m", route.get("distance_m"))
        ctx.setdefault("journey_status", ctx.get("journey_status") or "planned")
        factors = route.get("factors") or {}
        ctx.setdefault(
            "route_factors",
            {key: factors[key] for key in _FACTOR_KEYS if key in factors},
        )

    ctx["situation"] = _situation(ctx)
    ctx["score_guide"] = {
        "route_safety": "0-100, higher is safer",
        "risk_score": "0-100 SOS distress, higher is more concerning",
        "factors": "0-100, higher is safer",
    }
    return ctx


def _situation(ctx: dict[str, Any]) -> str:
    if ctx.get("sos_status") == "EMERGENCY_ACTIVE" or ctx.get("emergency_active"):
        trigger = str(ctx.get("sos_trigger") or "").upper()
        kind = "An automatic SOS is active" if trigger == "AUTO" else "A manual SOS is active" if trigger == "MANUAL" else "SOS is active"
        email_status = ctx.get("email_status")
        if email_status == "sent" or ctx.get("help_on_the_way"):
            alert = "Guardian alert emails were sent with the live location, so help has been requested."
        elif email_status == "partial":
            alert = "Some guardian alert emails were sent."
        else:
            alert = "Guardian emails were not sent. Use 112 from the emergency contacts if you can."
        dest = ctx.get("destination_name")
        place = f" The user was heading to {dest}." if dest else ""
        return f"{kind}. {alert}{place}"
    if ctx.get("safety_monitor_active"):
        score = ctx.get("risk_score")
        level = ctx.get("risk_level") or "LOW"
        dest = ctx.get("destination_name")
        route = ctx.get("route_safety")
        bits = [f"Safety monitor is on. SOS distress is {score}/100 ({level})."]
        if dest:
            bits.append(f"Destination is {dest}.")
        if route is not None:
            bits.append(f"Route safety is {route}/100.")
        return " ".join(bits)
    dest = ctx.get("destination_name")
    route = ctx.get("route_safety")
    if dest and route is not None:
        return f"No SOS is active. Planned route to {dest} has safety {route}/100."
    return "No SOS is active and no scored route is selected."


def _direct_answer(question: str, context: dict[str, Any]) -> str | None:
    emergency = context.get("sos_status") == "EMERGENCY_ACTIVE" or context.get("emergency_active")
    if not emergency or not _HELP_QUESTION.search(question):
        return None
    trigger = str(context.get("sos_trigger") or "").upper()
    kind = "automatic" if trigger == "AUTO" else "manual" if trigger == "MANUAL" else ""
    prefix = f"Yes. {kind.capitalize()} SOS is active" if kind else "Yes. SOS is active"
    if context.get("email_status") == "sent" or context.get("help_on_the_way"):
        count = context.get("guardian_count")
        who = f"{count} guardians" if count else "your guardians"
        return (
            f"{prefix} and alert emails were sent to {who} with your live location. "
            "Stay where you are if it is safe; they have been asked to come help. "
            "You can also call 112 from the emergency contacts on the dashboard."
        )
    if context.get("email_status") == "partial":
        return (
            f"{prefix}. At least one guardian alert was sent, but not every email succeeded. "
            "Call 112 from the dashboard if you can."
        )
    return (
        f"{prefix}, but guardian emails were not sent. "
        "Call 112 or a listed emergency contact from the dashboard now."
    )


def _context_for_model(question: str, context: dict[str, Any]) -> dict[str, Any]:
    emergency = context.get("sos_status") == "EMERGENCY_ACTIVE" or context.get("emergency_active")
    route_ask = bool(_ROUTE_QUESTION.search(question))
    payload = {
        "situation": context.get("situation"),
        "sos_status": context.get("sos_status"),
        "safety_monitor_active": context.get("safety_monitor_active"),
        "emergency_active": emergency,
        "help_on_the_way": context.get("help_on_the_way"),
        "sos_trigger": context.get("sos_trigger"),
        "email_status": context.get("email_status"),
        "guardian_count": context.get("guardian_count"),
        "user_name": context.get("user_name"),
        "destination_name": context.get("destination_name"),
        "risk_score": context.get("risk_score"),
        "risk_level": context.get("risk_level"),
        "trigger_reasons": context.get("emergency_reasons") or context.get("trigger_reasons"),
    }
    if (not emergency) or route_ask:
        payload.update(
            {
                "route_safety": context.get("route_safety"),
                "route_factors": context.get("route_factors"),
                "eta_min": context.get("eta_min"),
                "incidents_ahead": context.get("incidents_ahead"),
                "journey_status": context.get("journey_status"),
            }
        )
    if emergency:
        payload["nearby_safe_places"] = context.get("nearby_safe_places")
    return {key: value for key, value in payload.items() if value not in (None, [], {})}


def ask(question: str, context: dict[str, Any]) -> dict[str, str]:
    provider = settings.llm_provider.strip().lower()
    cleaned = question.strip()
    if not cleaned:
        return {"answer": FALLBACK_ANSWER, "provider_status": "empty_question"}

    direct = _direct_answer(cleaned, context)
    if direct:
        return {"answer": direct, "provider_status": "ok"}

    status = _preflight_status(provider, cleaned)
    if status is not None:
        return {"answer": FALLBACK_ANSWER, "provider_status": status}

    try:
        raw = _complete(provider, cleaned, _context_for_model(cleaned, context))
    except httpx.TimeoutException:
        return {"answer": FALLBACK_ANSWER, "provider_status": "timeout"}
    except httpx.HTTPStatusError as exc:
        return {"answer": FALLBACK_ANSWER, "provider_status": _http_error_status(exc)}
    except Exception:
        return {"answer": FALLBACK_ANSWER, "provider_status": "provider_error"}

    answer = _extract_answer(raw)
    if not answer:
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
    if _requires_key(provider) and not _api_key(provider):
        return "missing_key"
    if settings.mock_mode:
        return "mock_mode"
    return None


def _model(provider: str) -> str:
    if settings.llm_model:
        return settings.llm_model
    if provider == "groq":
        return DEFAULT_GROQ_MODEL
    if provider == "ollama":
        return DEFAULT_OLLAMA_MODEL
    return ""


def _timeout_seconds(provider: str) -> float:
    if provider == "ollama":
        return max(settings.llm_timeout_seconds, DEFAULT_OLLAMA_TIMEOUT_SECONDS)
    return settings.llm_timeout_seconds


def _chat_url(provider: str) -> str:
    if settings.llm_base_url:
        base = settings.llm_base_url.rstrip("/")
        return base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    defaults = {
        "openai": "https://api.openai.com/v1/chat/completions",
        "grok": "https://api.x.ai/v1/chat/completions",
        "groq": "https://api.groq.com/openai/v1/chat/completions",
        "ollama": DEFAULT_OLLAMA_CHAT_URL,
    }
    return defaults[provider]


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
        pass
    return f"http_{status}:{category}" if category else f"http_{status}"


def _complete(provider: str, question: str, context: dict[str, Any]) -> str:
    if provider == "anthropic":
        return _anthropic(question, context)
    return _openai_compatible(
        _chat_url(provider),
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
    if provider == "ollama":
        body["messages"].append({"role": "assistant", "content": OLLAMA_ANSWER_PREFIX})
    if provider not in {"groq", "ollama"}:
        body["response_format"] = {"type": "json_object"}
    with httpx.Client(timeout=_timeout_seconds(provider)) as client:
        response = client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
    message = payload["choices"][0]["message"]
    return _message_text(message)


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


def _message_text(message: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("content", "reasoning", "thinking", "reasoning_content"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    return _strip_think("\n".join(parts))


def _extract_answer(raw: str) -> str | None:
    text = _strip_think(raw or "")
    if not text.strip():
        return None
    candidates = [text]
    if not text.lstrip().startswith("{"):
        candidates.insert(0, OLLAMA_ANSWER_PREFIX + text)
    for candidate in candidates:
        match = _ANSWER_VALUE.search(candidate)
        if match:
            try:
                value = json.loads(f'"{match.group(1)}"')
            except json.JSONDecodeError:
                value = match.group(1)
            if isinstance(value, str) and value.strip():
                return value.strip()
        try:
            payload = _parse_json(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        answer = payload.get("answer") if isinstance(payload, dict) else None
        if isinstance(answer, str) and answer.strip():
            return answer.strip()
    stripped = text.strip()
    if stripped and not re.match(r"(okay|ok,|let's see|we are given|the user)", stripped, re.I):
        return stripped
    return None


def _strip_think(raw: str) -> str:
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()


def _parse_json(raw: str) -> object:
    text = _strip_think(raw.strip())
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)
