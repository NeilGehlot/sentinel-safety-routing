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
