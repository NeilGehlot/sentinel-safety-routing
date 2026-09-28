import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const ll = (p) => [p.latitude, p.longitude]
export default function MapView({ routes = [], selectedId, alt, incidents = [], position, start, dest }) {
  const el = useRef(), map = useRef(), layer = useRef()
  useEffect(() => {
    map.current = L.map(el.current).setView([26.92, 75.81], 12)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OpenStreetMap' }).addTo(map.current)
    layer.current = L.layerGroup().addTo(map.current)
    return () => map.current.remove()
  }, [])
  useEffect(() => {
    const g = layer.current; g.clearLayers()
    const all = []
    routes.forEach((r) => { const sel = r.id === selectedId
      const pl = L.polyline(r.geometry, { color: sel ? '#f5a524' : '#6b7a90', weight: sel ? 6 : 3, opacity: sel ? 1 : .6 }).addTo(g); all.push(pl) })
    if (alt) L.polyline(alt.geometry, { color: '#3ddc97', weight: 6, dashArray: '8 8' }).addTo(g)
    incidents.forEach((i) => {
      L.circle(ll(i), { radius: 500, color: '#ff4d4f', weight: 1, fillOpacity: .12 }).addTo(g)
      L.circleMarker(ll(i), { radius: 9, color: '#fff', fillColor: '#ff4d4f', fillOpacity: 1 }).bindTooltip(i.title).addTo(g) })
    if (start) L.circleMarker(ll(start), { radius: 7, color: '#fff', fillColor: '#4aa3ff', fillOpacity: 1 }).bindTooltip('Start').addTo(g)
    if (dest) L.circleMarker(ll(dest), { radius: 7, color: '#fff', fillColor: '#f5a524', fillOpacity: 1 }).bindTooltip('Destination').addTo(g)
    if (position) L.circleMarker(ll(position), { radius: 9, color: '#fff', weight: 3, fillColor: '#4aa3ff', fillOpacity: 1 }).bindTooltip('You').addTo(g)
    if (all.length && !position) map.current.fitBounds(L.featureGroup(all).getBounds(), { padding: [30, 30] })
  }, [routes, selectedId, alt, incidents, position, start, dest])
  return <div ref={el} className="map" />
}
