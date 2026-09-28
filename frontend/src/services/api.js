const j = async (r) => { if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Request failed (${r.status})`); return r.json() }
const post = (u, b) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b || {}) }).then(j)
export const api = {
  search: (start, destination) => post('/api/routes/search', { start, destination }),
  start: (route_id) => post('/api/navigation/start', { route_id }),
  status: (id) => fetch(`/api/navigation/${id}/status`).then(j),
  inject: (journey_id) => post('/api/demo/inject-incident', { journey_id }),
  switchTo: (id, alt) => post(`/api/navigation/${id}/switch`, { alternative_route_id: alt }),
  dismiss: (id) => post(`/api/navigation/${id}/dismiss`),
}
export const PLACES = [
  { name: 'Amber Fort', latitude: 26.9855, longitude: 75.8513 },
  { name: 'Hawa Mahal', latitude: 26.9239, longitude: 75.8267 },
  { name: 'Albert Hall Museum', latitude: 26.9116, longitude: 75.8195 },
  { name: 'Jal Mahal', latitude: 26.9533, longitude: 75.8462 },
]
export const POLL_MS = (Number(import.meta.env.VITE_POLLING_INTERVAL_SECONDS) || 10) * 1000
