import json
import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services import assistant

client = TestClient(app)


def configure_groq(monkeypatch, *, key="groq-key", mock_mode=False):
    monkeypatch.setattr(settings, "llm_provider", "GrOq")
    monkeypatch.setattr(settings, "llm_model", "groq-model")
    monkeypatch.setattr(settings, "groq_api_key", key)
    monkeypatch.setattr(settings, "mock_mode", mock_mode)


def test_offline_fallback(monkeypatch):
    configure_groq(monkeypatch, mock_mode=True)
    response = client.post("/assistant/ask", json={"question": "What is my risk?"})
    assert response.status_code == 200
    assert response.json()["provider_status"] == "mock_mode"
    assert "current risk level" in response.json()["answer"]


def test_groq_success_request(monkeypatch):
    configure_groq(monkeypatch)
    request = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"answer":"Use the displayed risk score."}'}}]}

    class FakeClient:
        def __init__(self, timeout):
            request["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, headers, json):
            request.update(url=url, headers=headers, json=json)
            return FakeResponse()

    monkeypatch.setattr(assistant.httpx, "Client", FakeClient)
    response = client.post("/assistant/ask", json={"question": "What is my risk?"})
    assert response.json() == {
        "answer": "Use the displayed risk score.",
        "provider_status": "ok",
    }
    assert request["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert request["headers"] == {"Authorization": "Bearer groq-key"}
    assert request["json"]["model"] == "groq-model"
    assert request["json"]["messages"][1]["role"] == "user"
    assert "response_format" not in request["json"]


def test_missing_groq_key_falls_back_without_network(monkeypatch):
    configure_groq(monkeypatch, key="")
    monkeypatch.setattr(
        assistant.httpx,
        "Client",
        lambda *args, **kwargs: pytest.fail("Missing key must not open a client"),
    )
    response = client.post("/assistant/ask", json={"question": "What is my risk?"})
    assert response.json()["provider_status"] == "missing_key"


@pytest.mark.parametrize(
    ("failure", "category"),
    [
        (httpx.TimeoutException("timed out"), "timeout"),
        (
            httpx.HTTPStatusError(
                "unauthorized",
                request=httpx.Request("POST", "https://api.groq.com"),
                response=httpx.Response(401),
            ),
            "http_401:authentication",
        ),
        (
            httpx.HTTPStatusError(
                "rate limited",
                request=httpx.Request("POST", "https://api.groq.com"),
                response=httpx.Response(429),
            ),
            "http_429:rate_limited",
        ),
    ],
)
def test_safe_provider_failure_status(monkeypatch, failure, category):
    configure_groq(monkeypatch)
    monkeypatch.setattr(assistant, "_complete", lambda *args: (_ for _ in ()).throw(failure))
    response = client.post("/assistant/ask", json={"question": "What is my risk?"})
    assert response.status_code == 200
    assert response.json()["provider_status"] == category
    assert "groq-key" not in response.text


def test_assistant_status_is_safe(monkeypatch):
    configure_groq(monkeypatch)
    response = client.get("/assistant/status")
    assert response.json() == {
        "provider": "groq",
        "supported": True,
        "mock_mode": False,
        "model_configured": True,
        "key_configured": True,
        "ready": True,
    }
    assert "groq-key" not in response.text
    assert "groq-model" not in response.text


def test_groq_404_model_error_is_informative(monkeypatch):
    configure_groq(monkeypatch)
    failure = httpx.HTTPStatusError(
        "not found",
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
        response=httpx.Response(
            404,
            request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
            json={"error": {"message": "The requested model does not exist."}},
        ),
    )
    monkeypatch.setattr(assistant, "_complete", lambda *args: (_ for _ in ()).throw(failure))
    response = client.post("/assistant/ask", json={"question": "What is my risk?"})
    assert response.json()["provider_status"] == "http_404:model_not_found"
    assert "groq-key" not in response.text


def configure_ollama(monkeypatch, *, mock_mode=False, model="qwen3:4b", base_url=""):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_model", model)
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_base_url", base_url)
    monkeypatch.setattr(settings, "mock_mode", mock_mode)


def test_ollama_success_request(monkeypatch):
    configure_ollama(monkeypatch)
    request = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": 'Use the displayed risk score."}\nBut the user asked about risk',
                            "reasoning": "",
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, timeout):
            request["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, headers, json):
            request.update(url=url, headers=headers, json=json)
            return FakeResponse()

    monkeypatch.setattr(assistant.httpx, "Client", FakeClient)
    response = client.post("/assistant/ask", json={"question": "What is my risk?"})
    assert response.json() == {
        "answer": "Use the displayed risk score.",
        "provider_status": "ok",
    }
    assert request["url"] == "http://127.0.0.1:11434/v1/chat/completions"
    assert request["headers"] == {"Authorization": "Bearer ollama"}
    assert request["json"]["model"] == "qwen3:4b"
    assert request["json"]["messages"][-1] == {
        "role": "assistant",
        "content": assistant.OLLAMA_ANSWER_PREFIX,
    }
    assert "think" not in request["json"]
    assert "response_format" not in request["json"]
    assert request["timeout"] == assistant.DEFAULT_OLLAMA_TIMEOUT_SECONDS


def test_ollama_uses_reasoning_when_content_is_empty(monkeypatch):
    configure_ollama(monkeypatch)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "reasoning": '{"answer":"Use the displayed risk score."}',
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, headers, json):
            return FakeResponse()

    monkeypatch.setattr(assistant.httpx, "Client", FakeClient)
    response = client.post("/assistant/ask", json={"question": "What is my risk?"})
    assert response.json() == {
        "answer": "Use the displayed risk score.",
        "provider_status": "ok",
    }


def test_ollama_status_does_not_require_a_key(monkeypatch):
    configure_ollama(monkeypatch, model="")
    response = client.get("/assistant/status")
    assert response.json() == {
        "provider": "ollama",
        "supported": True,
        "mock_mode": False,
        "model_configured": True,
        "key_configured": True,
        "ready": True,
    }


def test_groq_default_model_and_plain_text_response(monkeypatch):
    configure_groq(monkeypatch)
    monkeypatch.setattr(settings, "llm_model", "")
    monkeypatch.setattr(assistant, "_complete", lambda *args: "Use the displayed risk score.")
    response = client.post("/assistant/ask", json={"question": "What is my risk?"})
    assert response.json() == {
        "answer": "Use the displayed risk score.",
        "provider_status": "ok",
    }
    assert assistant._model("groq") == "llama-3.1-8b-instant"


def test_assistant_sends_dashboard_context(monkeypatch):
    configure_groq(monkeypatch)
    request = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"answer":"Your Amber Fort route is 81/100."}'}}]}

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, headers, json):
            request.update(json=json)
            return FakeResponse()

    monkeypatch.setattr(assistant.httpx, "Client", FakeClient)
    from app.services import store

    store.sos_journeys["sos1"] = {
        "journey_id": "sos1",
        "status": "JOURNEY_ACTIVE",
        "risk_score": 12,
        "risk_level": "LOW",
        "trigger_reasons": [],
        "user_name": "Dev",
    }
    store.routes["r1"] = {
        "id": "r1",
        "safety": 81.2,
        "eta_min": 18.5,
        "distance_m": 4200,
        "factors": {"lighting": 70, "crowd": 60},
    }
    try:
        response = client.post(
            "/assistant/ask",
            json={
                "question": "Is my route safe?",
                "journey_id": "sos1",
                "route_id": "r1",
                "context": {"destination_name": "Amber Fort"},
            },
        )
    finally:
        store.sos_journeys.pop("sos1", None)
        store.routes.pop("r1", None)

    assert response.json()["provider_status"] == "ok"
    payload = json.loads(request["json"]["messages"][1]["content"])
    assert payload["question"] == "Is my route safe?"
    assert payload["context"]["destination_name"] == "Amber Fort"
    assert payload["context"]["route_safety"] == 81.2
    assert payload["context"]["risk_score"] == 12
    assert payload["context"]["user_name"] == "Dev"
    assert payload["context"]["safety_monitor_active"] is True


def test_help_question_during_sos_answers_without_llm(monkeypatch):
    configure_groq(monkeypatch)
    monkeypatch.setattr(
        assistant.httpx,
        "Client",
        lambda *args, **kwargs: pytest.fail("SOS help questions must not call the model"),
    )
    from app.services import store

    store.sos_journeys["sos1"] = {
        "journey_id": "sos1",
        "status": "EMERGENCY_ACTIVE",
        "emergency_id": "e1",
        "email_status": "sent",
        "help_alerted": True,
        "guardian_count": 2,
        "sos_trigger": "AUTO",
        "risk_score": 0,
        "risk_level": "LOW",
        "trigger_reasons": ["SOS ACTIVATED"],
        "user_name": "Dev",
    }
    store.emergencies["e1"] = {
        "id": "e1",
        "trigger_type": "AUTO",
        "status": "ACTIVE",
        "risk_score": 70,
        "risk_level": "HIGH",
        "trigger_reasons": ["No response to safety countdown"],
    }
    store.routes["r1"] = {
        "id": "r1",
        "safety": 67.4,
        "eta_min": 24,
        "distance_m": 26300,
        "factors": {"traffic": 40},
    }
    try:
        response = client.post(
            "/assistant/ask",
            json={
                "question": "is help on the way?",
                "journey_id": "sos1",
                "route_id": "r1",
                "context": {"destination_name": "Hawa Mahal", "route_safety": 67.4},
            },
        )
    finally:
        store.sos_journeys.pop("sos1", None)
        store.emergencies.pop("e1", None)
        store.routes.pop("r1", None)

    body = response.json()
    assert body["provider_status"] == "ok"
    answer = body["answer"].lower()
    assert "guardian" in answer
    assert "automatic" in answer
    assert "traffic" not in answer
    assert "67.4" not in body["answer"]
