const HOURS = [6, 9, 12, 15, 18, 21, 0, 3]

export const speedScore = (r, minEta) => r?.eta_min ? Math.round(100 * Math.min(1, (minEta || r.eta_min) / r.eta_min)) : 0

/** Blend safety vs speed using the 0–100 safety-time preference slider. */
export const routeScore = (safety, speed, preference) => Math.round((preference / 100) * safety + (1 - preference / 100) * speed)

/** Time-of-day penalty from lighting, crowd, and traffic (before preference). */
export const timePenalty = (route, h) => {
  const f = route?.factors || {}, lighting = f.lighting ?? 80, crowd = f.crowd ?? 80, traffic = f.traffic ?? 80
  const night = h >= 21 || h < 5 ? 1 : h >= 18 || h < 7 ? .5 : 0, rush = Math.floor(h) === 9 || Math.floor(h) === 18 ? 1 : 0
  return night * ((100 - lighting) * .6 + (100 - crowd) * .4 + 8) + rush * (100 - traffic) * .2
}

/**
 * Preference-weighted hour safety, using the same slider mix as route score:
 * preference 0 → base route safety (ignore hour); 100 → full night/rush environment.
 */
export const hourSafety = (route, h, preference = 50) => {
  const base = Number(route?.safety) || 0
  const env = base - timePenalty(route, h)
  return Math.max(0, Math.min(100, routeScore(env, base, preference)))
}

export const profileAt = (route, h, preference = 50, minEta, label) => {
  const safety = hourSafety(route, h, preference)
  const speed = speedScore(route, minEta)
  return { hour: h, label: label || `${String(h).padStart(2, '0')}:00`, safety, risk: 100 - safety, score: routeScore(safety, speed, preference) }
}

export const timeProfile = (route, preference = 50, minEta) => route ? HOURS.map((h) => profileAt(route, h, preference, minEta)) : []
