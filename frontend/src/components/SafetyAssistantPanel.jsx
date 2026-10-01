import { useState } from 'react'
import { MessageCircle, X } from 'lucide-react'
import { Button } from './ui/button.jsx'

export default function SafetyAssistantPanel({ sosJourney }) {
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
        body: JSON.stringify({ question, journey_id: sosJourney?.journey_id }),
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
