"""Mock news articles for the retrieve stub. These are not live reports."""

from dataclasses import dataclass

from app.config import NEWS_MOCK_SEVERITY


@dataclass(frozen=True)
class NewsArticle:
    """One stub article. severity is already on a 0..1 scale.

    distance_m, lat, and lon are optional facts for the decay code.
    The LLM does not compute them.
    """

    severity: float
    headline: str
    distance_m: float | None = None
    lat: float | None = None
    lon: float | None = None


def default_articles() -> list[NewsArticle]:
    """The offline stub. Headline text stays generic so the engine does not invent an incident."""
    return [
        NewsArticle(
            severity=NEWS_MOCK_SEVERITY,
            headline="Local report in the retrieve stub.",
        )
    ]
