import { useEffect, useRef, useState } from 'react'
import MapView from '../components/MapView.jsx'
import { RouteCard, SelectedRouteSummary, RerouteCard, WhyNotCard, IncidentSummary, SafetyProfile, SafePointPanel, IndependencePanel, AnalysisPanel, JourneyStatus, LoadingState, ErrorState } from '../components/Parts.jsx'
import { api, PLACES, POLL_MS } from '../services/api.js'

const DEFAULT_START = { latitude: 26.9196, longitude: 75.7878 }
export default function Home() {
  const [start, setStart] = useState(DEFAULT_START), [dest, setDest] = useState(PLACES[0])
  const [routes, setRoutes] = useState([]), [sel, setSel] = useState(), [busy, setBusy] = useState(false)
  const [err, setErr] = useState(), [jid, setJid] = useState(), [st, setSt] = useState(), [note, setNote] = useState()
  const [incidents, setIncidents] = useState([])
  const [preference, setPreference] = useState(50)
  const [destinationMode, setDestinationMode] = useState(false), [destinationQuery, setDestinationQuery] = useState('')
  const [gps, setGps] = useState(), watch = useRef()
  const run = async (fn) => { setErr(); try { return await fn() } catch (e) { setErr(e.message) } }

  useEffect(() => { api.recent().then(setIncidents).catch(() => {}) }, [])

  const locate = () => navigator.geolocation
    ? navigator.geolocation.getCurrentPosition((p) => setStart({ latitude: p.coords.latitude, longitude: p.coords.longitude }),
        (e) => setErr(e.code === 1 ? 'Location permission denied. Using Jaipur Junction as the start.' : 'Could not read your location.'))
    : setErr('Geolocation is not supported in this browser.')
  const swapLocations = () => { const nextStart = dest; setDest(start); setStart(nextStart); setDestinationMode(false); setDestinationQuery('') }
  const chooseDestination = (value) => { if (value === '__search__') { setDestinationMode(true); setDestinationQuery(''); return } const next = PLACES.find((p) => p.name === value); if (next) { setDest(next); setDestinationMode(false); setDestinationQuery('') } }
  const typeDestination = (value) => { setDestinationQuery(value); const next = PLACES.find((p) => p.name.toLowerCase() === value.trim().toLowerCase()); if (next) { setDest(next); setDestinationMode(false); setDestinationQuery('') } }
  const search = async () => { if (destinationMode) { setErr('Search destination is not connected to a geocoder. Choose one of the configured destinations to find a route.'); return } setBusy(true); setNote(); const r = await run(() => api.search(start, dest)); setBusy(false)
    if (r) { setRoutes(r.routes); setSel(r.routes.find((x) => x.recommended)?.id); if (!r.routes.length) setErr('No routes found.') } }
  const begin = async () => { const r = await run(() => api.start(sel)); if (r) { setJid(r.journey_id); refresh(r.journey_id)
    if (navigator.geolocation) watch.current = navigator.geolocation.watchPosition((p) => setGps({ latitude: p.coords.latitude, longitude: p.coords.longitude }), () => setNote('Live location is unavailable; using simulated navigation.'))
    else setNote('Live location is unavailable; using simulated navigation.') } }
  const refresh = async (id = jid) => { const s = await run(() => api.status(id)); if (s) setSt(s) }
  useEffect(() => { if (!jid || st?.status === 'completed') return; const t = setInterval(refresh, POLL_MS); return () => clearInterval(t) }, [jid, st?.status])
  useEffect(() => { if (st?.status === 'completed' && watch.current !== undefined) { navigator.geolocation?.clearWatch(watch.current); watch.current = undefined } }, [st?.status])
  useEffect(() => () => { if (watch.current !== undefined) navigator.geolocation?.clearWatch(watch.current) }, [])

  const inject = async () => { const i = await run(() => api.inject(jid)); if (i) setIncidents((current) => [i, ...current]); refresh() }
  const doSwitch = async () => { const s = await run(() => api.switchTo(jid, st.reroute.alternative.id)); if (s) { setSt(s); setNote('Switched to the safer route.') } }
  const keep = async () => { await run(() => api.dismiss(jid)); setNote('Keeping current route.'); refresh() }
  const shown = st ? [{ id: st.route_id, geometry: st.geometry }] : routes

  const selectedRoute = routes.find((r) => r.id === sel)
  const activeRoute = st ? { id: st.route_id, geometry: st.geometry, safety: st.safety, factors: st.factors, distance_m: st.distance_m, progress_m: st.progress_m, eta_min: st.eta_min, incident_count: st.incidents_ahead.length } : selectedRoute
  const navItems = [['⌂', 'Home'], ['⌖', 'Route Planner'], ['◉', 'Live Journey'], ['◈', 'Safety Reports'], ['☆', 'Saved Places'], ['⚙', 'Settings']]

  return (<div className="dashboard">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">✦</span><div><strong>SENTINEL</strong><small>Safe navigation</small></div></div>
      <nav className="sidebar-nav">{navItems.map(([icon, label]) => <div key={label} className={'nav-item' + (label === 'Route Planner' ? ' active' : '')}><span>{icon}</span>{label}</div>)}</nav>
      <div className="sidebar-foot"><div className="avatar">A</div><div><b>Aarav</b><small>Stay safe.</small></div><span className="more">•••</span></div>
    </aside>
    <main className="workspace">
      <header className="topbar"><div><span className="eyebrow">Safety-first navigation</span><h1>{jid ? 'Live journey' : 'Safe route planner'}</h1></div><div className="top-actions"><span className="status-chip"><span className="live-dot" />{jid ? 'Journey active' : 'Ready to plan'}</span><button className="icon-button">?</button></div></header>
      <section className="search-panel">
        <div className="search-fields"><label><span>From</span><div className="field"><span className="field-icon blue">⌖</span><input readOnly value={`${start.latitude.toFixed(4)}, ${start.longitude.toFixed(4)}`} /><button className="locate-button" onClick={locate} title="Use my location">◎</button></div></label><button className="swap-button" onClick={swapLocations} title="Swap locations">⇄</button><label><span>To</span>{destinationMode ? <div className="field destination-search"><span className="field-icon red">●</span><input autoFocus value={destinationQuery} onChange={(e) => typeDestination(e.target.value)} placeholder="Search destination..." /></div> : <div className="field"><span className="field-icon red">●</span><select value={dest.name} onChange={(e) => chooseDestination(e.target.value)}><option value="__search__">Search destination...</option>{PLACES.map((p) => <option key={p.name}>{p.name}</option>)}</select></div>}{destinationMode && <small className="muted destination-note">Only configured destinations can be routed right now.</small>}</label><label className="departure"><span>Depart at</span><div className="field"><span className="field-icon">◷</span><select defaultValue="Now"><option>Now</option><option>Today, later</option></select></div></label><button className="find-button" onClick={search} disabled={busy || Boolean(jid) || destinationMode}>{busy ? 'Finding…' : jid ? 'Route active' : 'Find Safe Routes'} <span>→</span></button></div>
        <div className="preference"><span className="preference-icon">✦</span><div><b>Safety-Time Preference</b><small>Adjust how much you want to prioritise safety vs faster travel.</small></div><div className="preference-control"><span>Faster Travel</span><input type="range" min="0" max="100" value={preference} onChange={(e) => setPreference(e.target.value)} /><span>Safer Travel</span><div className="preference-labels"><small>Shorter time, higher risk</small><strong>{preference < 40 ? 'Faster Travel' : preference > 60 ? 'Safer Travel' : 'Balanced (Recommended)'}</strong><small>May take longer, higher safety</small></div></div></div>
      </section>
      {err && <ErrorState message={err} />}{busy && <LoadingState text="Finding real road routes…" />}
      <section className="dashboard-grid">
        <div className="route-column"><div className="section-heading"><div><span className="eyebrow">Route planning</span><h2>Route Options <em>{routes.length || (jid ? 1 : 0)}</em></h2></div><select className="sort-select" defaultValue="recommended"><option value="recommended">Recommended</option></select></div>{!jid && routes.map((r) => <RouteCard key={r.id} r={r} selected={r.id === sel} onSelect={setSel} />)}{!jid && !routes.length && <div className="empty-card"><span className="empty-icon">⌁</span><b>Find a safe route</b><p>Choose your destination and compare real road routes.</p></div>}{jid && st && <JourneyStatus s={st} />}{!jid && sel && <><SelectedRouteSummary r={selectedRoute} /><button className="start-button" onClick={begin}>START ROUTE <span>→</span></button></>}{jid && st && <><div className="journey-actions">{st.reroute && <RerouteCard rr={st.reroute} onSwitch={doSwitch} onKeep={keep} />}{!st.reroute && st.status !== 'completed' && <WhyNotCard analysis={st.reroute_analysis} />}{note && <p className="muted">{note}</p>}{!st.incidents_ahead.length && st.status !== 'completed' && <p className="muted">No incidents ahead.</p>}<button className="demo-button" onClick={inject}>Demo: inject accident 600 m ahead</button></div></>}</div>
        <div className="map-column"><div className="map-toolbar"><div className="map-tabs"><span className="active">◉ Safety View</span><span>⌖ Safe Points</span><span>◌ Risk Heatmap</span><span>◷ Time Profile</span></div><span className="map-expand">⛶</span></div><MapView routes={shown} selectedId={jid ? st?.route_id : sel} alt={st?.reroute?.alternative} incidents={st?.incidents_ahead || []} heatmapIncidents={incidents} position={gps || st?.position} start={start} dest={dest} /></div>
        <div className="intel-column"><SafetyProfile route={activeRoute} /><SafePointPanel route={activeRoute} /><IndependencePanel routes={routes} /><IncidentSummary incidents={incidents} /></div>
      </section>
      <AnalysisPanel route={activeRoute} incidents={incidents} analysis={st?.reroute_analysis} />
    </main>
  </div>)
}
