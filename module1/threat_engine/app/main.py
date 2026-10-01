"""FastAPI application for the threat assessment engine.

Routes are GET /v1/health and POST /v1/assess.
The page at / is static files on the same origin.
The assess route scores with the rule-based core and projects 5 and 10 minute scores.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from app.config import MOCK_MODE
from app.engine import assess
from app.llm import answer_assistant_question, bind_explain, reset_explain
from app.schemas import AssistantRequest, AssistantResponse, AssessRequest, AssessResponse, HealthResponse

_STATIC = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    """Build the ASGI app and load configuration at startup."""
    application = FastAPI(
        title="AI Threat Assessment Engine",
        version="0.1.0",
    )
    application.state.mock_mode = MOCK_MODE

    @application.get("/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @application.post("/v1/assistant", response_model=AssistantResponse)
    def assistant_endpoint(body: AssistantRequest) -> AssistantResponse:
        context = {
            "risk_score": body.risk_score,
            "risk_level": body.risk_level,
            "route_safety": body.route_safety,
            "nearby_safe_places": body.nearby_safe_places,
        }
        answer = answer_assistant_question(body.question, context)
        if answer is None:
            answer = (
                "I can't reach the assistant service right now. Your current risk level is shown "
                "on the dashboard - please rely on that and contact your guardians directly if "
                "you're concerned."
            )
        return AssistantResponse(answer=answer)

    @application.post("/v1/assess", response_model=AssessResponse)
    async def assess_endpoint(
        body: AssessRequest,
        explain: str | None = Query(default=None),
    ) -> AssessResponse:
        token = bind_explain(explain)
        try:
            return await assess(body)
        finally:
            reset_explain(token)

    @application.api_route(
        "/v1/{rest:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
    )
    def unknown_api(rest: str) -> None:
        """Unknown API paths stay missing. The page mount does not answer them."""
        _ = rest
        raise HTTPException(status_code=404)

    application.mount("/", StaticFiles(directory=_STATIC, html=True), name="ui")
    return application


app = create_app()
