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
            "http_401",
        ),
        (
            httpx.HTTPStatusError(
                "rate limited",
                request=httpx.Request("POST", "https://api.groq.com"),
                response=httpx.Response(429),
            ),
            "http_429",
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
