import { useState } from 'react'
import { motion } from 'framer-motion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { segmentSafety } from './MapView.jsx'

export const toneClass = (v) => v <= 40 ? 'tone-red' : v <= 70 ? 'tone-amber' : 'tone-green'
export const Num = ({ value, risk = false, className = '' }) => <span className={`${toneClass(risk ? 100 - value : value)} ${className}`}>{Math.round(value)}</span>
export const SafetyScore = ({ value }) => <span className={'score ' + toneClass(value)}>{Math.round(value)}</span>
const segLen = (a, b) => { const r = Math.PI / 180, x = (b[1] - a[1]) * r * Math.cos((a[0] + b[0]) / 2 * r), y = (b[0] - a[0]) * r; return Math.sqrt(x * x + y * y) * 6371000 }
export const HIGH_RISK_BELOW = 70
export const highRiskExposure = (route, incidents = []) => {
  const g = route?.geometry || []
  if (g.length < 2 || !route.distance_m || !route.eta_min) return { minutes: 0, meters: 0, share: 0 }
  let meters = 0
  for (let n = 0; n < g.length - 1; n++) if (segmentSafety(Number(route.safety) || 80, g[n], g[n + 1], incidents) <= HIGH_RISK_BELOW) meters += segLen(g[n], g[n + 1])
  return { meters: Math.round(meters), minutes: Math.round(meters / route.distance_m * route.eta_min * 10) / 10, share: Math.round(meters / route.distance_m * 100) }
}
export const leastExposedId = (routes = [], incidents = []) => routes.reduce((best, r) => { const e = highRiskExposure(r, incidents).minutes; return !best || e < best.e || (e === best.e && r.safety > best.r.safety) ? { r, e } : best }, undefined)?.r.id
export const LoadingState = ({ text = 'Working…' }) => <p className="muted">{text}</p>
export const ErrorState = ({ message, onRetry }) => <div className="err">{message}{onRetry && <button onClick={onRetry}>Try again</button>}</div>
export const Metric = ({ icon, label, value, tone = '' }) => <div className="metric-cell"><span className={'metric-icon ' + tone}>{icon}</span><div><b>{value}</b><small>{label}</small></div></div>
export const SafetyFactorList = ({ factors }) => (
  <ul className="factors">{Object.entries(factors || {}).map(([k, v]) =>
    <li key={k}><span>{k === 'safe_locations' ? 'safe-location factor' : k.replace('_', ' ')}</span><i><b style={{ width: v + '%' }} /></i><em>{v}</em></li>)}</ul>)
export const RouteCard = ({ r, selected, onSelect }) => (
  <motion.article layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} whileHover={{ y: -4, boxShadow: '0 16px 32px rgba(27,31,78,.18)' }} transition={{ type: 'spring', stiffness: 300, damping: 24 }} className={'route-card' + (selected ? ' selected' : '')} onClick={() => onSelect(r.id)}>
    <div className="route-card-head"><div><span className="eyebrow">Route option</span><h3>{r.recommended ? 'Recommended route' : 'Alternative route'}</h3></div>{r.recommended && <span className="tag"><span>✓</span> Recommended</span>}</div>
    <div className="route-score-row"><div className="route-score route-score-hero"><strong className={toneClass(r.safety)}>{Math.round(r.safety)}</strong><span>/100</span><small>Safety score</small></div><Metric icon="◷" label="ETA" value={`${Math.round(r.eta_min)} min`} /><Metric icon="⌁" label="Distance" value={`${(r.distance_m / 1000).toFixed(1)} km`} /></div>
    {r.route_score != null && <div className="muted">Route score <Num value={r.route_score} />/100 at your preference</div>}
    <div className="route-metrics"><Metric icon="✥" label="Safe factor" value={r.factors?.safe_locations ?? '—'} tone="safe" /><Metric icon="⌘" label="High-risk time" value={r.high_risk_min != null ? `${r.high_risk_min} min` : 'n/a'} tone={r.high_risk_min ? 'risk' : 'safe'} /><Metric icon="△" label="Incidents" value={r.incident_count ?? 0} tone={r.incident_count ? 'risk' : 'safe'} /></div>
    {selected && <div className="route-details"><SafetyFactorList factors={r.factors} /><button className="link-button" onClick={(e) => { e.stopPropagation(); onSelect(r.id) }}>View route details <span>→</span></button></div>}
  </motion.article>)
export const SelectedRouteSummary = ({ r }) => (
  <div className="selected-summary"><span className="live-dot" /> Ready to navigate · <Num value={r.safety} />/100 safety</div>)
export const RerouteCard = ({ rr, onSwitch, onKeep }) => (
  <div className="insight-card alert">
    <div className="card-title"><span className="number-badge danger">!</span><div><span className="eyebrow">Safety intervention</span><h3>Safer route available</h3></div></div>
    <p>Current route: <b>{Math.round(rr.current_safety)}/100</b> · {Math.round(rr.current_eta_min)} min<br />Alternative: <b>{Math.round(rr.alternative.safety)}/100</b> · {Math.round(rr.alternative.eta_min)} min</p>
    <ul>{rr.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
    <div className="button-row"><button className="primary" onClick={onSwitch}>Switch route</button><button onClick={onKeep}>Keep current</button></div>
  </div>)
export const WhyNotCard = ({ analysis }) => analysis?.why_not?.length ? (
  <div className="insight-card why-not"><div className="card-title"><span className="number-badge">i</span><div><span className="eyebrow">Route comparison</span><h3>Why not reroute?</h3></div></div><ul>{analysis.why_not.map((reason) => <li key={reason}>{reason}</li>)}</ul></div>
) : null
export const IncidentSummary = ({ incidents = [] }) => (
  <div className="insight-card incident-summary"><div className="card-title"><span className="number-badge">!</span><div><span className="eyebrow">Live safety data</span><h3>Incident exposure</h3></div></div><div className="summary-value">{incidents.length}<small> reported incident{incidents.length === 1 ? '' : 's'}</small></div><div className="muted">{incidents.filter((i) => i.severity >= .75).length} high severity · Map intensity uses reported severity and confidence.</div></div>)
const HOURS = [6, 9, 12, 15, 18, 21, 0, 3]
export const speedScore = (r, minEta) => r?.eta_min ? Math.round(100 * Math.min(1, (minEta || r.eta_min) / r.eta_min)) : 0
export const routeScore = (safety, speed, preference) => Math.round((preference / 100) * safety + (1 - preference / 100) * speed)
export const profileAt = (route, h, preference = 50, minEta, label) => {
  const f = route.factors || {}, lighting = f.lighting ?? 80, crowd = f.crowd ?? 80, traffic = f.traffic ?? 80, speed = speedScore(route, minEta)
  const night = h >= 21 || h < 5 ? 1 : h >= 18 || h < 7 ? .5 : 0, rush = Math.floor(h) === 9 || Math.floor(h) === 18 ? 1 : 0
  const safety = Math.max(0, Math.min(100, Math.round(route.safety - night * ((100 - lighting) * .6 + (100 - crowd) * .4 + 8) - rush * (100 - traffic) * .2)))
  return { hour: h, label: label || `${String(h).padStart(2, '0')}:00`, safety, risk: 100 - safety, score: routeScore(safety, speed, preference) }
}
export const timeProfile = (route, preference = 50, minEta) => route ? HOURS.map((h) => profileAt(route, h, preference, minEta)) : []
export const DepartCompare = ({ route, time, preference, minEta }) => {
  if (!time) return null
  if (!route) return <p className="muted depart-compare">Select a route to compare departure at {time}.</p>
  const [hh, mm] = time.split(':').map(Number), at = profileAt(route, hh + mm / 60, preference, minEta, time), rows = timeProfile(route, preference, minEta)
  const best = rows.reduce((a, b) => b.score > a.score ? b : a), worst = rows.reduce((a, b) => b.score < a.score ? b : a), better = rows.filter((r) => r.score > at.score).length
  return <div className="depart-compare"><b>Departing at {time}</b>: safety <Num value={at.safety} />, risk <Num value={at.risk} risk />, route score <Num value={at.score} />. {better ? `${better} of ${rows.length} profiled hours score higher; best is ${best.label} (${best.score}), worst is ${worst.label} (${worst.score}).` : `This is as good as or better than every profiled hour (worst is ${worst.label} at ${worst.score}).`}</div>
}
export const TimeProfileTable = ({ route, preference, minEta }) => {
  const rows = timeProfile(route, preference, minEta), now = new Date().getHours()
  if (!rows.length) return <p className="muted">Find and select a route to see how its safety changes through the day.</p>
  const current = rows.reduce((best, r) => Math.abs(r.hour - now) < Math.abs(best.hour - now) ? r : best, rows[0])
  return <table className="time-profile"><thead><tr><th>Time</th><th>Risk</th><th>Safety</th><th>Route score</th></tr></thead><tbody>{rows.map((r) => <tr key={r.hour} className={r === current ? 'current' : ''}><td>{r.label}</td><td><Num value={r.risk} risk /></td><td><Num value={r.safety} /></td><td><Num value={r.score} /></td></tr>)}</tbody></table>
}
export const SafetyProfile = ({ route, preference, minEta }) => <div className="panel"><div className="panel-heading"><div><span className="eyebrow">01 · Safety intelligence</span><h2>Time-Aware Route Profile</h2></div><span className="info-dot">i</span></div><p className="muted">Estimated from the route lighting, crowd and traffic factors. Route score blends safety with speed using your slider.</p><TimeProfileTable route={route} preference={preference} minEta={minEta} /></div>
export const SafePointPanel = ({ route, points = [] }) => <div className="panel"><div className="panel-heading"><div><span className="eyebrow">02 · Network coverage</span><h2>Safe-Point Network</h2></div><span className="info-dot">i</span></div>{points.length ? <ul className="factors">{points.map((p) => <li key={p.name}><span>{p.name}</span><em>{p.kind}</em></li>)}</ul> : <div className="unavailable"><span className="panel-icon">⌖</span><div><b>No route selected</b><p>Select a route to see safe points along it (estimated demo points).</p></div></div>}{route?.factors?.safe_locations != null && <div className="factor-callout"><span>Model safe-location factor</span><strong><Num value={route.factors.safe_locations} />/100</strong></div>}</div>
export const IndependencePanel = ({ routes = [], incidents = [] }) => {
  const best = leastExposedId(routes, incidents)
  return <div className="panel"><div className="panel-heading"><div><span className="eyebrow">03 · Route comparison</span><h2>Route Independence</h2></div><span className="info-dot">i</span></div>
    {routes.length ? <><p className="muted">Recommends the route with the least time inside high-risk segments (segment safety {HIGH_RISK_BELOW} or below).</p><ul className="factors">{routes.map((r, n) => { const e = highRiskExposure(r, incidents); return <li key={r.id}><span>Route {n + 1} {r.id === best && <Badge>Least high-risk time</Badge>}</span><em className={e.minutes ? 'tone-red' : 'tone-green'}>{e.minutes} min ({e.share}%)</em></li> })}</ul></> : <div className="unavailable compact"><span className="panel-icon">⌘</span><div><b>No routes yet</b><p>Find routes to compare time spent in high-risk areas.</p></div></div>}</div>
}
const Section = ({ title, defaultOpen = false, children }) => { const [open, setOpen] = useState(defaultOpen)
  return <Collapsible open={open} onOpenChange={setOpen} className="analysis-section"><CollapsibleTrigger render={<Button variant="ghost" className="analysis-trigger" />}><span>{title}</span><span>{open ? '−' : '+'}</span></CollapsibleTrigger><CollapsibleContent className="analysis-content">{children}</CollapsibleContent></Collapsible> }
export const AnalysisPanel = ({ route, incidents = [], analysis, routes = [], threat }) => {
  const exp = route ? highRiskExposure(route, incidents) : null, best = leastExposedId(routes, incidents)
  return <section className="analysis-panel"><div className="analysis-header"><div><span className="eyebrow">Route details & analysis</span><h2>{route ? 'Selected route overview' : 'Select a route to analyze'}</h2></div>{route && <span className="analysis-score"><Num value={route.safety} /><small>/100</small></span>}</div>{route && <div className="analysis-sections">
    <Section title="Overview" defaultOpen><div className="analysis-metrics"><Metric icon="◷" label="ETA" value={`${Math.round(route.eta_min)} min`} /><Metric icon="⌁" label="Distance" value={`${(route.distance_m / 1000).toFixed(1)} km`} /><Metric icon="△" label="Incidents" value={route.incident_count ?? 0} tone={route.incident_count ? 'risk' : 'safe'} /></div></Section>
    <Section title="Risk breakdown">
      <div className="analysis-grid"><div className="analysis-block"><span className="eyebrow">Module 2 route factors</span><SafetyFactorList factors={route.factors} /></div>
      <div className="analysis-block"><span className="eyebrow">Module 1 threat engine</span>{threat?.loading && <p className="muted">Asking the threat engine…</p>}{threat?.error && <p className="muted">Module 1 threat engine is unavailable ({threat.error}). Route factors above still apply.</p>}{threat?.data && <><p>Threat score <Num value={threat.data.current_score} risk className="threat-score" /> <small className="muted">(lower is safer)</small>{threat.data.predicted?.map((p) => <span key={p.horizon_min} className="muted"> · {p.horizon_min} min: <Num value={p.score} risk /></span>)}</p><p className="muted">{threat.data.explanation?.summary}</p><ul className="factors">{threat.data.explanation?.contributors?.filter((c) => c.points).map((c) => <li key={c.signal}><span>{c.signal.replace(/_/g, ' ')}</span><small className="muted">{c.reason}</small><em>{c.points > 0 ? '+' : ''}{c.points}</em></li>)}</ul>{threat.data.recommendations?.map((x) => <p key={x} className="muted">{x}</p>)}</>}</div></div>
    </Section>
    <Section title="Exposure time"><p>High-risk time on this route: <b className={exp.minutes ? 'tone-red' : 'tone-green'}>{exp.minutes} min</b> over {(exp.meters / 1000).toFixed(2)} km ({exp.share}% of the route). {incidents.length} incident report{incidents.length === 1 ? '' : 's'} considered.</p></Section>
    <Section title="Why this route?"><p>Safety <Num value={route.safety} />/100{route.route_score != null && <>, route score <Num value={route.route_score} /> at your slider setting</>}. {best === route.id ? 'It also spends the least time in high-risk areas.' : best ? 'Another route spends less time in high-risk areas; see Route Independence.' : ''}</p></Section>
    <Section title="Why not others?">{analysis?.why_not?.length ? <ul>{analysis.why_not.map((x) => <li key={x}>{x}</li>)}</ul> : routes.filter((r) => r.id !== route.id).length ? <ul>{routes.filter((r) => r.id !== route.id).map((r) => <li key={r.id}>Safety <Num value={r.safety} />, {Math.round(r.eta_min)} min, {highRiskExposure(r, incidents).minutes} min high-risk</li>)}</ul> : <p className="muted">No other routes to compare.</p>}</Section>
  </div>}</section>
}
export const JourneyStatus = ({ s }) => (
  <div className="panel journey-panel"><div className="journey-heading"><div><span className="eyebrow">Live journey</span><h2>{s.status.replace('_', ' ')}</h2></div><SafetyScore value={s.safety} /></div>
    <div className="muted">Remaining {(Math.max(s.distance_m - s.progress_m, 0) / 1000).toFixed(1)} km · ETA {Math.round(s.eta_min)} min · {s.incidents_ahead.length} incident(s) ahead
      {s.incidents_ahead[0] && ` · nearest ${s.incidents_ahead[0].distance_ahead_m} m`}</div>
    {s.status === 'completed' && <p><b>You have arrived.</b></p>}
    <SafetyFactorList factors={s.factors} /></div>)
