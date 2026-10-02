import { useState } from 'react'
import { MessageCircle, X } from 'lucide-react'
import { Button } from './ui/button.jsx'

const compactFactors = (factors = {}) => {
  const keys = ['lighting', 'crowd', 'traffic', 'connectivity', 'safe_locations', 'historical_crime']
  return Object.fromEntries(keys.filter((key) => factors[key] != null).map((key) => [key, factors[key]]))
}

export function buildAssistantContext({
  sosJourney,
  sosStatus,
  navJourneyId,
  selectedRoute,
  journeyStatus,
  dest,
  start,
  livePoint,
  safePoints,
  userName,
} = {}) {
  const route = journeyStatus || selectedRoute
  const factors = livePoint?.factors || route?.factors || {}
  return {
    user_name: userName || undefined,
    safety_monitor_active: Boolean(sosJourney),
    sos_status: sosStatus?.status || (sosJourney ? 'JOURNEY_ACTIVE' : 'inactive'),
    emergency_active: sosStatus?.status === 'EMERGENCY_ACTIVE',
    sos_trigger: sosStatus?.sos_trigger || sosStatus?.trigger_type || null,
    email_status: sosStatus?.email_status || null,
    help_on_the_way: sosStatus?.status === 'EMERGENCY_ACTIVE' && (sosStatus?.email_status === 'sent' || sosStatus?.help_alerted),
    guardian_count: sosStatus?.guardian_count ?? null,
    trigger_reasons: sosStatus?.trigger_reasons || [],
    risk_score: sosJourney ? Number(sosStatus?.risk_score ?? 0) : null,
    risk_level: sosJourney ? (sosStatus?.risk_level || 'LOW') : null,
    destination_name: dest?.name || null,
    origin: start ? { latitude: start.latitude, longitude: start.longitude } : null,
    route_safety: livePoint?.safety ?? route?.safety ?? null,
    route_factors: compactFactors(factors),
    eta_min: route?.eta_min ?? null,
    distance_m: route?.distance_m ?? null,
    progress_m: journeyStatus?.progress_m ?? null,
    journey_status: journeyStatus?.status || (route ? 'planned' : 'no_route'),
    incidents_ahead: (journeyStatus?.incidents_ahead || []).slice(0, 5).map((item) => ({
      title: item.title,
      type: item.type,
      distance_ahead_m: item.distance_ahead_m,
      eta_min: item.eta_min,
    })),
    nearby_safe_places: (safePoints || []).slice(0, 5).map((point) => ({ name: point.name, kind: point.kind })),
    live_location_label: livePoint?.crime?.city || livePoint?.crime?.district || null,
    navigation_active: Boolean(navJourneyId),
  }
}

export default function SafetyAssistantPanel(props) {
  const { sosJourney, navJourneyId, selectedRoute } = props
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    const question = input.trim()
    if (!question || sending) return
    setMessages((current) => [...current, { role: 'user', text: question }])
    setInput('')
    setSending(true)
    try {
      const response = await fetch('/assistant/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          journey_id: sosJourney?.journey_id,
          nav_journey_id: navJourneyId,
          route_id: selectedRoute?.id,
          context: buildAssistantContext(props),
        }),
      })
      if (!response.ok) throw new Error('Assistant request failed')
      const payload = await response.json()
      setMessages((current) => [...current, { role: 'assistant', text: payload.answer }])
    } catch {
      setMessages((current) => [...current, {
        role: 'assistant',
        text: 'Something went wrong reaching the assistant. Please try again.',
      }])
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      {open && (
        <section className="assistant-panel" aria-label="Safety assistant">
          <header>
            <div><strong>Safety assistant</strong><small>Ask about your current risk</small></div>
            <button type="button" className="icon-button" onClick={() => setOpen(false)} aria-label="Close assistant"><X /></button>
          </header>
          <div className="assistant-messages" aria-live="polite">
            {!messages.length && <p className="assistant-empty">How can I help you understand your current safety status?</p>}
            {messages.map((message, index) => <p key={`${message.role}-${index}`} className={`assistant-message ${message.role}`}>{message.text}</p>)}
            {sending && <p className="assistant-message assistant">Checking your current safety data...</p>}
          </div>
          <form onSubmit={submit}>
            <input value={input} onChange={(event) => setInput(event.target.value)} disabled={sending} placeholder="Ask a safety question" aria-label="Safety question" />
            <Button type="submit" disabled={sending || !input.trim()}>Send</Button>
          </form>
        </section>
      )}
      <Button type="button" className="assistant-fab" size="icon-lg" onClick={() => setOpen((value) => !value)} aria-label={open ? 'Close safety assistant' : 'Open safety assistant'}>
        {open ? <X /> : <MessageCircle />}
      </Button>
    </>
  )
}
