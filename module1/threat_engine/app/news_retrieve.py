"""News retrieve stub. Phase 2 returns mock articles and does not call an LLM."""

from collections.abc import Callable

from app.mocks.news_risk import NewsArticle, default_articles

RetrieveFn = Callable[[float, float, float, float], list[NewsArticle] | None]


def _default_retrieve(lat: float, lon: float, radius_m: float, hours: float) -> list[NewsArticle]:
    _ = (lat, lon, radius_m, hours)
    return default_articles()


_retrieve: RetrieveFn = _default_retrieve


def wire_retrieve(fn: RetrieveFn | None) -> None:
    """Tests replace the stub. None restores the default mock articles."""
    global _retrieve
    _retrieve = fn if fn is not None else _default_retrieve


def retrieve(lat: float, lon: float, radius_m: float, hours: float) -> list[NewsArticle] | None:
    """Return mock articles, or whatever the current stub returns."""
    return _retrieve(lat, lon, radius_m, hours)
