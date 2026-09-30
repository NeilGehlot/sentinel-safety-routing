"""Reset in-engine session memory and the news stub between tests."""

import pytest

from app.engine import reset_session_memory
from app.llm import wire_complete
from app.news_retrieve import wire_retrieve
from app.providers.crime_risk import reset_model_cache
from app.providers.movement import reset_model_cache as reset_motion_cache
from app.providers.safe_places import clear_cache as clear_safe_place_cache
from app.providers.weather import clear_cache as clear_weather_cache


@pytest.fixture(autouse=True)
def _fresh_engine_state() -> None:
    reset_session_memory()
    wire_retrieve(None)
    wire_complete(None)
    clear_weather_cache()
    clear_safe_place_cache()
    reset_model_cache()
    reset_motion_cache()
