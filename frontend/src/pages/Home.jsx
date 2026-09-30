import { useEffect, useRef, useState } from 'react'
import MapView from '../components/MapView.jsx'
import { RouteCard, RerouteCard, JourneyStatus, LoadingState, ErrorState } from '../components/Parts.jsx'
import { api, PLACES, POLL_MS } from '../services/api.js'

const DEFAULT_START = { latitude: 26.9196, longitude: 75.7878 }
const KEYWORDS = ['help', 'bachao', 'save me', 'emergency', 'mujhe bachao', 'stop', 'leave me alone', "don't touch me", 'call the police']

const normalizeText = (value = '') => value.toLowerCase().replace(/\s+/g, ' ').trim()
const keywordMatch = (value = '') => KEYWORDS.some((keyword) => normalizeText(value).includes(normalizeText(keyword)))
const classifyVoiceEmotion = (value = '') => {
  const text = normalizeText(value)
  if (/(angry|gussa|mad|furious|hate|rage)/.test(text)) return 'angry'
  if (/(sad|cry|crying|upset|depressed|afraid|fear)/.test(text)) return 'sad'
  return 'neutral'
}
const encodeWav = (samples, sampleRate = 16000) => {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  const write = (offset, value) => view.setUint32(offset, value, true)
  const write16 = (offset, value) => view.setUint16(offset, value, true)

  write(0, 0x46464952)
  write(4, 36 + samples.length * 2)
  write(8, 0x45564157)
  write(12, 0x20746d66)
  write(16, 16)
  write16(20, 1)
  write16(22, 1)
  write(24, sampleRate)
  write(28, sampleRate * 2)
  write16(32, 2)
  write16(34, 16)
  write(36, 0x61746164)
  write(40, samples.length * 2)

  let offset = 44
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
    offset += 2
  }
  return new Uint8Array(buffer)
}

export default function Home() {
  const [start, setStart] = useState(DEFAULT_START), [dest, setDest] = useState(PLACES[0])
  const [routes, setRoutes] = useState([]), [sel, setSel] = useState(), [busy, setBusy] = useState(false)
  const [err, setErr] = useState(), [jid, setJid] = useState(), [st, setSt] = useState(), [note, setNote] = useState()
  const [sosJourney, setSosJourney] = useState(null), [sosStatus, setSosStatus] = useState(null), [sosNotice, setSosNotice] = useState('')
  const [isListening, setIsListening] = useState(false), [manualTranscript, setManualTranscript] = useState('help me')
  const recognitionRef = useRef(null)
  const audioStreamRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const lastVoiceEventRef = useRef(0)
  const run = async (fn) => { setErr(); try { return await fn() } catch (e) { setErr(e.message) } }

  const stopVoiceMonitoring = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop()
      recognitionRef.current = null
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach((track) => track.stop())
      audioStreamRef.current = null
    }
    setIsListening(false)
  }

  const processTranscript = async (transcript) => {
    const text = (transcript || '').trim()
    if (!text) return

    const now = Date.now()
    if (now - lastVoiceEventRef.current < 2500) return
    lastVoiceEventRef.current = now

    setSosNotice(`Heard: "${text}"`)

    if (/safe|i am safe|i'm safe/.test(normalizeText(text))) {
      await triggerSafetyEvent('SAFE')
      return
    }

    if (keywordMatch(text)) {
      await triggerSafetyEvent('KEYWORD_DETECTED')
      const emotion = await classifyWithFairHindiSER(text)
      if (emotion !== 'neutral') {
        await triggerSafetyEvent('EMOTION_DETECTED', emotion)
      }
    }
  }

  const classifyWithFairHindiSER = async (transcript) => {
    if (!navigator.mediaDevices?.getUserMedia) {
      return classifyVoiceEmotion(transcript)
    }

    try {
      if (!audioStreamRef.current) {
        audioStreamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true })
      }

      const stream = audioStreamRef.current
      const recorder = new MediaRecorder(stream)
      const audioChunks = []
      recorder.ondataavailable = (event) => event.data && audioChunks.push(event.data)

      const recorded = await new Promise((resolve, reject) => {
        recorder.onstop = () => resolve(new Blob(audioChunks, { type: recorder.mimeType || 'audio/webm' }))
        recorder.onerror = () => reject(new Error('Audio capture failed'))
        recorder.start()
        setTimeout(() => recorder.stop(), 2500)
      })

      const arrayBuffer = await recorded.arrayBuffer()
      const audioContext = new (window.AudioContext || window.webkitAudioContext)()
      const decoded = await audioContext.decodeAudioData(arrayBuffer.slice(0))
      const channelData = decoded.getChannelData(0)
      const mono = new Float32Array(channelData.length)
      for (let i = 0; i < channelData.length; i++) mono[i] = channelData[i]
      const wavBytes = encodeWav(mono, decoded.sampleRate || 16000)
      const audioBase64 = btoa(String.fromCharCode(...wavBytes))
      const response = await fetch('/internal/emotion-infer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript, audio_base64: audioBase64, sample_rate: decoded.sampleRate || 16000 })
      })
      const data = await response.json().catch(() => ({}))
      if (response.ok && data.label) return data.label.toLowerCase()
      return classifyVoiceEmotion(transcript)
    } catch (error) {
      console.warn('FairHindiSER inference failed, using transcript fallback', error)
      return classifyVoiceEmotion(transcript)
    }
  }

  const startVoiceMonitoring = async () => {
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('This browser does not support microphone access.')
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      audioStreamRef.current = stream
    } catch (error) {
      setErr(`Microphone permission failed: ${error.message || 'Please allow mic access.'}`)
      setIsListening(false)
      return
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      setErr('This browser does not support the Web Speech API for microphone listening.')
      setIsListening(false)
      return
    }

    const recognition = new SpeechRecognition()
    recognition.lang = 'en-IN'
    recognition.interimResults = false
    recognition.continuous = true

    recognition.onresult = async (event) => {
      const transcript = Array.from(event.results).map((result) => result[0]?.transcript || '').join(' ').trim()
      if (!transcript) return
      await processTranscript(transcript)
    }

    recognition.onerror = (event) => {
      const msg = event.error === 'network' || event.error === 'service-not-allowed'
        ? 'Browser speech recognition is unavailable here. Use the manual transcript box or demo buttons.'
        : `Microphone listening failed: ${event.error}`

      setSosNotice(msg)
      setIsListening(false)
    }

    recognition.onend = () => {
      setIsListening(false)
    }

    recognitionRef.current = recognition
    setIsListening(true)
    try { recognition.start() } catch { setIsListening(false) }
  }

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

  const startSafetyJourney = async () => {
    const payload = await run(() => api.startSafetyMonitor({ user_name: 'Demo User', latitude: start.latitude, longitude: start.longitude }))
    if (!payload) return

    setSosJourney(payload)
    setSosNotice('Safety monitor active. Please allow microphone access.')
    setSosStatus({ risk_level: 'LOW', risk_score: 0, status: 'JOURNEY_ACTIVE', countdown_required: false, countdown_seconds: 0 })
    await startVoiceMonitoring()
  }

  const refreshSafetyJourney = async () => {
    if (!sosJourney) return
    const payload = await run(() => api.safetyStatus(sosJourney.journey_id))
    if (payload) setSosStatus(payload)
  }

  const triggerSafetyEvent = async (signal_type, emotion) => {
    if (!sosJourney) return
    const payload = await run(() => api.signal({ journey_id: sosJourney.journey_id, signal_type, latitude: start.latitude, longitude: start.longitude, emotion }))
    if (payload) { setSosStatus(payload); setSosNotice(`${signal_type} recorded.`) }
  }

  const triggerManualSos = async () => {
    if (!sosJourney) return
    stopVoiceMonitoring()
    const payload = await run(() => api.createEmergency({ journey_id: sosJourney.journey_id, trigger_type: 'MANUAL', latitude: start.latitude, longitude: start.longitude }))
    if (payload) { setSosStatus({ ...payload, status: 'EMERGENCY_ACTIVE' }); setSosNotice('Manual SOS created.') }
  }

  useEffect(() => {
    if (!sosJourney) return
    const id = setInterval(refreshSafetyJourney, 4000)
    return () => clearInterval(id)
  }, [sosJourney])

  useEffect(() => () => stopVoiceMonitoring(), [])

  const shown = st ? [{ id: st.route_id, geometry: st.geometry }] : routes

  return (<div className="app">
    <aside>
      <h1>SENTINEL</h1><p className="muted">Safe routes that adapt while you travel.</p>
      <div className="card">
        <h3>Intelligent SOS</h3>
        {!sosJourney && <button className="primary" onClick={startSafetyJourney}>Activate safety monitor</button>}
        {sosJourney && <div>
          <p className="muted">Journey: {sosJourney.journey_id} · {sosStatus?.status || 'JOURNEY_ACTIVE'}</p>
          <div className="row"><span className="tag">Risk: {sosStatus?.risk_level || 'LOW'}</span><span className="tag">{sosStatus?.risk_score || 0}</span></div>
          {sosStatus?.countdown_required && <div className="alert"><strong>POSSIBLE EMERGENCY DETECTED</strong><p className="muted">Are you safe? Automatic SOS in {sosStatus.countdown_seconds}s</p></div>}
          <div className="row"><button onClick={() => triggerSafetyEvent('KEYWORD_DETECTED')}>Keyword</button><button onClick={() => triggerSafetyEvent('FALL_DETECTED')}>Fall</button></div>
          <div className="row"><button onClick={() => triggerSafetyEvent('EMOTION_DETECTED', 'angry')}>Angry voice</button><button onClick={() => triggerSafetyEvent('SAFE')}>I'm safe</button></div>
          <button className="primary" onClick={triggerManualSos}>Manual SOS</button>
          <button onClick={isListening ? stopVoiceMonitoring : startVoiceMonitoring}>{isListening ? 'Stop mic' : 'Start mic'}</button>
          <div className="row"><input value={manualTranscript} onChange={(e) => setManualTranscript(e.target.value)} placeholder="Type a phrase like 'help me'" /><button onClick={() => processTranscript(manualTranscript)}>Use transcript</button></div>
        </div>}
        {sosNotice && <p className="muted">{sosNotice}</p>}
      </div>
      {!jid && <div className="card">
        <label>From</label><div className="row"><input readOnly value={`${start.latitude.toFixed(4)}, ${start.longitude.toFixed(4)}`} /><button onClick={locate}>Use my location</button></div>
        <label>To</label><select value={dest.name} onChange={(e) => setDest(PLACES.find((p) => p.name === e.target.value))}>{PLACES.map((p) => <option key={p.name}>{p.name}</option>)}</select>
        <button className="primary" onClick={search} disabled={busy}>Search safe routes</button></div>}
      {err && <ErrorState message={err} />}{busy && <LoadingState text="Finding routes..." />}
      {!jid && routes.map((r) => <RouteCard key={r.id} r={r} selected={r.id === sel} onSelect={setSel} />)}
      {!jid && sel && <button className="primary" onClick={begin}>Start journey</button>}
      {jid && st && <div>
        <JourneyStatus s={st} />
        {st.reroute && <RerouteCard rr={st.reroute} onSwitch={doSwitch} onKeep={keep} />}
        {note && <p className="muted">{note}</p>}
        {!st.incidents_ahead.length && st.status !== 'completed' && <p className="muted">No incidents ahead.</p>}
        <button onClick={inject}>Demo: inject accident 600 m ahead</button>
      </div>}
    </aside>
    <MapView routes={shown} selectedId={jid ? st?.route_id : sel} alt={st?.reroute?.alternative} incidents={st?.incidents_ahead || []}
      position={st?.position} start={start} dest={dest} />
  </div>)
}
