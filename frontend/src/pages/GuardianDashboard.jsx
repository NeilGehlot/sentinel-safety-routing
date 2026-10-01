import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import MapView from '../components/MapView.jsx'
import { Num } from '../components/Parts.jsx'
import { Badge } from '../components/ui/badge.jsx'

export const DASHBOARD_POLL_MS = 5000

export default function GuardianDashboard() {
  const { emergencyId } = useParams()
  const [emergency, setEmergency] = useState(null)
  const [state, setState] = useState('loading')

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const response = await fetch(`/emergencies/${emergencyId}`)
        if (response.status === 404) {
          if (active) setState('invalid')
          return
        }
        if (!response.ok) throw new Error('Unable to load emergency')
        const payload = await response.json()
        if (active) {
          setEmergency(payload)
          setState('ready')
        }
      } catch {
        if (active) setState('error')
      }
    }
    load()
    const timer = setInterval(load, DASHBOARD_POLL_MS)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [emergencyId])

  if (state === 'loading') return <main className="guardian-message">Loading live emergency data...</main>
  if (state === 'invalid') return <main className="guardian-message">This emergency link is invalid or has expired.</main>
  if (state === 'error') return <main className="guardian-message">Live emergency data is temporarily unavailable.</main>

  const hasLocation = emergency.latitude != null && emergency.longitude != null
  const events = [...(emergency.events || [])].reverse()

  return (
    <main className="guardian-dashboard">
      {emergency.status === 'RESOLVED' && <div className="resolved-banner">This emergency has been resolved</div>}
      <header>
        <div><span className="eyebrow">Sentinel live emergency</span><h1>{emergency.user_name || 'User'}</h1></div>
        <Badge variant={emergency.status === 'RESOLVED' ? 'secondary' : 'destructive'}>{emergency.status}</Badge>
      </header>
      <section className="guardian-summary panel">
        <div><small>Trigger</small><strong>{emergency.trigger_type}</strong></div>
        <div><small>Started</small><strong>{new Date(emergency.created_at).toLocaleString()}</strong></div>
        <div className="guardian-risk"><small>Risk level</small><Badge variant="outline" className="risk-level-badge"><Num value={emergency.risk_score} risk className="score" /> {emergency.risk_level}</Badge></div>
      </section>
      <section className="guardian-map panel">
        <h2>Last known location</h2>
        {hasLocation
          ? <MapView start={{ latitude: emergency.latitude, longitude: emergency.longitude }} />
          : <div className="location-unavailable">Location unavailable</div>}
      </section>
      <div className="guardian-details">
        <section className="panel"><h2>Trigger reasons</h2>{emergency.trigger_reasons?.length ? <ul>{emergency.trigger_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul> : <p className="muted">No trigger reasons recorded</p>}</section>
        <section className="panel"><h2>Activity</h2>{events.length ? <ol className="event-timeline">{events.map((event, index) => <li key={index}><strong>{event.event_type || event.type || 'Update'}</strong><span>{event.created_at ? new Date(event.created_at).toLocaleString() : 'Time not recorded'}</span></li>)}</ol> : <p className="muted">No activity logged yet</p>}</section>
      </div>
    </main>
  )
}
