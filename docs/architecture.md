# Architecture
React (Leaflet) -> FastAPI `api/` (thin) -> `services/`:
`routing_service` (HeiGIT/OpenRouteService road geometry) · `route_matcher` (Shapely distance, along-route position, ETA, temporal decay, impact) · `route_scorer` (weighted factors, incident penalty; Module 1 score can become a factor) · `rerouting_service` (deterministic policy) · `navigation_service` (journey simulation) · `store` (in-memory; incident sources).
Impact = severity × (1 − dist/radius) × exp(−age/decay) × confidence. Reroute only if safety < CRITICAL_SAFETY_THRESHOLD AND improvement ≥ MIN_SAFETY_IMPROVEMENT AND extra ETA ≤ MAX_EXTRA_TRAVEL_MINUTES. The user always confirms.
