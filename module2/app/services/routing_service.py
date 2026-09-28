"""RoutingService: only place that knows about OpenRouteService.
Falls back to synthetic alternatives when ORS_API_KEY is unset (demo/offline)."""
import logging, math, uuid
import httpx
from app.config import settings
from app.services.geo import path_length

log = logging.getLogger("routing")
ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"

class RoutingService:
    def routes(self, start, end):
        """start/end: (lat, lon). Returns list of {id, geometry[[lat,lon]], distance_m, duration_s, source}."""
        if settings.ors_api_key:
            try:
                return self._ors(start, end)
            except Exception as e:
                log.warning("ORS failed (%s); using mock routes", e)
        return self._mock(start, end)

    def _ors(self, s, e):
        body = {"coordinates": [[s[1], s[0]], [e[1], e[0]]],
                "alternative_routes": {"target_count": 3, "share_factor": 0.6, "weight_factor": 1.6}}
        r = httpx.post(ORS_URL, json=body, headers={"Authorization": settings.ors_api_key}, timeout=20)
        r.raise_for_status()
        out = []
        for f in r.json()["features"][:3]:
            geom = [[c[1], c[0]] for c in f["geometry"]["coordinates"]]
            sm = f["properties"]["summary"]
            out.append(self._mk(geom, sm["distance"], sm["duration"], "ors"))
        return out

    def _mock(self, s, e):
        out = []
        dx, dy = e[1]-s[1], e[0]-s[0]
        for bulge, speed in ((0.0, 8.3), (0.2, 7.8), (-0.2, 7.8)):
            geom = []
            for i in range(41):
                t = i/40
                off = bulge*math.sqrt(math.sin(math.pi*t))
                geom.append([s[0]+dy*t + (-dx)*off, s[1]+dx*t + dy*off])
            d = path_length(geom)
            out.append(self._mk(geom, d, d/speed, "mock"))
        return out

    @staticmethod
    def _mk(geom, dist, dur, src):
        return {"id": uuid.uuid4().hex[:8], "geometry": geom, "distance_m": dist, "duration_s": dur, "source": src}
