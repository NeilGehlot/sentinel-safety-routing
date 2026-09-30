"""In-memory prototype store + incident sources. Swap for SQLite/PostGIS repository later."""
import json, pathlib
from app.models.schemas import Incident

class DemoIncidentSource:
    """Implemented. RSS/GDELT/UserReport sources plug in with the same .fetch()."""
    def fetch(self):
        p = pathlib.Path(__file__).resolve().parents[2]/"data"/"demo_incidents.json"
        return [Incident(**d) for d in json.loads(p.read_text())]

routes: dict = {}
journeys: dict = {}
incidents: list = DemoIncidentSource().fetch()

# SOS prototype state
sos_journeys: dict = {}
emergencies: dict = {}
emergency_events: list = []
contacts: dict = {
    "1": {"id": "1", "name": "Contact 1", "email": "contact1@example.com"},
    "2": {"id": "2", "name": "Contact 2", "email": "contact2@example.com"},
    "3": {"id": "3", "name": "Contact 3", "email": "contact3@example.com"},
}
