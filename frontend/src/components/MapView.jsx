import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const ll = (p) => [p.latitude, p.longitude]
const heatColor = (severity) => severity >= .75 ? '#ff4d4f' : severity >= .45 ? '#f5a524' : '#4aa3ff'
export default function MapView({ routes = [], selectedId, alt, incidents = [], heatmapIncidents = [], position, start, dest }) {
  const el = useRef(), map = useRef(), layer = useRef()
  useEffect(() => {
    if (!el.current) return undefined
    map.current = L.map(el.current, { zoomControl: true }).setView([26.92, 75.81], 12)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap', maxZoom: 19 }).addTo(map.current)
    layer.current = L.layerGroup().addTo(map.current)
    const frame = requestAnimationFrame(() => map.current?.invalidateSize())
    const resize = new ResizeObserver(() => map.current?.invalidateSize())
    resize.observe(el.current)
    return () => { cancelAnimationFrame(frame); resize.disconnect(); map.current?.remove(); map.current = undefined; layer.current = undefined }
  }, [])
  useEffect(() => {
    if (!map.current || !layer.current) return
    const g = layer.current; g.clearLayers()
    const all = []
    routes.forEach((r) => { const sel = r.id === selectedId
      const geometry = (r.geometry || []).filter((p) => Array.isArray(p) && p.length >= 2 && Number.isFinite(Number(p[0])) && Number.isFinite(Number(p[1]))).map(([lat, lon]) => [Number(lat), Number(lon)])
      if (geometry.length < 2) return
      const pl = L.polyline(geometry, { color: sel ? '#f5a524' : '#6b7a90', weight: sel ? 6 : 3, opacity: sel ? 1 : .6 }).bindTooltip(sel ? 'Selected route' : 'Alternative route').addTo(g); all.push(pl) })
    if (alt?.geometry?.length >= 2) L.polyline(alt.geometry, { color: '#3ddc97', weight: 6, dashArray: '8 8' }).bindTooltip('Safer alternative').addTo(g)
    heatmapIncidents.forEach((i) => {
      const severity = Number(i.severity) || 0
      const confidence = Number(i.confidence) || 0
      L.circle(ll(i), { radius: 180 + severity * 420, color: heatColor(severity), weight: 1, opacity: .35, fillColor: heatColor(severity), fillOpacity: .08 + confidence * .16 })
        .bindTooltip(`${i.title} · severity ${Math.round(severity * 100)}% · confidence ${Math.round(confidence * 100)}%`).addTo(g)
    })
    incidents.forEach((i) => {
      L.circle(ll(i), { radius: 500, color: '#ff4d4f', weight: 1, fillOpacity: .12 }).addTo(g)
      L.circleMarker(ll(i), { radius: 9, color: '#fff', fillColor: '#ff4d4f', fillOpacity: 1 }).bindTooltip(i.title).addTo(g) })
    if (start) L.circleMarker(ll(start), { radius: 7, color: '#fff', fillColor: '#4aa3ff', fillOpacity: 1 }).bindTooltip('Start').addTo(g)
    if (dest) L.circleMarker(ll(dest), { radius: 7, color: '#fff', fillColor: '#f5a524', fillOpacity: 1 }).bindTooltip('Destination').addTo(g)
    if (position) L.circleMarker(ll(position), { radius: 9, color: '#fff', weight: 3, fillColor: '#4aa3ff', fillOpacity: 1 }).bindTooltip('You').addTo(g)
    if (all.length && !position) map.current.fitBounds(L.featureGroup(all).getBounds(), { padding: [30, 30], maxZoom: 15 })
    map.current.invalidateSize()
  }, [routes, selectedId, alt, incidents, heatmapIncidents, position, start, dest])
  return <div className="map-shell"><div ref={el} className="map" style={{ height: '100%', minHeight: 300 }} /><div className="map-key"><b>Map signals</b><span><i className="key-dot incident" />Reported incident intensity</span><span><i className="key-line route" />Selected route</span><span><i className="key-line safer" />Safer alternative</span></div></div>
}
