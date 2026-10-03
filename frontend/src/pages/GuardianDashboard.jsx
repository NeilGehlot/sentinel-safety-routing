import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import MapView from '../components/MapView.jsx'
import { Num, SafetyFactorList, SafetyScore } from '../components/Parts.jsx'
import { Badge } from '../components/ui/badge.jsx'

export const DASHBOARD_POLL_MS = 5000

function pickPosition(emergency) {
  const live = emergency.position
  if (live && live.latitude != null && live.longitude != null) return { point: live, source: emergency.location_live === false ? 'last_known' : (live.source || 'live') }
  if (emergency.latitude != null && emergency.longitude != null) {
    return { point: { latitude: emergency.latitude, longitude: emergency.longitude }, source: 'last_known' }
  }
  const last = emergency.last_known
  if (last && last.latitude != null && last.longitude != null) return { point: last, source: 'last_known' }
  const geometry = emergency.geometry || []
  if (geometry.length) {
    const pt = geometry[0]
    if (Array.isArray(pt) && pt.length >= 2) return { point: { latitude: pt[0], longitude: pt[1] }, source: 'route' }
  }
  return { point: null, source: null }
}

export default function GuardianDashboard() {
  const { emergencyId } = useParams()
  const [emergency, setEmergency] = useState(null)
  const [state, setState] = useState('loading')

  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        let response = await fetch(`/monitor/${emergencyId}`)
        if (response.status === 404) {
          response = await fetch(`/emergencies/${emergencyId}`)
        }
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

  if (state === 'loading') return <main className="guardian-message">Loading live trip data...</main>
  if (state === 'invalid') return <main className="guardian-message">This emergency link is invalid or has expired.</main>
  if (state === 'error') return <main className="guardian-message">Live emergency data is temporarily unavailable.</main>

  const { point: position, source: locationSource } = pickPosition(emergency)
  const geometry = emergency.geometry || []
  const hasRoute = geometry.length >= 2
  const distance = emergency.distance_m || 0
  const progress = emergency.progress_m || 0
  const progressPct = distance ? Math.max(0, Math.min(100, Math.round((100 * progress) / distance))) : null
  const events = [...(emergency.events || [])].reverse()
  const isShare = (emergency.monitor_kind === 'share') || emergency.trigger_type === 'SHARE'
  const routes = hasRoute
    ? [{ id: emergency.route_id || 'live', geometry, safety: emergency.safety }]
    : []
  const mapTitle = locationSource === 'live' || emergency.location_live
    ? 'Live location and route'
    : locationSource
      ? 'Last known location and route'
      : 'Route map'

  return (
    <main className="guardian-dashboard">
      {emergency.status === 'RESOLVED' && <div className="resolved-banner">This emergency has been resolved</div>}
      {emergency.nav_status === 'completed' && <div className="resolved-banner">This trip has completed</div>}
      <header>
        <div>
          <span className="eyebrow">{isShare ? 'Sentinel live trip' : 'Sentinel live emergency'}</span>
          <h1>{emergency.user_name || 'User'}</h1>
        </div>
        <Badge variant={emergency.status === 'RESOLVED' ? 'secondary' : 'destructive'}>{emergency.status}</Badge>
      </header>
      <section className="guardian-summary panel">
        <div><small>Trigger</small><strong>{emergency.trigger_type}</strong></div>
        <div><small>Started</small><strong>{new Date(emergency.created_at).toLocaleString()}</strong></div>
        <div className="guardian-risk">
          <small>Route safety</small>
          {emergency.safety != null
            ? <span className="guardian-safety"><SafetyScore value={emergency.safety} /> / 100</span>
            : <strong>Not yet scored</strong>}
        </div>
        <div className="guardian-risk">
          <small>SOS risk</small>
          <Badge variant="outline" className="risk-level-badge"><Num value={emergency.risk_score} risk className="score" /> {emergency.risk_level}</Badge>
        </div>
        <div>
          <small>Progress</small>
          <strong>{progressPct != null ? `${progressPct}% · ${Math.round(progress)} m of ${Math.round(distance)} m` : 'Waiting for route'}</strong>
        </div>
        <div>
          <small>ETA</small>
          <strong>{emergency.eta_min != null ? `${emergency.eta_min} min` : 'Unavailable'}</strong>
        </div>
      </section>
      <section className="guardian-map panel">
        <h2>{mapTitle}</h2>
        {hasRoute || position
          ? <MapView
              routes={routes}
              selectedId={emergency.route_id || 'live'}
              incidents={emergency.incidents_ahead || []}
              position={position}
              start={hasRoute ? { latitude: geometry[0][0], longitude: geometry[0][1] } : position}
              dest={hasRoute ? { latitude: geometry[geometry.length - 1][0], longitude: geometry[geometry.length - 1][1] } : undefined}
            />
          : <div className="location-unavailable">Location unavailable</div>}
      </section>
      <div className="guardian-details">
        <section className="panel">
          <h2>Safety factors</h2>
          {emergency.factors && Object.keys(emergency.factors).length
            ? <SafetyFactorList factors={emergency.factors} />
            : <p className="muted">Safety factors will appear once a route is active. Historical crime is one factor, not the whole score.</p>}
        </section>
        <section className="panel">
          <h2>{isShare ? 'Trip notes' : 'Trigger reasons'}</h2>
          {emergency.trigger_reasons?.length ? <ul>{emergency.trigger_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul> : <p className="muted">No trigger reasons recorded</p>}
        </section>
        <section className="panel">
          <h2>Incidents ahead</h2>
          {emergency.incidents_ahead?.length
            ? <ul>{emergency.incidents_ahead.map((item) => <li key={item.id || item.title}>{item.title} ({item.distance_ahead_m} m)</li>)}</ul>
            : <p className="muted">No incidents ahead</p>}
        </section>
        <section className="panel">
          <h2>Activity</h2>
          {events.length ? <ol className="event-timeline">{events.map((event, index) => <li key={index}><strong>{event.event_type || event.type || 'Update'}</strong><span>{event.created_at ? new Date(event.created_at).toLocaleString() : 'Time not recorded'}</span></li>)}</ol> : <p className="muted">No activity logged yet</p>}
        </section>
      </div>
    </main>
  )
}
