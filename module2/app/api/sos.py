import base64
import io
import logging
import smtplib
import uuid
from datetime import datetime
from email.message import EmailMessage

from fastapi import APIRouter, HTTPException

from app.config import (
    EMOTION_ANGRY_SCORE,
    EMOTION_SAD_SCORE,
    KEYWORD_FIRST_MATCH_SCORE,
    KEYWORD_REPEAT_SCORE,
    KEYWORD_WINDOW_CAP,
    settings,
)
from app.models.schemas import EmergencyCreateRequest, EmergencyResolveRequest, EmergencyResponse, GuardianSettingsRequest, SignalEventRequest, SosJourneyStartRequest
from app.services import store
from app.services.risk_engine import compute_risk, level_for_score, update_risk

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sos"])

MODEL_ID = "Saumya3007/spee_project_fairhindiser-clues"
_fairhindiser_model = None
_fairhindiser_processor = None


def _load_fairhindiser():
    global _fairhindiser_model, _fairhindiser_processor
    if _fairhindiser_model is not None or _fairhindiser_processor is not None:
        return True
    try:
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
        _fairhindiser_processor = AutoFeatureExtractor.from_pretrained(MODEL_ID)
        _fairhindiser_model = AutoModelForAudioClassification.from_pretrained(MODEL_ID)
        return True
    except Exception as exc:  # pragma: no cover - optional dependency path
        logger.warning("FairHindiSER unavailable: %s", exc)
        return False


def _normalize_emotion(label):
    value = (label or 'neutral').lower().strip()
    if value in {'angry', 'anger'}:
        return 'angry'
    if value in {'sad', 'cry', 'sorry', 'disappointed'}:
        return 'sad'
    if value in {'happy', 'joy'}:
        return 'happy'
    return 'neutral'


def _transcript_fallback(transcript):
    text = (transcript or '').lower()
    if any(token in text for token in ['angry', 'gussa', 'mad', 'rage', 'furious', 'hate']):
        return 'angry'
    if any(token in text for token in ['sad', 'cry', 'crying', 'upset', 'afraid', 'fear', 'depressed']):
        return 'sad'
    return 'neutral'


def _infer_emotion_from_audio(audio_bytes, sample_rate=16000, transcript=''):
    if not audio_bytes:
        return _transcript_fallback(transcript)

    ok = _load_fairhindiser()
    if not ok:
        return _transcript_fallback(transcript)

    try:
        import numpy as np
        import torch
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        if _fairhindiser_processor is None or _fairhindiser_model is None:
            _fairhindiser_processor = AutoFeatureExtractor.from_pretrained(MODEL_ID)
            _fairhindiser_model = AutoModelForAudioClassification.from_pretrained(MODEL_ID)

        wav = io.BytesIO(audio_bytes)
        try:
            import soundfile as sf
            data, sr = sf.read(wav, dtype='float32', always_2d=False)
        except Exception:
            data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            sr = sample_rate

        if data.ndim == 2:
            data = data.mean(axis=1)
        if sr != 16000:
            # approximate resample without extra dependency to keep runtime lightweight
            import math
            target = 16000
            new_len = int(len(data) * target / sr)
            if new_len > 0:
                resampled = np.interp(np.linspace(0, len(data), new_len), np.arange(len(data)), data)
                data = resampled.astype(np.float32)
                sr = target
        inputs = _fairhindiser_processor(data, sampling_rate=sr, return_tensors='pt')
        with torch.no_grad():
            logits = _fairhindiser_model(**inputs).logits
        idx = int(torch.argmax(logits, dim=-1).item())
        label = _fairhindiser_model.config.id2label.get(idx, 'neutral')
        return _normalize_emotion(label)
    except Exception as exc:  # pragma: no cover - model/runtime fallback
        logger.warning("FairHindiSER runtime inference failed: %s", exc)
        return _transcript_fallback(transcript)


def _journey(jid):
    if jid not in store.sos_journeys:
        raise HTTPException(404, "Unknown journey")
    return store.sos_journeys[jid]


def _emergency(eid):
    if eid not in store.emergencies:
        raise HTTPException(404, "Unknown emergency")
    return store.emergencies[eid]


def _reset_journey_risk_window(journey):
    journey["risk_score"] = 0
    journey["risk_level"] = "LOW"
    journey["keyword_window_score"] = 0
    journey["countdown_required"] = False
    journey["countdown_seconds"] = 0


def _guardian_emails():
    return [email.strip() for email in store.guardian_settings.get("guardian_emails", []) if email and email.strip()]


def _send_alert_email(emergency, recipient_email):
    host = settings.smtp_host
    port = settings.smtp_port
    user = settings.smtp_username
    password = settings.smtp_password
    from_addr = settings.smtp_from
    base_url = settings.frontend_base_url

    if not all([host, port, user, password, from_addr]):
        return {
            "success": False,
            "error": "SMTP not configured. Add SMTP_HOST/PORT/USERNAME/PASSWORD and SMTP_FROM (or EMAIL_* equivalents) in the backend environment before sending guardian emails.",
            "recipient": recipient_email,
        }

    recipient = recipient_email
    if not recipient:
        return {
            "success": False,
            "error": "No valid guardian email configured for SOS alerts.",
            "recipient": recipient_email,
        }
    port_int = int(port)

    try:
        msg = EmailMessage()
        msg["Subject"] = "URGENT: SOS ALERT - Immediate Assistance Needed"
        msg["From"] = from_addr
        msg["To"] = recipient
        msg["Reply-To"] = from_addr

        lat = emergency.get("latitude")
        lon = emergency.get("longitude")
        profile = store.guardian_settings.get("emergency_profile", {})
        address = (profile.get("address") or "Address not provided").strip() or "Address not provided"
        blood_type = (profile.get("blood_type") or "Not provided").strip() or "Not provided"
        emergency_contacts = store.guardian_settings.get("emergency_contacts") or []
        contacts_text = "\n".join(
            f"- {item.get('label', 'Contact')}: {item.get('number', 'N/A')}"
            for item in emergency_contacts if item.get("number")
        ) or "- No emergency contacts configured"
        map_url = "unavailable" if lat is None or lon is None else f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}"
        location_link = f"{base_url}/?lat={lat}&lng={lon}" if lat is not None and lon is not None else "Location unavailable"
        body = (
            "URGENT SOS ALERT\n\n"
            "This is an emergency notification. Please act immediately.\n\n"
            f"User: {emergency.get('user_name', 'User')}\n"
            f"Trigger: {emergency.get('trigger_type', 'AUTO')}\n"
            f"Risk Score: {emergency.get('risk_score', 0)}\n"
            f"Time: {emergency.get('created_at')}\n\n"
            "Current location:\n"
            f"Latitude: {lat if lat is not None else 'unavailable'}\n"
            f"Longitude: {lon if lon is not None else 'unavailable'}\n"
            f"Map link: {map_url}\n"
            f"Live tracking link: {location_link}\n\n"
            f"Address: {address}\n"
            f"Blood type: {blood_type}\n\n"
            "Emergency contact numbers:\n"
            f"{contacts_text}\n\n"
            "Please contact the user immediately and if necessary call local emergency services."
        )
        msg.set_content(body)

        if port_int == 465:
            with smtplib.SMTP_SSL(host, port_int) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port_int, timeout=30) as smtp:
                if host.lower() not in {"localhost"}:
                    smtp.starttls()
                smtp.login(user, password)
                smtp.send_message(msg)
        return {"success": True, "recipient": recipient}
    except Exception as exc:  # pragma: no cover - network config only
        return {"success": False, "error": str(exc), "recipient": recipient}


@router.get("/settings/guardians")
def get_guardian_settings():
    settings = dict(store.guardian_settings)
    settings["guardian_emails"] = [email for email in settings.get("guardian_emails", []) if email]
    settings.setdefault("emergency_contacts", [])
    settings.setdefault("emergency_profile", {
        "name": "",
        "address": "",
        "blood_type": "",
        "allergies": "",
        "medical_conditions": "",
    })
    return settings


@router.post("/settings/guardians")
def save_guardian_settings(req: GuardianSettingsRequest):
    emails = []
    for email in req.guardian_emails or []:
        cleaned = (email or "").strip()
        if cleaned:
            emails.append(cleaned)
    if len(emails) < 2:
        raise HTTPException(400, "At least two guardian emails are required")
    contacts = []
    for item in req.emergency_contacts or []:
        number = (item.number or "").strip()
        if number:
            contacts.append({"label": (item.label or "Emergency").strip() or "Emergency", "number": number})
    if len(contacts) < 2:
        contacts = [{"label": "Police", "number": "112"}, {"label": "Emergency", "number": "108"}]
    profile = {
        "name": (req.emergency_profile.name or "").strip(),
        "address": (req.emergency_profile.address or "").strip(),
        "blood_type": (req.emergency_profile.blood_type or "").strip(),
        "allergies": (req.emergency_profile.allergies or "").strip(),
        "medical_conditions": (req.emergency_profile.medical_conditions or "").strip(),
    }
    store.guardian_settings = {
        "guardian_emails": emails[:2],
        "location_update_interval_minutes": max(1, int(req.location_update_interval_minutes or 5)),
        "emergency_contacts": contacts[:2],
        "emergency_profile": profile,
    }
    return store.guardian_settings


@router.post("/journeys/start")
def start_journey(req: SosJourneyStartRequest):
    jid = uuid.uuid4().hex[:8]
    store.sos_journeys[jid] = {
        "journey_id": jid,
        "status": "JOURNEY_ACTIVE",
        "risk_score": 0,
        "risk_level": "LOW",
        "trigger_reasons": [],
        "keyword_window_score": 0,
        "user_name": req.user_name,
        "latitude": req.latitude,
        "longitude": req.longitude,
    }
    return {"journey_id": jid, "status": "JOURNEY_ACTIVE"}


@router.post("/journeys/{jid}/end")
def end_journey(jid: str):
    journey = _journey(jid)
    journey["status"] = "IDLE"
    if journey.get("emergency_id"):
        emergency = _emergency(journey["emergency_id"])
        emergency["status"] = "RESOLVED"
    return {"journey_id": jid, "status": "IDLE"}


@router.get("/journeys/{jid}/status")
def journey_status(jid: str):
    journey = _journey(jid)
    return {
        "journey_id": jid,
        "status": journey["status"],
        "risk_score": journey.get("risk_score", 0),
        "risk_level": journey.get("risk_level", "LOW"),
        "trigger_reasons": journey.get("trigger_reasons", []),
        "countdown_required": journey.get("countdown_required", False),
        "countdown_seconds": journey.get("countdown_seconds", 0),
        "latitude": journey.get("latitude"),
        "longitude": journey.get("longitude"),
    }


@router.post("/signals")
def record_signal(req: SignalEventRequest):
    journey = _journey(req.journey_id)
    if journey.get("status") == "EMERGENCY_ACTIVE" and req.signal_type != "SAFE":
        return {
            "journey_id": req.journey_id,
            "risk_score": 0,
            "risk_level": "LOW",
            "trigger_reasons": ["SOS ACTIVATED"],
            "countdown_required": False,
            "countdown_seconds": 0,
            "status": "EMERGENCY_ACTIVE",
        }
    if req.latitude is not None:
        journey["latitude"] = req.latitude
    if req.longitude is not None:
        journey["longitude"] = req.longitude

    if req.signal_type == "KEYWORD_DETECTED":
        current = journey.get("keyword_window_score", 0)
        if current == 0:
            delta = KEYWORD_FIRST_MATCH_SCORE
            reason = "Distress keyword detected"
        else:
            delta = max(0, min(KEYWORD_REPEAT_SCORE, KEYWORD_WINDOW_CAP - current))
            reason = "Repeated distress keyword"
        journey["keyword_window_score"] = current + delta
        risk = update_risk(journey, "KEYWORD_DETECTED", reason=reason, delta=delta)
    elif req.signal_type == "EMOTION_DETECTED":
        emotion = (req.emotion or "neutral").lower()
        if emotion == "angry":
            delta = EMOTION_ANGRY_SCORE
            signal_reason = "Angry voice tone"
        elif emotion == "sad":
            delta = EMOTION_SAD_SCORE
            signal_reason = "Sad voice tone"
        else:
            delta = 0
            signal_reason = "Neutral voice tone"
        risk = update_risk(journey, "EMOTION_DETECTED", reason=signal_reason, delta=delta)
    elif req.signal_type == "FALL_DETECTED":
        risk = update_risk(journey, "FALL_DETECTED", reason="Fall detected + post-fall inactivity", delta=70)
    elif req.signal_type == "COUNTDOWN_EXPIRED":
        risk = update_risk(journey, "COUNTDOWN_EXPIRED", reason="No response to safety countdown", delta=30)
    elif req.signal_type == "MOVEMENT_RESUMED":
        risk = update_risk(journey, "MOVEMENT_RESUMED", reason="Normal movement resumed", delta=-10)
    elif req.signal_type == "SAFE":
        emergency_id = journey.pop("emergency_id", None)
        if emergency_id and emergency_id in store.emergencies:
            store.emergencies[emergency_id]["status"] = "RESOLVED"
            store.emergencies[emergency_id]["risk_score"] = 0
            store.emergencies[emergency_id]["risk_level"] = "LOW"
            store.emergencies[emergency_id]["trigger_reasons"] = ["User confirmed safe"]
        _reset_journey_risk_window(journey)
        journey["status"] = "IDLE"
        journey["trigger_reasons"] = []
        store.sos_journeys.pop(req.journey_id, None)
        return {"journey_id": req.journey_id, "risk_score": 0, "risk_level": "LOW",
                "trigger_reasons": [], "countdown_required": False, "countdown_seconds": 0,
                "status": "IDLE"}
    else:
        risk = compute_risk(journey)

    journey["risk_score"] = risk["risk_score"]
    journey["risk_level"] = risk["risk_level"]
    journey["trigger_reasons"] = risk["trigger_reasons"]
    if journey.get("status") == "EMERGENCY_ACTIVE":
        journey["countdown_required"] = False
        journey["countdown_seconds"] = 0
        journey["risk_score"] = 0
        journey["risk_level"] = "LOW"
        journey["trigger_reasons"] = ["SOS ACTIVATED"]
        return {"journey_id": req.journey_id, "risk_score": 0, "risk_level": "LOW", "trigger_reasons": ["SOS ACTIVATED"], "countdown_required": False, "countdown_seconds": 0, "status": "EMERGENCY_ACTIVE"}
    if risk["risk_score"] >= 60:
        journey["countdown_required"] = True
        journey["countdown_seconds"] = settings.safety_countdown_seconds
        if journey["status"] == "JOURNEY_ACTIVE":
            journey["status"] = "SUSPECTED_EMERGENCY"
    else:
        journey["countdown_required"] = False
        journey["countdown_seconds"] = 0
    return {"journey_id": req.journey_id, **risk, "countdown_required": journey.get("countdown_required", False), "countdown_seconds": journey.get("countdown_seconds", 0), "status": journey.get("status", "JOURNEY_ACTIVE")}


@router.post("/emergencies")
def create_emergency(req: EmergencyCreateRequest):
    # TODO: single-user prototype assumption; without journey_id the first stored journey is used.
    journey = _journey(req.journey_id) if req.journey_id else next(iter(store.sos_journeys.values()), None)
    if journey is None:
        raise HTTPException(404, "No active journey")
    trigger_score = 100 if req.trigger_type == "MANUAL" else int(journey.get("risk_score", 0))
    eid = uuid.uuid4().hex[:8]
    emergency = {
        "id": eid,
        "journey_id": journey["journey_id"],
        "trigger_type": req.trigger_type,
        "user_name": req.user_name or journey.get("user_name", "User"),
        "latitude": req.latitude if req.latitude is not None else journey.get("latitude"),
        "longitude": req.longitude if req.longitude is not None else journey.get("longitude"),
        "accuracy": req.accuracy,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "status": "ACTIVE",
        "risk_score": trigger_score,
        "risk_level": level_for_score(trigger_score),
        "trigger_reasons": ["Manual SOS"] if req.trigger_type == "MANUAL" else list(journey.get("trigger_reasons", [])),
        "events": [],
    }
    store.emergencies[eid] = emergency
    journey["emergency_id"] = eid
    journey["status"] = "EMERGENCY_ACTIVE"
    _reset_journey_risk_window(journey)
    journey["trigger_reasons"] = ["SOS ACTIVATED"]
    guardian_emails = _guardian_emails()
    email_results = [_send_alert_email(emergency, email) for email in guardian_emails]
    return {
        "emergency_id": eid,
        "status": "EMERGENCY_ACTIVE",
        "risk_score": 0,
        "risk_level": "LOW",
        "countdown_required": False,
        "countdown_seconds": 0,
        "trigger_reasons": ["SOS ACTIVATED"],
        "guardian_emails_sent": guardian_emails,
        "email_results": email_results,
        "email_status": "sent" if guardian_emails and all(result.get("success") for result in email_results) else "skipped" if not guardian_emails else "partial",
    }


def _emergency_response(emergency):
    return EmergencyResponse(
        id=emergency["id"],
        journey_id=emergency["journey_id"],
        trigger_type=emergency["trigger_type"],
        user_name=emergency.get("user_name"),
        latitude=emergency.get("latitude"),
        longitude=emergency.get("longitude"),
        accuracy=emergency.get("accuracy"),
        created_at=emergency["created_at"],
        status=emergency["status"],
        events=list(emergency.get("events", [])),
        **compute_risk(emergency),
    )


@router.get("/emergencies/{eid}", response_model=EmergencyResponse)
def read_emergency(eid: str):
    return _emergency_response(_emergency(eid))


@router.post("/emergencies/{eid}/resolve")
def resolve_emergency(eid: str, req: EmergencyResolveRequest):
    emergency = _emergency(eid)
    journey = _journey(emergency["journey_id"])
    if req.reason == "SAFE":
        emergency["status"] = "RESOLVED"
        journey["status"] = "JOURNEY_ACTIVE"
        _reset_journey_risk_window(journey)
        journey["trigger_reasons"] = []
        emergency["risk_score"] = 0
        emergency["risk_level"] = "LOW"
        emergency["trigger_reasons"] = ["User confirmed safe"]
        return {"emergency_id": eid, "status": "RESOLVED", "message": "Journey resumed"}
    emergency["status"] = "RESOLVED"
    return {"emergency_id": eid, "status": "RESOLVED"}


@router.post("/emergencies/{eid}/resend-email")
def resend_email(eid: str):
    emergency = _emergency(eid)
    results = [_send_alert_email(emergency, email) for email in _guardian_emails()]
    success = bool(results) and all(r.get("success") for r in results)
    errors = [r["error"] for r in results if r.get("error")]
    emergency.setdefault("events", []).append({"event_type": "EMAIL_SENT", "metadata": {"success": success, "errors": errors}})
    return {"emergency_id": eid, "success": success, "email_results": results}


@router.post("/internal/emotion-infer")
def emotion_infer(payload: dict):
    payload = payload or {}
    transcript = payload.get("transcript") or ""
    label = payload.get("emotion")
    if label is None:
        audio_b64 = payload.get("audio_base64") or payload.get("audio")
        if audio_b64:
            try:
                raw = base64.b64decode(audio_b64)
                label = _infer_emotion_from_audio(raw, sample_rate=int(payload.get("sample_rate") or 16000), transcript=transcript)
            except Exception:
                label = _transcript_fallback(transcript)
        else:
            label = _transcript_fallback(transcript)
    return {"label": _normalize_emotion(label), "source": "FairHindiSER" if _fairhindiser_model is not None else "heuristic"}
