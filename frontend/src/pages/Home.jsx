import { useEffect, useState } from 'react'
import MapView from '../components/MapView.jsx'
import { RouteCard, RerouteCard, JourneyStatus, LoadingState, ErrorState } from '../components/Parts.jsx'
import { api, PLACES, POLL_MS } from '../services/api.js'

const DEFAULT_START = { latitude: 26.9196, longitude: 75.7878 }
export default function Home() {
  const [start, setStart] = useState(DEFAULT_START), [dest, setDest] = useState(PLACES[0])
  const [routes, setRoutes] = useState([]), [sel, setSel] = useState(), [busy, setBusy] = useState(false)
  const [err, setErr] = useState(), [jid, setJid] = useState(), [st, setSt] = useState(), [note, setNote] = useState()
  const run = async (fn) => { setErr(); try { return await fn() } catch (e) { setErr(e.message) } }

  const locate = () => navigator.geolocation
    ? navigator.geolocation.getCurrentPosition((p) => setStart({ latitude: p.coords.latitude, longitude: p.coords.longitude }),
        (e) => setErr(e.code === 1 ? 'Location permission denied. Using Jaipur Junction as the start.' : 'Could not read your location.'))
    : setErr('Geolocation is not supported in this browser.')
  const search = async () => { setBusy(true); setNote(); const r = await run(() => api.search(start, dest)); setBusy(false)
    if (r) { setRoutes(r.routes); setSel(r.routes.find((x) => x.recommended)?.id); if (!r.routes.length) setErr('No routes found.') } }
  const begin = async () => { const r = await run(() => api.start(sel)); if (r) { setJid(r.journey_id); refresh(r.journey_id) } }
  const refresh = async (id = jid) => { const s = await run(() => api.status(id)); if (s) setSt(s) }
  useEffect(() => { if (!jid || st?.status === 'completed') return; const t = setInterval(refresh, POLL_MS); return () => clearInterval(t) }, [jid, st?.status])

  const inject = async () => { await run(() => api.inject(jid)); refresh() }
  const doSwitch = async () => { const s = await run(() => api.switchTo(jid, st.reroute.alternative.id)); if (s) { setSt(s); setNote('Switched to the safer route.') } }
  const keep = async () => { await run(() => api.dismiss(jid)); setNote('Keeping current route.'); refresh() }
  const shown = st ? [{ id: st.route_id, geometry: st.geometry }] : routes

  return (<div className="app">
    <aside>
      <h1>SENTINEL</h1><p className="muted">Safe routes that adapt while you travel.</p>
      {!jid && <div className="card">
        <label>From</label><div className="row"><input readOnly value={`${start.latitude.toFixed(4)}, ${start.longitude.toFixed(4)}`} /><button onClick={locate}>Use my location</button></div>
        <label>To</label><select value={dest.name} onChange={(e) => setDest(PLACES.find((p) => p.name === e.target.value))}>{PLACES.map((p) => <option key={p.name}>{p.name}</option>)}</select>
        <button className="primary" onClick={search} disabled={busy}>Search safe routes</button></div>}
      {err && <ErrorState message={err} />}{busy && <LoadingState text="Finding routes…" />}
      {!jid && routes.map((r) => <RouteCard key={r.id} r={r} selected={r.id === sel} onSelect={setSel} />)}
      {!jid && sel && <button className="primary" onClick={begin}>Start journey</button>}
      {jid && st && <><JourneyStatus s={st} />
        {st.reroute && <RerouteCard rr={st.reroute} onSwitch={doSwitch} onKeep={keep} />}
        {note && <p className="muted">{note}</p>}
        {!st.incidents_ahead.length && st.status !== 'completed' && <p className="muted">No incidents ahead.</p>}
        <button onClick={inject}>Demo: inject accident 600 m ahead</button></>}
    </aside>
    <MapView routes={shown} selectedId={jid ? st?.route_id : sel} alt={st?.reroute?.alternative} incidents={st?.incidents_ahead || []}
      position={st?.position} start={start} dest={dest} />
  </div>)
}
