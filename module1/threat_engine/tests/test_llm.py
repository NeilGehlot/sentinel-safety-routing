"""LLM phrasing falls back to the rules. These tests never open a network call."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config
from app.config import NEWS_MOCK_SEVERITY
from app.engine import assess, reset_session_memory
from app.explain import ExplainContext, explain
from app import llm
from app.llm import wire_complete
from app.main import app
from app.providers import news_risk
from app.providers.news_risk import apply_decay
from app.schemas import AssessRequest, Contributor

SAMPLE = AssessRequest.model_validate(
    {
        "session_id": "abc",
        "timestamp": "2026-09-29T23:40:00+05:30",
        "location": {"lat": 28.4595, "lon": 77.0266, "speed_mps": 1.4, "heading_deg": 90},
        "device": {"battery_pct": 18, "cellular_dbm": -108, "internet_available": False},
        "nearby_devices": {"ble_count": 3, "wifi_count": 2},
        "movement": {"accel_window": [[0.1, 9.8, 0.3]], "sampling_hz": 50},
    }
)


def _enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "LLM_MODEL", "fake-model")
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")


def _matching_news() -> str:
    return json.dumps(
        {
            "incident_type": "report",
            "severity_0_to_1": NEWS_MOCK_SEVERITY,
            "location_text": "",
            "hours_old": 0,
        }
    )


def _matching_explanation() -> str:
    return json.dumps(
        {
            "summary": "Your score uses only the supplied signals.",
            "recommendations": ["Your battery is at 18%. Consider enabling battery saver."],
        }
    )


def _fake_ok(system: str, user: str) -> str:
    _ = user
    if system.startswith("Extract"):
        return _matching_news()
    return _matching_explanation()


def test_decay_is_applied_in_code() -> None:
    assert apply_decay(1.0, 0.0, None) == pytest.approx(1.0)
    assert apply_decay(1.0, 48.0, None) == pytest.approx(0.0)
    assert apply_decay(1.0, 0.0, 1000.0) == pytest.approx(0.0)
    assert apply_decay(0.8, 24.0, None) == pytest.approx(0.4)


def test_missing_key_uses_the_rule_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    called = False

    def _should_not_run(system: str, user: str) -> str:
        nonlocal called
        _ = (system, user)
        called = True
        return _matching_news()

    wire_complete(_should_not_run)
    result = news_risk.signal(SAMPLE)
    assert called is False
    assert result.risk == pytest.approx(NEWS_MOCK_SEVERITY)
    assert result.reason == f"the news stub severity is {NEWS_MOCK_SEVERITY:.2f}"
    _explanation, recommendations = explain(
        40,
        [Contributor(signal="news_risk", points=5, reason=result.reason)],
        ExplainContext(battery_pct=18),
    )
    assert "18%" in " ".join(recommendations)
    assert "supplied signals" not in _explanation.summary


def test_invalid_json_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)

    def _bad(system: str, user: str) -> str:
        _ = (system, user)
        return "this is not json"

    wire_complete(_bad)
    result = news_risk.signal(SAMPLE)
    assert result.risk == pytest.approx(NEWS_MOCK_SEVERITY)
    assert "stub severity" in result.reason
    summary, recommendations = explain(
        40,
        [Contributor(signal="news_risk", points=5, reason=result.reason)],
        ExplainContext(battery_pct=18),
    )
    assert "stub severity" in summary.summary
    assert any("18%" in item for item in recommendations)


def test_timeout_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)

    def _timeout(system: str, user: str) -> str:
        _ = (system, user)
        raise httpx.TimeoutException("timed out")

    wire_complete(_timeout)
    result = news_risk.signal(SAMPLE)
    assert result.risk == pytest.approx(NEWS_MOCK_SEVERITY)
    summary, _recommendations = explain(
        40,
        [Contributor(signal="news_risk", points=5, reason=result.reason)],
        ExplainContext(),
    )
    assert "stub severity" in summary.summary


def test_grok_provider_dispatch_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_PROVIDER", "GrOk")
    monkeypatch.setattr(config, "LLM_MODEL", "grok-test")
    monkeypatch.setattr(config, "GROK_API_KEY", "grok-key")
    called = []
    monkeypatch.setattr(llm, "_grok", lambda system, user, timeout: called.append((system, user, timeout)) or "ok")

    assert llm._http_complete("system", "user") == "ok"
    assert called[0][0:2] == ("system", "user")


def test_grok_uses_xai_chat_completions_request(monkeypatch: pytest.MonkeyPatch) -> None:
    request = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": '{"answer":"Stay calm."}'}}]}

    class FakeClient:
        def __init__(self, timeout) -> None:
            request["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def post(self, url, headers, json):
            request.update(url=url, headers=headers, json=json)
            return FakeResponse()

    monkeypatch.setattr(config, "LLM_MODEL", "grok-test")
    monkeypatch.setattr(config, "GROK_API_KEY", "grok-key")
    monkeypatch.setattr(llm.httpx, "Client", FakeClient)

    result = llm._grok("system", "user", httpx.Timeout(8))
    assert result == '{"answer":"Stay calm."}'
    assert request["url"] == "https://api.x.ai/v1/chat/completions"
    assert request["headers"] == {"Authorization": "Bearer grok-key"}
    assert request["json"]["model"] == "grok-test"
    assert request["json"]["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "user"},
    ]


def test_grok_missing_key_uses_assistant_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_PROVIDER", "grok")
    monkeypatch.setattr(config, "LLM_MODEL", "grok-test")
    monkeypatch.setattr(config, "GROK_API_KEY", "")
    monkeypatch.setattr(config, "LLM_API_KEY", "openai-key-is-not-used")
    monkeypatch.setattr(config, "MOCK_MODE", False)
    monkeypatch.setattr(
        llm.httpx,
        "Client",
        lambda *args, **kwargs: pytest.fail("Missing Grok key must not open a network client"),
    )

    response = TestClient(app).post(
        "/v1/assistant",
        json={"question": "What is my risk?", "risk_score": 40},
    )
    assert response.status_code == 200
    assert response.json()["answer"].startswith("I can't reach the assistant service right now.")


def test_groq_provider_dispatch_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_PROVIDER", "GrOq")
    monkeypatch.setattr(config, "LLM_MODEL", "groq-test")
    monkeypatch.setattr(config, "GROQ_API_KEY", "groq-key")
    called = []
    monkeypatch.setattr(llm, "_groq", lambda system, user, timeout: called.append((system, user, timeout)) or "ok")

    assert llm._http_complete("system", "user") == "ok"
    assert called[0][0:2] == ("system", "user")


def test_groq_uses_chat_completions_request(monkeypatch: pytest.MonkeyPatch) -> None:
    request = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": '{"answer":"Stay calm."}'}}]}

    class FakeClient:
        def __init__(self, timeout) -> None:
            request["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def post(self, url, headers, json):
            request.update(url=url, headers=headers, json=json)
            return FakeResponse()

    monkeypatch.setattr(config, "LLM_MODEL", "groq-test")
    monkeypatch.setattr(config, "GROQ_API_KEY", "groq-key")
    monkeypatch.setattr(llm.httpx, "Client", FakeClient)

    result = llm._groq("system", "user", httpx.Timeout(8))
    assert result == '{"answer":"Stay calm."}'
    assert request["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert request["headers"] == {"Authorization": "Bearer groq-key"}
    assert request["json"]["model"] == "groq-test"
    assert request["json"]["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "user"},
    ]


def test_groq_missing_key_uses_assistant_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_PROVIDER", "groq")
    monkeypatch.setattr(config, "LLM_MODEL", "groq-test")
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    monkeypatch.setattr(config, "LLM_API_KEY", "openai-key-is-not-used")
    monkeypatch.setattr(config, "MOCK_MODE", False)
    monkeypatch.setattr(
        llm.httpx,
        "Client",
        lambda *args, **kwargs: pytest.fail("Missing Groq key must not open a network client"),
    )

    response = TestClient(app).post(
        "/v1/assistant",
        json={"question": "What is my risk?", "risk_score": 40},
    )
    assert response.status_code == 200
    assert response.json()["answer"].startswith("I can't reach the assistant service right now.")


def test_forbidden_claim_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)

    def _claim(system: str, user: str) -> str:
        _ = user
        if system.startswith("Extract"):
            return _matching_news()
        return json.dumps(
            {
                "summary": "You are being attacked.",
                "recommendations": ["Someone is following you."],
            }
        )

    wire_complete(_claim)
    summary, recommendations = explain(
        40,
        [Contributor(signal="news_risk", points=5, reason="the news stub severity is 0.45")],
        ExplainContext(battery_pct=18),
    )
    text = summary.summary + " ".join(recommendations)
    assert "attack" not in text.lower()
    assert "follow" not in text.lower()


@pytest.mark.asyncio
async def test_numeric_score_is_identical_with_the_llm_on_or_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    off = await assess(SAMPLE)
    reset_session_memory()
    _enable(monkeypatch)
    wire_complete(_fake_ok)
    on = await assess(SAMPLE)
    assert on.current_score == off.current_score
    assert [(item.horizon_min, item.score) for item in on.predicted] == [
        (item.horizon_min, item.score) for item in off.predicted
    ]
    assert [(item.signal, item.points) for item in on.explanation.contributors] == [
        (item.signal, item.points) for item in off.explanation.contributors
    ]
    assert on.explanation.summary != off.explanation.summary
    assert "supplied signals" in on.explanation.summary
