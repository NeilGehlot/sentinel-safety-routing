import assert from 'node:assert/strict'
import { test } from 'node:test'
import { hourSafety, profileAt, routeScore, timePenalty } from './routeProfile.js'

const route = {
  safety: 80,
  eta_min: 20,
  factors: { lighting: 40, crowd: 50, traffic: 60 },
}

test('night penalty is applied fully at preference 100', () => {
  const night = 21
  const env = route.safety - timePenalty(route, night)
  assert.equal(hourSafety(route, night, 100), Math.max(0, Math.round(env)))
  assert.notEqual(hourSafety(route, night, 100), hourSafety(route, 12, 100))
})

test('preference 0 ignores time of day for safety and risk', () => {
  const noon = profileAt(route, 12, 0, 15)
  const night = profileAt(route, 21, 0, 15)
  assert.equal(noon.safety, route.safety)
  assert.equal(night.safety, route.safety)
  assert.equal(noon.risk, 100 - route.safety)
  assert.equal(night.risk, 100 - route.safety)
})

test('slider moves safety and risk, not only route score', () => {
  const hour = 21
  const low = profileAt(route, hour, 0, 15)
  const mid = profileAt(route, hour, 50, 15)
  const high = profileAt(route, hour, 100, 15)
  assert.notEqual(low.safety, high.safety)
  assert.notEqual(low.risk, high.risk)
  assert.notEqual(low.score, high.score)
  assert.ok(high.safety < mid.safety)
  assert.ok(mid.safety < low.safety)
  assert.ok(high.risk > mid.risk)
  assert.ok(mid.risk > low.risk)
})

test('route score still blends preference-weighted safety with speed', () => {
  const row = profileAt(route, 21, 40, 15)
  const speed = Math.round(100 * (15 / 20))
  assert.equal(row.score, routeScore(row.safety, speed, 40))
  assert.equal(row.risk, 100 - row.safety)
})
