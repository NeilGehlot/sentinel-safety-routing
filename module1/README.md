# Module 1: AI Threat Assessment Engine

Phase 7 of the threat assessment engine. `POST /v1/assess` scores a snapshot with the rule-based core and fills `predicted` with a 5 minute score and a 10 minute score. Those scores are a projection along the current speed and heading, not a forecast. When `MOCK_MODE` is not true, weather comes from Open-Meteo and the nearest safe place comes from OSM Overpass. Crime risk uses a LightGBM artifact when that file loads, and the synthetic grid when it does not. Movement uses a random forest when a window is present and that artifact loads, and the existing rules otherwise. An LLM may phrase news severity and the explanation when `LLM_PROVIDER`, `LLM_MODEL`, and `LLM_API_KEY` are set. It does not change the numeric score or the contributor points. The page is `GET /`. The API routes stay `POST /v1/assess` and `GET /v1/health`.

The contract is [MODULE1_FINAL_SPEC.md](MODULE1_FINAL_SPEC.md).

## Requirements

- Python 3.11 or newer
- Packages in `pyproject.toml`: FastAPI, Pydantic v2, uvicorn, httpx, cachetools, pytest, pytest-asyncio

## Setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

`MOCK_MODE` defaults to `true`, which keeps weather, safe places, crime risk, movement, and the LLM offline. Crime risk then reads the synthetic grid. Movement then uses the activity label or the accelerometer rule. `sudden_stop` still comes from a speed drop between requests. News and the explanation stay on their rule-based text when the LLM key is missing, the call times out, or the JSON does not match the schema. Set `MOCK_MODE=false` to call Open-Meteo and Overpass, to score crime risk with `threat_engine/ml/artifacts/crime_risk.txt` when that artifact loads, and to classify an accelerometer window with `threat_engine/ml/artifacts/motion.joblib` when that artifact loads. A missing or unreadable artifact falls back and does not raise. With `MOCK_MODE=false` and `LLM_PROVIDER`, `LLM_MODEL`, and `LLM_API_KEY` set, the client calls OpenAI or Anthropic with a timeout. No key means no call. Crime training is under `threat_engine/ml/crime_risk/`. It is trained on Los Angeles data to demonstrate the method, with city-agnostic features, and is ready for local police data. Gurugram output is illustrative, not validated. Movement training is under `threat_engine/ml/motion/`. Place density stays on its offline rule. The URLs and LLM names are in `.env.example`.

## Run locally

```bash
cd threat_engine
MOCK_MODE=true uvicorn app.main:app --host 127.0.0.1 --port 8741
```

Health check:

```bash
curl http://127.0.0.1:8741/v1/health
```

Expected body: `{"status":"ok"}`.

The section 5 sample, from `threat_engine/`:

```bash
curl -s -X POST http://127.0.0.1:8741/v1/assess \
  -H 'content-type: application/json' \
  -d '{"session_id":"abc","timestamp":"2026-09-29T23:40:00+05:30","location":{"lat":28.4595,"lon":77.0266,"speed_mps":1.4,"heading_deg":90},"device":{"battery_pct":18,"cellular_dbm":-108,"internet_available":false},"nearby_devices":{"ble_count":3,"wifi_count":2},"movement":{"accel_window":[[0.1,9.8,0.3]],"sampling_hz":50}}'
```

The response uses the section 5 fields. `current_score` is the clamped rule-based score. `predicted` lists a 5 minute score and a 10 minute score. Those are a projection along the current speed and heading, not a forecast. Contributor points sum to the current score before that clamp.

Routes: `GET /` (the page), `GET /v1/health`, and `POST /v1/assess`.

The page is served by the same process. The UI addendum uses port 8000. Port 8741 serves the same page when the server is started that way.

```bash
cd threat_engine
MOCK_MODE=true uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/. Details are in [MODULE1_UI_ADDENDUM.md](MODULE1_UI_ADDENDUM.md).

## Tests

From the repository root, with the virtualenv active:

```bash
pytest
```

The suite checks schema validation, health, each provider's 0..1 range, missing-data fallbacks, weight renormalization, and the contributor-point invariant.
