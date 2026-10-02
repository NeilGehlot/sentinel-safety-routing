"""Keep live Overpass off for module2 tests unless a test patches the fetcher itself."""
import pytest


@pytest.fixture(autouse=True)
def _no_live_overpass(monkeypatch):
    import httpx
    from app.services import osm_route_factors

    def _blocked(query: str):
        _ = query
        raise httpx.TimeoutException("overpass disabled in tests")

    monkeypatch.setattr(osm_route_factors, "fetch_overpass_payload", _blocked)
    osm_route_factors.clear_cache()
    yield
    osm_route_factors.clear_cache()
