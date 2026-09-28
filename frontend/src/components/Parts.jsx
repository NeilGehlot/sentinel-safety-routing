export const SafetyScore = ({ value }) => <span className={'score ' + (value >= 75 ? 'ok' : value >= 60 ? 'mid' : 'bad')}>{Math.round(value)}</span>
export const LoadingState = ({ text = 'Working…' }) => <p className="muted">{text}</p>
export const ErrorState = ({ message, onRetry }) => <div className="err">{message}{onRetry && <button onClick={onRetry}>Try again</button>}</div>
export const SafetyFactorList = ({ factors }) => (
  <ul className="factors">{Object.entries(factors || {}).map(([k, v]) =>
    <li key={k}><span>{k.replace('_', ' ')}</span><i><b style={{ width: v + '%' }} /></i><em>{v}</em></li>)}</ul>)
export const RouteCard = ({ r, selected, onSelect }) => (
  <div className={'card route' + (selected ? ' sel' : '')} onClick={() => onSelect(r.id)}>
    {r.recommended && <span className="tag">Recommended</span>}
    <div className="row"><SafetyScore value={r.safety} /><div><b>Safety {Math.round(r.safety)}/100</b>
      <div className="muted">ETA {Math.round(r.eta_min)} min · {(r.distance_m / 1000).toFixed(1)} km · {r.incident_count} incidents</div></div></div>
    {selected && <SafetyFactorList factors={r.factors} />}
  </div>)
export const RerouteCard = ({ rr, onSwitch, onKeep }) => (
  <div className="card alert">
    <h3>Route update</h3>
    <p>Current route: safety {Math.round(rr.current_safety)}, ETA {Math.round(rr.current_eta_min)} min<br />
      Alternative: safety {Math.round(rr.alternative.safety)}, ETA {Math.round(rr.alternative.eta_min)} min</p>
    <ul>{rr.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
    <div className="row"><button className="primary" onClick={onSwitch}>Switch to safer route</button><button onClick={onKeep}>Keep current route</button></div>
  </div>)
export const JourneyStatus = ({ s }) => (
  <div className="card"><div className="row"><SafetyScore value={s.safety} /><b>{s.status.replace('_', ' ')}</b></div>
    <div className="muted">ETA {Math.round(s.eta_min)} min · {s.incidents_ahead.length} incident(s) ahead
      {s.incidents_ahead[0] && ` · nearest ${s.incidents_ahead[0].distance_ahead_m} m`}</div>
    {s.status === 'completed' && <p><b>You have arrived.</b></p>}
    <SafetyFactorList factors={s.factors} /></div>)
