"""
RoutingService

This is the only service that communicates with OpenRouteService.

Flow:

Frontend
   ↓
FastAPI
   ↓
RoutingService
   ↓
OpenRouteService
   ↓
Real road-following geometry

ORS is required for route geometry. Routing failures are surfaced
to the API caller instead of being replaced with synthetic routes.
"""

import logging
import uuid

import httpx

from app.config import settings
log = logging.getLogger("routing")


# ============================================================
# OPENROUTESERVICE
# ============================================================

ORS_URL = (
    "https://api.openrouteservice.org/"
    "v2/directions/driving-car/geojson"
)


class RoutingServiceError(RuntimeError):
    """Raised when OpenRouteService cannot provide usable routes."""


class RoutingService:
    """
    Provides route alternatives between two coordinates.

    Coordinates are represented internally as:

        (latitude, longitude)

    ORS expects:

        [longitude, latitude]
    """

    # --------------------------------------------------------
    # PUBLIC METHOD
    # --------------------------------------------------------

    def routes(self, start, end):
        """
        Parameters
        ----------
        start : tuple
            (latitude, longitude)

        end : tuple
            (latitude, longitude)

        Returns
        -------
        list
            List of route dictionaries.
        """

        if not settings.ors_api_key:
            raise RoutingServiceError(
                "OpenRouteService is not configured: ORS_API_KEY is missing"
            )

        try:
            routes = self._ors(start, end)
        except RoutingServiceError:
            raise
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300].strip()
            raise RoutingServiceError(
                "OpenRouteService returned "
                f"HTTP {exc.response.status_code}"
                f"{f': {detail}' if detail else ''}"
            ) from exc
        except httpx.RequestError as exc:
            raise RoutingServiceError(
                f"Could not reach OpenRouteService: {exc}"
            ) from exc
        except (TypeError, ValueError, KeyError) as exc:
            raise RoutingServiceError(
                "OpenRouteService returned an invalid route response"
            ) from exc

        if not routes:
            raise RoutingServiceError(
                "OpenRouteService returned no usable routes"
            )

        log.info("ORS returned %d real route(s)", len(routes))
        return routes

    # --------------------------------------------------------
    # REAL ORS ROUTING
    # --------------------------------------------------------

    def _ors(self, start, end):
        """
        Request real road-following routes from ORS.
        """

        start_lat, start_lon = start
        end_lat, end_lon = end

        # ORS requires [longitude, latitude]
        body = {
            "coordinates": [
                [start_lon, start_lat],
                [end_lon, end_lat],
            ],

            "alternative_routes": {
                "target_count": 3,
                "share_factor": 0.6,
                "weight_factor": 1.6,
            },
        }

        headers = {
            "Authorization": settings.ors_api_key,
            "Content-Type": "application/json",
        }

        response = httpx.post(
            ORS_URL,
            json=body,
            headers=headers,
            timeout=20,
        )

        # Raise an exception for 4xx / 5xx responses
        response.raise_for_status()

        data = response.json()

        features = data.get("features", [])

        if not features:
            return []

        routes = []

        for feature in features[:3]:

            geometry = feature.get("geometry", {})
            coordinates = geometry.get("coordinates", [])

            if not coordinates:
                continue

            # ORS returns:
            #
            # [longitude, latitude]
            #
            # Sentinel uses:
            #
            # [latitude, longitude]

            geom = [[coordinate[1], coordinate[0]] for coordinate in coordinates]

            properties = feature.get(
                "properties",
                {}
            )

            summary = properties.get(
                "summary",
                {}
            )

            distance_m = float(
                summary.get("distance", 0)
            )

            duration_s = float(
                summary.get("duration", 0)
            )

            routes.append(
                self._mk(
                    geom=geom,
                    dist=distance_m,
                    dur=duration_s,
                    src="ors",
                )
            )

        return routes

    # --------------------------------------------------------
    # ROUTE OBJECT CREATOR
    # --------------------------------------------------------

    @staticmethod
    def _mk(geom, dist, dur, src):
        """
        Create the standard Sentinel route object.
        """

        return {
            "id": uuid.uuid4().hex[:8],

            "geometry": geom,

            "distance_m": float(dist),

            "duration_s": float(dur),

            "source": src,
        }