# Module 3 : AI Threat Assessment Engine

The threat assessment engine. `POST /v1/assess` scores a snapshot with the rule-based core and fills `predicted` with a 5 minute score and a 10 minute score. Those scores are a projection along the current speed and heading, not a forecast. A lower score is safer. When `MOCK_MODE` is not true, weather comes from Open-Meteo and the nearest safe place comes from OSM Overpass. Crime risk uses a LightGBM artifact when that file loads. Movement uses a random forest when a window is present and that artifact loads, and the existing rules otherwise. An LLM may phrase news severity and the explanation when `LLM_PROVIDER`, `LLM_MODEL`, and `LLM_API_KEY` are set. It does not change the numeric score or the contributor points. The page is `GET /`. The API routes stay `POST /v1/assess` and `GET /v1/health`.


## Requirements

- Python 3.11
- Packages in `module1/pyproject.toml`: FastAPI, Pydantic v2, uvicorn, httpx, cachetools, pandas, numpy, lightgbm, scikit-learn, shap. Dev extra: pytest, pytest-asyncio

## Run locally (Windows PowerShell)

From the cloned repository:

```powershell
cd module1
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cd threat_engine
$env:MOCK_MODE = "true"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8741
```

If `Activate.ps1` is blocked by execution policy, run this once, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

`MOCK_MODE=true` is the offline default path. It does not call live APIs. Crime and motion artifacts are gitignored, so a fresh clone uses the rule fallbacks.

Open http://127.0.0.1:8741/ for the page.

Open http://127.0.0.1:8741/v1/health for health. Expected body: `{"status":"ok"}`.

A lower score is safer.

## Run locally (Ubuntu or WSL)

From the cloned repository:

```bash
cd module1
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cd threat_engine
export MOCK_MODE=true
python -m uvicorn app.main:app --host 127.0.0.1 --port 8741
```

Same page and health URLs as above.

## Offline behavior

With `MOCK_MODE=true`, weather, safe places, and the LLM stay offline. Movement uses the activity label or the accelerometer rule. `sudden_stop` still comes from a speed drop between requests in the same session. News and the explanation stay on their rule-based text when the LLM key is missing, the call times out, or the JSON does not match the schema. A missing or unreadable artifact does not raise.

Set `MOCK_MODE=false` to call Open-Meteo and Overpass, to score crime risk with `threat_engine/ml/artifacts/crime_risk.txt` when that artifact loads, and to classify an accelerometer window with `threat_engine/ml/artifacts/motion.joblib` when that artifact loads. With `MOCK_MODE=false` and `LLM_PROVIDER`, `LLM_MODEL`, and `LLM_API_KEY` set, the client calls OpenAI or Anthropic with a timeout. No key means no call.

Crime training is under `threat_engine/ml/crime_risk/`. It is trained on Los Angeles data to demonstrate the method, with city-agnostic features, and is ready for local police data. Gurugram output is illustrative, not validated. Movement training is under `threat_engine/ml/motion/`. Place density stays on its offline rule.

## Sample assess

From `module1/threat_engine`, with the server running. On PowerShell, `curl` is an alias, so use `curl.exe`:

```bash
curl -s -X POST http://127.0.0.1:8741/v1/assess \
  -H 'content-type: application/json' \
  -d '{"session_id":"abc","timestamp":"2026-09-29T23:40:00+05:30","location":{"lat":28.4595,"lon":77.0266,"speed_mps":1.4,"heading_deg":90},"device":{"battery_pct":18,"cellular_dbm":-108,"internet_available":false},"nearby_devices":{"ble_count":3,"wifi_count":2},"movement":{"accel_window":[[0.1,9.8,0.3]],"sampling_hz":50}}'
```

`current_score` is the clamped rule-based score. `predicted` lists a 5 minute score and a 10 minute score. Those are a projection along the current speed and heading, not a forecast. Contributor points sum to the current score before that clamp. A lower score is safer.

## Tests

From `module1`, with the virtualenv active:

```powershell
pytest
```

The suite checks schema validation, health, each provider's 0..1 range, missing-data fallbacks, weight renormalization, and the contributor-point invariant.
