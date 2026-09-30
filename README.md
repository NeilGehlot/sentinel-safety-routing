# SENTINEL – Module 2: Safe Route Search & Predictive Adaptive Rerouting

Scores 2–3 routes for safety, recommends the safest, then monitors the active journey and proposes a safer reroute when an incident ahead makes the current route significantly worse. The user always decides.

## Run
```bash
cd module2 && pip install -r requirements.txt && cp .env.example .env
uvicorn app.main:app --reload          # http://localhost:8000/docs
cd frontend && npm install && npm run dev
```
Env vars: see `module2/.env.example` (export them or use your shell; `ORS_API_KEY` is required for real road-following routes). Frontend poll: `VITE_POLLING_INTERVAL_SECONDS` (default 10).

## Demo
Search → pick route → **START ROUTE** → **Demo: inject accident 600 m ahead** → reroute card → Switch. ORS connectivity and an API key are required for route search.
Journey movement is simulated (`SIM_SPEED`, default 2×).

## Tests
`cd module2 && pytest`

## Status
Implemented: P0 flow, temporal decay, source confidence, Module 1 mock client, Module 3 endpoints. Not yet implemented: SQLite persistence (in-memory store), RSS/GDELT sources, RAG, Tailwind, geocoding search (preset destinations), real safety datasets (factors are deterministic placeholders). See docs/.
