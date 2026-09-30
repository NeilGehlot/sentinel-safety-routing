# SENTINEL

SENTINEL is a multi-module safety prototype combining real-time safe-route monitoring with an Intelligent SOS flow. It includes a route safety dashboard and an emergency-response workflow for distress detection, risk scoring, countdown checks, and contact escalation.

## Included Features

- Safe route search and recommendation engine
- Predictive rerouting when an incident ahead makes the current route worse
- Journey simulation and live trip status tracking
- Intelligent SOS journey lifecycle
- Manual SOS trigger
- Automatic signal handling for:
  - distress keywords
  - fall detection
  - speech emotion signal (angry/sad/neutral/happy)
  - countdown expiry and safe confirmation
- Emergency risk scoring and risk levels
- Email alerting flow with SMTP configuration
- Demo-ready UI for testing the SOS flow and route monitoring

## Architecture

- Frontend: React + Vite
- Backend: FastAPI
- Data: in-memory prototype store for hackathon/demo use
- Maps: Leaflet + OpenStreetMap

## Run the Project

### 1) Install backend dependencies
```bash
cd module2
python -m pip install -r requirements.txt
```

### 2) Configure environment variables
Copy the example file and edit as needed:
```bash
cp .env.example .env
```
Use the required values for any SMTP or frontend env vars you want to test. The app also supports route/journey demo config values such as polling and timing intervals.

### 3) Start the backend
```bash
cd module2
uvicorn app.main:app --reload
```
Open the API docs at:
- http://localhost:8000/docs

### 4) Start the frontend
In a second terminal:
```bash
cd frontend
npm install
npm run dev
```
Then open the frontend in the browser, usually at:
- http://localhost:5173

## Demo Flow

### Route safety demo
1. Open the frontend
2. Choose a starting point and destination
3. Search routes
4. Start a journey
5. Use the demo incident injector to simulate an accident ahead
6. Review the reroute recommendation and switch routes if desired

### SOS demo
1. Activate the safety monitor from the frontend
2. Trigger distress keyword, fall, or angry-voice signal events
3. Observe the risk score and countdown behavior
4. Confirm "I'm safe" before timeout or trigger a manual SOS
5. Review the created emergency state and related alert flow

## Tests

Run the backend test suite:
```bash
cd module2
python -m pytest -q
```

## Project Status

Implemented:
- route search and route recommendation
- adaptive rerouting logic
- demo incident injection
- Intelligent SOS journey state handling
- manual and automatic emergency triggers
- risk calculations and countdown flow
- basic email alert integration

Prototype-only limitations:
- in-memory storage instead of a persistent database
- demo data instead of live production sources
- simplified emergency/contact workflow for hackathon use
- no production-grade auth, persistence, or deployment setup
