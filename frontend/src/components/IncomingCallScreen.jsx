import { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { Phone } from 'lucide-react'

const CALLER_NAME = 'Mom'
const CALLER_NUMBER = '+91 98765 43210'

export default function IncomingCallScreen({ onDismiss }) {
  const audioRef = useRef(null)

  useEffect(() => {
    const dismiss = (event) => {
      if (event.type === 'keydown' && event.key !== 'Escape') return
      onDismiss()
    }
    window.addEventListener('keydown', dismiss)
    window.history.pushState({ incomingCall: true }, '')
    window.addEventListener('popstate', dismiss)
    audioRef.current?.play().catch(() => {})
    return () => {
      window.removeEventListener('keydown', dismiss)
      window.removeEventListener('popstate', dismiss)
      audioRef.current?.pause()
    }
  }, [onDismiss])

  const dismiss = () => {
    audioRef.current?.pause()
    onDismiss()
  }

  return (
    <div className="incoming-call" role="dialog" aria-modal="true" aria-label="Incoming call">
      {/* TODO: Make caller details configurable in safety settings. */}
      <audio ref={audioRef} src="/ringtone.mp3" autoPlay loop />
      <div className="incoming-call-content">
        <motion.div
          className="caller-avatar"
          animate={{ scale: [1, 1.08, 1], opacity: [0.9, 1, 0.9] }}
          transition={{ duration: 1.8, repeat: Infinity }}
        >
          M
        </motion.div>
        <p className="incoming-label">Incoming call</p>
        <h1>{CALLER_NAME}</h1>
        <p className="caller-number">{CALLER_NUMBER}</p>
        <p className="caller-type">Mobile</p>
      </div>
      <div className="call-actions">
        <button type="button" className="call-action decline" onClick={dismiss} aria-label="Decline call">
          <Phone />
          <span>Decline</span>
        </button>
        <button type="button" className="call-action answer" onClick={dismiss} aria-label="Answer call">
          <Phone />
          <span>Answer</span>
        </button>
      </div>
    </div>
  )
}
