import { useEffect, useRef, useState } from 'react'
import MapView from '../components/MapView.jsx'
import { RouteCard, SelectedRouteSummary, RerouteCard, WhyNotCard, IncidentSummary, SafetyProfile, SafePointPanel, IndependencePanel, AnalysisPanel, JourneyStatus, LoadingState, ErrorState } from '../components/Parts.jsx'
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
  const [incidents, setIncidents] = useState([])
  const [preference, setPreference] = useState(50)
  const [destinationMode, setDestinationMode] = useState(false), [destinationQuery, setDestinationQuery] = useState('')
  const [gps, setGps] = useState(), watch = useRef()
  const [sosJourney, setSosJourney] = useState(null), [sosStatus, setSosStatus] = useState(null), [sosNotice, setSosNotice] = useState('')
  const [isListening, setIsListening] = useState(false), [manualTranscript, setManualTranscript] = useState('help me')
  const [liveTranscript, setLiveTranscript] = useState('')
  const [activeNav, setActiveNav] = useState('Route Planner')
  const [currentPage, setCurrentPage] = useState('home')
  const [guardianEmails, setGuardianEmails] = useState([])
  const [emergencyContacts, setEmergencyContacts] = useState([
    { label: 'Police', number: '112' },
    { label: 'Ambulance', number: '108' }
  ])
  const [emergencyProfile, setEmergencyProfile] = useState({
    name: '',
    address: '',
    blood_type: '',
    allergies: '',
    medical_conditions: '',
  })
  const [locationUpdateMinutes, setLocationUpdateMinutes] = useState(5)
  const [settingsSavedMessage, setSettingsSavedMessage] = useState('')
  const [countdownOpen, setCountdownOpen] = useState(false)
  const [countdownSeconds, setCountdownSeconds] = useState(10)
  const recognitionRef = useRef(null)
  const audioStreamRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const lastVoiceEventRef = useRef(0)
  const countdownTriggeredRef = useRef(false)
  const run = async (fn) => { setErr(); try { return await fn() } catch (e) { setErr(e.message) } }

  useEffect(() => { api.recent().then(setIncidents).catch(() => {}) }, [])
  useEffect(() => {
    const loadSettings = async () => {
      const settings = await run(() => api.getGuardianSettings())
      if (!settings) return
      const emails = Array.isArray(settings.guardian_emails) ? settings.guardian_emails : []
      const contacts = Array.isArray(settings.emergency_contacts) && settings.emergency_contacts.length
        ? settings.emergency_contacts
        : [{ label: 'Police', number: '112' }, { label: 'Ambulance', number: '108' }]
      setGuardianEmails(emails.slice(0, 2))
      setEmergencyContacts(contacts.slice(0, 2).map((item) => ({ label: item.label || 'Emergency', number: item.number || '' })))
      setEmergencyProfile({
        name: settings.emergency_profile?.name || '',
        address: settings.emergency_profile?.address || '',
        blood_type: settings.emergency_profile?.blood_type || '',
        allergies: settings.emergency_profile?.allergies || '',
        medical_conditions: settings.emergency_profile?.medical_conditions || '',
      })
      setLocationUpdateMinutes(Number(settings.location_update_interval_minutes) || 5)
    }
    loadSettings()
  }, [])

  const validGuardianEmails = guardianEmails.map((email) => (email || '').trim()).filter(Boolean)
  const validEmergencyContacts = emergencyContacts.filter((c) => (c.number || '').trim())

  const saveSettings = async () => {
    const cleanEmails = guardianEmails.map((email) => (email || '').trim()).filter(Boolean)
    if (cleanEmails.length < 2) {
      setSosNotice('Add guardian emails in Settings before enabling the safety monitor.')
      setSettingsSavedMessage('Need two guardian emails.')
      setCurrentPage('settings')
      setActiveNav('Settings')
      return
    }

    const payload = {
      guardian_emails: cleanEmails.slice(0, 2),
      location_update_interval_minutes: Number(locationUpdateMinutes) || 5,
      emergency_contacts: emergencyContacts
        .map((item) => ({ label: item.label || 'Emergency', number: String(item.number || '').trim() }))
        .filter((item) => item.number),
      emergency_profile: {
        ...emergencyProfile,
        name: (emergencyProfile.name || '').trim(),
        address: (emergencyProfile.address || '').trim(),
        blood_type: (emergencyProfile.blood_type || '').trim(),
        allergies: (emergencyProfile.allergies || '').trim(),
        medical_conditions: (emergencyProfile.medical_conditions || '').trim(),
      }
    }

    const saved = await run(() => api.saveGuardianSettings(payload))
    if (!saved) return
    setGuardianEmails(saved.guardian_emails || cleanEmails.slice(0, 2))
    setEmergencyContacts((saved.emergency_contacts || []).map((item) => ({ label: item.label || 'Emergency', number: item.number || '' })))
    setEmergencyProfile({
      name: saved.emergency_profile?.name || '',
      address: saved.emergency_profile?.address || '',
      blood_type: saved.emergency_profile?.blood_type || '',
      allergies: saved.emergency_profile?.allergies || '',
      medical_conditions: saved.emergency_profile?.medical_conditions || '',
    })
    setLocationUpdateMinutes(Number(saved.location_update_interval_minutes) || 5)
    setSettingsSavedMessage('Settings saved.')
    setSosNotice(`Guardian alerts configured for ${cleanEmails.join(', ')}.`)
    setCurrentPage('home')
    setActiveNav('Route Planner')
  }

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

  const ensureGuardiansConfigured = () => {
    if (validGuardianEmails.length < 2) {
      setCurrentPage('settings')
      setActiveNav('Settings')
      setSosNotice('Add guardian emails in Settings before enabling the safety monitor.')
      return false
    }
    return true
  }

  const shareGuardianLocation = () => {
    if (!sosJourney || validGuardianEmails.length === 0) return
    const recipients = validGuardianEmails.join(', ')
    setSosNotice(`SOS location shared to ${recipients}. Help contacted and is on the way.`)
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
      mediaRecorderRef.current = recorder
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
    setLiveTranscript('')

    if (!navigator.mediaDevices?.getUserMedia) {
      setSosNotice('Microphone access is unavailable in this browser. Use the manual transcript box or demo buttons instead.')
      setIsListening(false)
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      audioStreamRef.current = stream
    } catch (error) {
      setSosNotice(`Microphone permission is blocked: ${error.message || 'allow mic access to enable live voice detection.'}`)
      setIsListening(false)
      return
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SpeechRecognition) {
      setSosNotice('Browser speech recognition is unavailable here. The app is in transcript fallback mode, so you can still trigger SOS manually.')
      setIsListening(false)
      return
    }

    const recognition = new SpeechRecognition()
    recognition.lang = 'en-IN'
    recognition.interimResults = true
    recognition.continuous = true

    recognition.onresult = async (event) => {
      const results = Array.from(event.results)
      const interim = results.map((result) => result[0]?.transcript || '').join(' ').trim()
      const finalText = results.filter((result) => result.isFinal).map((result) => result[0]?.transcript || '').join(' ').trim()

      setLiveTranscript(interim || finalText)

      if (finalText) {
        await processTranscript(finalText)
      }
    }

    recognition.onerror = (event) => {
      const fallbackMessages = ['network', 'service-not-allowed', 'not-allowed', 'audio-capture', 'no-speech']
      const msg = fallbackMessages.includes(event.error)
        ? 'Browser speech recognition is unavailable here. The manual transcript box and demo buttons are still active.'
        : `Microphone listening failed: ${event.error}`

      setSosNotice(msg)
      setIsListening(false)
      setLiveTranscript('')
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

  const startSafetyJourney = async () => {
    if (!ensureGuardiansConfigured()) return

    const payload = await run(() => api.startSafetyMonitor({ user_name: 'Demo User', latitude: start.latitude, longitude: start.longitude }))
    if (!payload) return

    setSosJourney(payload)
    setSosNotice('Safety monitor active. Please allow microphone access.')
    setSosStatus({ risk_level: 'LOW', risk_score: 0, status: 'JOURNEY_ACTIVE', countdown_required: false, countdown_seconds: 0 })
    countdownTriggeredRef.current = false
    await startVoiceMonitoring()
  }

  const refreshSafetyJourney = async () => {
    if (!sosJourney) return
    const payload = await run(() => api.safetyStatus(sosJourney.journey_id))
    if (payload) setSosStatus(payload)
  }

  const triggerSafetyEvent = async (signal_type, emotion) => {
    if (!sosJourney) return
    if (sosStatus?.status === 'EMERGENCY_ACTIVE' && signal_type !== 'SAFE') return
    const payload = await run(() => api.signal({ journey_id: sosJourney.journey_id, signal_type, latitude: start.latitude, longitude: start.longitude, emotion }))
    if (payload) {
      if (signal_type === 'SAFE') {
        setSosStatus({ ...payload, status: 'JOURNEY_ACTIVE', risk_score: 0, risk_level: 'LOW', countdown_required: false, countdown_seconds: 0 })
        setCountdownOpen(false)
        setCountdownSeconds(0)
        countdownTriggeredRef.current = true
        setSosNotice('Status reset to safe. SOS cleared.')
        return
      }
      if (payload?.status === 'EMERGENCY_ACTIVE' || payload?.risk_score === 0) {
        setSosStatus({ ...payload, status: 'EMERGENCY_ACTIVE', risk_score: 0, risk_level: 'LOW', countdown_required: false, countdown_seconds: 0 })
        setCountdownOpen(false)
        setCountdownSeconds(0)
        countdownTriggeredRef.current = true
        setSosNotice('SOS ACTIVATED — Help contacted and is on the way.')
        return
      }
      setSosStatus(payload)
      setSosNotice(`${signal_type} recorded.`)
      if (payload?.risk_score >= 60 && !countdownOpen) {
        setCountdownOpen(true)
        setCountdownSeconds(Number(payload?.countdown_seconds) || 10)
      }
      if (payload?.risk_score >= 60 && !countdownTriggeredRef.current && payload?.countdown_required) {
        countdownTriggeredRef.current = false
      }
      if (payload?.risk_score >= 60 && payload?.countdown_required === false) {
        setCountdownOpen(false)
        setCountdownSeconds(0)
      }
    }
  }

  const triggerManualSos = async () => {
    if (!sosJourney || sosStatus?.status === 'EMERGENCY_ACTIVE') return
    stopVoiceMonitoring()
    const recipients = validGuardianEmails.length ? validGuardianEmails.join(', ') : 'guardian contacts'
    const payload = await run(() => api.createEmergency({ journey_id: sosJourney.journey_id, trigger_type: 'MANUAL', latitude: start.latitude, longitude: start.longitude }))
    if (payload) {
      setSosStatus({ ...payload, status: 'EMERGENCY_ACTIVE', risk_score: 0, risk_level: 'LOW', countdown_required: false, countdown_seconds: 0 })
      setSosNotice(`SOS ACTIVATED — help contacted and is on the way. Alerts sent to ${recipients}.`)
      setCountdownOpen(false)
      setCountdownSeconds(0)
      countdownTriggeredRef.current = true
      shareGuardianLocation()
    }
  }

  const isEmergencyActive = Boolean(sosJourney && sosStatus?.status === 'EMERGENCY_ACTIVE')
  const hideActionButtons = isEmergencyActive
  const riskDisplayValue = Number(sosStatus?.risk_score ?? 0)

  const handleSafeResponse = async () => {
    if (sosStatus?.status === 'EMERGENCY_ACTIVE') return
    setCountdownOpen(false)
    setCountdownSeconds(0)
    countdownTriggeredRef.current = true
    await triggerSafetyEvent('SAFE')
  }

  useEffect(() => {
    if (!sosJourney) return
    const id = setInterval(refreshSafetyJourney, 4000)
    return () => clearInterval(id)
  }, [sosJourney])

  useEffect(() => {
    if (!sosJourney) {
      setCountdownOpen(false)
      setCountdownSeconds(10)
      return
    }
    const required = Boolean(sosStatus?.countdown_required)
    setCountdownOpen(required)
    if (required) {
      setCountdownSeconds(Number(sosStatus?.countdown_seconds) || 10)
      countdownTriggeredRef.current = false
    }
  }, [sosJourney, sosStatus?.countdown_required, sosStatus?.countdown_seconds])

  useEffect(() => {
    if (!countdownOpen || !sosJourney) return
    const id = setInterval(() => {
      setCountdownSeconds((current) => {
        if (current <= 1) {
          clearInterval(id)
          if (!countdownTriggeredRef.current) {
            countdownTriggeredRef.current = true
            ;(async () => {
              await triggerSafetyEvent('COUNTDOWN_EXPIRED')
              await triggerManualSos()
            })()
          }
          return 0
        }
        return current - 1
      })
    }, 1000)
    return () => clearInterval(id)
  }, [countdownOpen, sosJourney])

  useEffect(() => {
    if (!sosJourney || validGuardianEmails.length === 0) return
    const intervalMs = Math.max(300000, Number(locationUpdateMinutes || 5) * 60 * 1000)
    const id = setInterval(() => shareGuardianLocation(), intervalMs)
    return () => clearInterval(id)
  }, [sosJourney, validGuardianEmails.length, locationUpdateMinutes])

  useEffect(() => () => stopVoiceMonitoring(), [])

  const selectedRoute = routes.find((r) => r.id === sel)
  const activeRoute = st ? { id: st.route_id, geometry: st.geometry, safety: st.safety, factors: st.factors, distance_m: st.distance_m, progress_m: st.progress_m, eta_min: st.eta_min, incident_count: st.incidents_ahead.length } : selectedRoute
  const navItems = [{ icon: '⌂', label: 'Home' }, { icon: '⌖', label: 'Route Planner' }, { icon: '◉', label: 'Live Journey' }, { icon: '◈', label: 'Safety Reports' }, { icon: '☆', label: 'Saved Places' }, { icon: '⚙', label: 'Settings' }]
  const shown = st ? [{ id: st.route_id, geometry: st.geometry }] : routes

  if (currentPage === 'settings') {
    return (<div className="dashboard settings-page-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">✦</span><div><strong>SENTINEL</strong><small>Safe navigation</small></div></div>
        <nav className="sidebar-nav">{navItems.map(({ icon, label }) => (
          <button
            key={label}
            type="button"
            className={'nav-item' + (label === activeNav ? ' active' : '')}
            onClick={() => {
              setActiveNav(label)
              setCurrentPage(label === 'Settings' ? 'settings' : 'home')
            }}
          >
            <span>{icon}</span>{label}
          </button>
        ))}</nav>
        <div className="sidebar-foot"><div className="avatar">A</div><div><b>Aarav</b><small>Stay safe.</small></div><span className="more">•••</span></div>
      </aside>
      <main className="workspace settings-page">
        <header className="topbar settings-topbar"><div><span className="eyebrow">Safety preferences</span><h1>Guardian settings</h1></div><button className="sos-button sos-button-muted" onClick={() => { setCurrentPage('home'); setActiveNav('Route Planner') }}>← Back to home</button></header>
        <section className="panel settings-panel">
          <div className="settings-page-form">
            <label>Guardian email 1<input value={guardianEmails[0] || ''} onChange={(e) => setGuardianEmails((current) => [e.target.value, current[1] || ''])} placeholder="guardian1@example.com" /></label>
            <label>Guardian email 2<input value={guardianEmails[1] || ''} onChange={(e) => setGuardianEmails((current) => [current[0] || '', e.target.value])} placeholder="guardian2@example.com" /></label>
            <label>Emergency contact 1<input value={emergencyContacts[0]?.number || ''} onChange={(e) => setEmergencyContacts((current) => [{ ...current[0], number: e.target.value }, current[1] || { label: 'Ambulance', number: '108' }])} placeholder="112" /></label>
            <label>Emergency contact 2<input value={emergencyContacts[1]?.number || ''} onChange={(e) => setEmergencyContacts((current) => [current[0] || { label: 'Police', number: '112' }, { ...current[1], number: e.target.value }])} placeholder="108" /></label>
            <label>User name<input value={emergencyProfile.name} onChange={(e) => setEmergencyProfile((current) => ({ ...current, name: e.target.value }))} placeholder="Name" /></label>
            <label>Address<textarea value={emergencyProfile.address} onChange={(e) => setEmergencyProfile((current) => ({ ...current, address: e.target.value }))} placeholder="Address" rows={3} /></label>
            <label>Blood type<input value={emergencyProfile.blood_type} onChange={(e) => setEmergencyProfile((current) => ({ ...current, blood_type: e.target.value }))} placeholder="A+" /></label>
            <label>Allergies<input value={emergencyProfile.allergies} onChange={(e) => setEmergencyProfile((current) => ({ ...current, allergies: e.target.value }))} placeholder="Penicillin, peanuts" /></label>
            <label>Medical conditions<input value={emergencyProfile.medical_conditions} onChange={(e) => setEmergencyProfile((current) => ({ ...current, medical_conditions: e.target.value }))} placeholder="Asthma, epilepsy" /></label>
            <label>Location update interval
              <select value={locationUpdateMinutes} onChange={(e) => setLocationUpdateMinutes(Number(e.target.value))}>
                <option value={5}>5 minutes</option>
                <option value={10}>10 minutes</option>
                <option value={15}>15 minutes</option>
                <option value={30}>30 minutes</option>
              </select>
            </label>
            {settingsSavedMessage && <div className="sos-notice">{settingsSavedMessage}</div>}
            <button className="sos-button sos-button-primary" onClick={saveSettings}>Save settings</button>
          </div>
        </section>
      </main>
    </div>)
  }

  return (<div className="dashboard">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">✦</span><div><strong>SENTINEL</strong><small>Safe navigation</small></div></div>
      <nav className="sidebar-nav">{navItems.map(({ icon, label }) => (
        <button
          key={label}
          type="button"
          className={'nav-item' + (label === activeNav ? ' active' : '')}
          onClick={() => {
            setActiveNav(label)
            setCurrentPage(label === 'Settings' ? 'settings' : 'home')
          }}
        >
          <span>{icon}</span>{label}
        </button>
      ))}</nav>
      <div className="sidebar-foot"><div className="avatar">A</div><div><b>Aarav</b><small>Stay safe.</small></div><span className="more">•••</span></div>
    </aside>
    <main className="workspace">
      <header className="topbar"><div><span className="eyebrow">Safety-first navigation</span><h1>{jid ? 'Live journey' : 'Safe route planner'}</h1></div><div className="top-actions"><span className="status-chip"><span className="live-dot" />{jid ? 'Journey active' : 'Ready to plan'}</span><button className="icon-button">?</button></div></header>
      <section className="panel sos-panel">
        <div className="panel-heading">
          <div><span className="eyebrow">04 · Intelligent SOS</span><h2>Safety monitor</h2></div>
        </div>
        {!sosJourney && <button className="sos-button sos-button-primary" onClick={startSafetyJourney}>Activate safety monitor</button>}
        {sosJourney && <div className="sos-panel-body">
          <div className="sos-header">
            <p className="muted">Journey: {sosJourney.journey_id} · {sosStatus?.status || 'JOURNEY_ACTIVE'}</p>
            <div className="sos-tag-row">
              <span className="tag">Risk: {sosStatus?.risk_level || 'LOW'}</span>
              <span className="tag">{sosStatus?.risk_score || 0}</span>
            </div>
          </div>

          {sosStatus?.countdown_required && <div className="alert"><strong>POSSIBLE EMERGENCY DETECTED</strong><p className="muted">Are you safe? Automatic SOS in {sosStatus.countdown_seconds}s</p></div>}
          {isEmergencyActive && <div className="alert emergency-alert"><strong>SOS ACTIVATED</strong><p className="muted">Emergency state active. Guardians have been notified and help is on the way.</p></div>}

          <div className="risk-display-wrap">
            <div className="risk-label">Risk score</div>
            <div className={`risk-score risk-score-${riskDisplayValue >= 60 ? 'high' : riskDisplayValue >= 30 ? 'mid' : 'low'}`}>{riskDisplayValue}</div>
          </div>

          <div className="sos-button-grid">
            {!hideActionButtons && <button className="sos-button sos-button-secondary" onClick={() => triggerSafetyEvent('KEYWORD_DETECTED')}>Keyword</button>}
            {!hideActionButtons && <button className="sos-button sos-button-secondary" onClick={() => triggerSafetyEvent('FALL_DETECTED')}>Fall</button>}
            {!hideActionButtons && <button className="sos-button sos-button-secondary" onClick={() => triggerSafetyEvent('EMOTION_DETECTED', 'angry')}>Angry voice</button>}
            <button className="sos-button sos-button-secondary" onClick={handleSafeResponse}>I am safe</button>
          </div>

          {!hideActionButtons && <button className="sos-button sos-button-danger" onClick={triggerManualSos}>Manual SOS</button>}
          {!hideActionButtons && <button className="sos-button sos-button-muted" onClick={isListening ? stopVoiceMonitoring : startVoiceMonitoring}>{isListening ? 'Stop mic' : 'Start mic'}</button>}

          <div className="transcript-box">
            <label>Current detected words</label>
            <div className="transcript-buffer">{liveTranscript || 'Listening for speech…'}</div>
          </div>

          <div className="manual-transcript-row">
            <input value={manualTranscript} onChange={(e) => setManualTranscript(e.target.value)} placeholder="Type a phrase like 'help me'" />
            <button className="sos-button sos-button-primary" onClick={() => processTranscript(manualTranscript)}>Use transcript</button>
          </div>
        </div>}
        {sosNotice && <p className="sos-notice">{sosNotice}</p>}
      </section>

      {countdownOpen && <div className="countdown-backdrop">
        <div className="countdown-modal">
          <p className="eyebrow">Safety check</p>
          <h3>Are you safe?</h3>
          <div className="countdown-total">{countdownSeconds}s</div>
          <p className="muted">If you do not respond, the app will trigger SOS automatically and notify your guardians.</p>
          <div className="countdown-actions">
            <button className="sos-button sos-button-primary" onClick={handleSafeResponse}>I am safe</button>
            <button className="sos-button sos-button-danger" onClick={triggerManualSos}>Trigger SOS now</button>
          </div>
        </div>
      </div>}

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
