"""News risk from the retrieve stub.

A configured LLM may label the snippet. Distance and recency decay are applied
here, not by the model. A missing key, timeout, or bad JSON keeps the rule
that uses the highest stub severity. This module does not raise.
"""

import math

from cachetools import TTLCache

from app import config
from app.config import EARTH_RADIUS_M, NEWS_LOOKBACK_HOURS, NEWS_RADIUS_M
from app.llm import explain_mode, extract_news
from app.mocks.news_risk import NewsArticle
from app.news_retrieve import retrieve
from app.providers.base import SignalResult, clamp_risk, unavailable
from app.schemas import AssessRequest

_ARTICLE_CAP = 5
_ARTICLE_CACHE: TTLCache[str, dict] = TTLCache(maxsize=128, ttl=24 * 60 * 60)


def apply_decay(severity: float, hours_old: float, distance_m: float | None) -> float:
    """Scale a 0..1 severity by recency and, when known, distance. Both are code."""
    lookback = float(NEWS_LOOKBACK_HOURS)
    recency = 1.0 - (hours_old / lookback) if lookback > 0 else 0.0
    if recency < 0.0:
        recency = 0.0
    if distance_m is None:
        distance_factor = 1.0
    else:
        radius = float(NEWS_RADIUS_M)
        distance_factor = 1.0 - (float(distance_m) / radius) if radius > 0 else 0.0
        if distance_factor < 0.0:
            distance_factor = 0.0
    return clamp_risk(severity * recency * distance_factor)


def _distance_m(article: NewsArticle, lat: float, lon: float) -> float | None:
    if article.distance_m is not None:
        return float(article.distance_m)
    if article.lat is None or article.lon is None:
        return None
    return _haversine_m(lat, lon, article.lat, article.lon)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = EARTH_RADIUS_M
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    chord = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2.0) ** 2
    return 2.0 * radius * math.asin(min(1.0, math.sqrt(chord)))


def _rule(articles: list[NewsArticle]) -> SignalResult:
    """Highest stub severity, with no decay. This is the fallback."""
    try:
        severity = max(clamp_risk(article.severity) for article in articles)
    except Exception:
        return unavailable("news_risk", "News severity could not be read.")
    return SignalResult(
        name="news_risk",
        risk=severity,
        reason=f"the news stub severity is {severity:.2f}",
        available=True,
        details={"severity": severity},
    )


def _news_llm_allowed() -> bool:
    """News stays on the rule unless USE_LLM is on and this is not a live check.

    explain=llm spends its single model call on the summary and tips.
    A request with no explain flag is a live check and does not call the model.
    """
    mode = explain_mode()
    if not config.USE_LLM:
        return False
    if mode is None or mode == "" or mode == "llm":
        return False
    return True


def _from_model(articles: list[NewsArticle], lat: float, lon: float) -> SignalResult | None:
    """Decayed severity from cached labels. None keeps the rule."""
    if not _news_llm_allowed():
        return None
    best_risk = -1.0
    best_hours = 0.0
    kept = 0
    for article in articles:
        snippet = article.headline.strip()
        if not snippet:
            continue
        if kept >= _ARTICLE_CAP:
            break
        kept += 1
        parsed = _ARTICLE_CACHE.get(snippet)
        if parsed is None:
            parsed = extract_news(snippet)
            if parsed is None:
                return None
            _ARTICLE_CACHE[snippet] = parsed
        if parsed is None:
            return None
        distance = _distance_m(article, lat, lon)
        risk = apply_decay(float(parsed["severity_0_to_1"]), float(parsed["hours_old"]), distance)
        if risk > best_risk:
            best_risk = risk
            best_hours = float(parsed["hours_old"])
    if best_risk < 0.0:
        return None
    return SignalResult(
        name="news_risk",
        risk=best_risk,
        reason=f"the news severity is {best_risk:.2f} after distance and recency decay",
        available=True,
        details={"severity": best_risk, "hours_old": best_hours},
    )


def signal(request: AssessRequest) -> SignalResult:
    """Prefer a validated extraction. Otherwise the stub severity. Never raise."""
    try:
        location = request.location
        if location is None:
            return unavailable("news_risk", "Location is missing.")
        articles = retrieve(
            location.lat,
            location.lon,
            float(NEWS_RADIUS_M),
            float(NEWS_LOOKBACK_HOURS),
        )
    except Exception:
        return unavailable("news_risk", "News retrieve failed.")
    if articles is None:
        return unavailable("news_risk", "News retrieve returned nothing.")
    if not articles:
        return SignalResult(
            name="news_risk",
            risk=0.0,
            reason="the news stub returned no recent reports",
            available=True,
        )
    ruled = _rule(articles)
    try:
        modeled = _from_model(articles, location.lat, location.lon)
    except Exception:
        modeled = None
    if modeled is None:
        return ruled
    return modeled
