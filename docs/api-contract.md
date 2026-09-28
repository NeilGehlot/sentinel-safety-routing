# Module 2 API contract (Swagger: http://localhost:8000/docs)

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | /api/routes/search | `{start:{latitude,longitude}, destination:{...}}` | `{routes:[{id,geometry,distance_m,eta_min,safety,factors,incident_count,recommended}], module1_threat}` |
| POST | /api/navigation/start | `{route_id}` | `{journey_id}` |
| GET | /api/navigation/{id}/status | – | position, eta_min, safety, status (`on_track`/`incident_ahead`/`reroute_recommended`/`completed`), incidents_ahead, next_checkpoint, `reroute` (alternative, reasons, improvement, extra_minutes) or null |
| POST | /api/navigation/{id}/switch | `{alternative_route_id}` | new status |
| POST | /api/navigation/{id}/dismiss | – | `{ok}` (keep current route) |
| POST | /api/routes/recalculate | `{journey_id}` | status |
| GET | /api/incidents/recent | – | `Incident[]` |
| POST | /api/incidents/report | `{type,title,latitude,longitude,severity}` | `Incident` |
| POST | /api/demo/inject-incident | `{journey_id, ahead_meters=600, severity=0.9}` | `Incident` (needs DEMO_MODE=true) |
| GET | /api/navigation/{id}/location | – | Module 3: current position |
| GET | /api/navigation/{id}/route-context | – | Module 3: position, route, incidents ahead |
