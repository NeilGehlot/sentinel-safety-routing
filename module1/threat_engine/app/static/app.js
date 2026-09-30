const CITIES = {
  gurugram: { name: "Gurugram", lat: 28.4595, lon: 77.0266, zoom: 13 },
  jaipur: { name: "Jaipur", lat: 26.9124, lon: 75.7873, zoom: 12 },
};
const WHEN = [
  { id: "now", label: "Now" },
  { id: "morning", label: "Morning", h: 9, m: 0 },
  { id: "afternoon", label: "Afternoon", h: 14, m: 0 },
  { id: "evening", label: "Evening", h: 19, m: 0 },
  { id: "late", label: "Late night", h: 23, m: 30 },
];
const ACTIVITIES = [
  { id: "standing", emoji: "🧍", label: "Standing", activity: "stationary", speed: 0 },
  { id: "walking", emoji: "🚶", label: "Walking", activity: "walking", speed: 1.4 },
  { id: "running", emoji: "🏃", label: "Running", activity: "running", speed: 3.5 },
  { id: "vehicle", emoji: "🚗", label: "Vehicle", activity: "vehicle", speed: 10 },
];
const SIGNALS = [
  { id: "none", label: "No signal", dbm: -125 },
  { id: "weak", label: "Weak", dbm: -108 },
  { id: "okay", label: "Okay", dbm: -95 },
  { id: "strong", label: "Strong", dbm: -75 },
];
// Demo stand-in for scan counts. The real app sends scan counts.
const PEOPLE = [
  { id: "nobody", label: "Nobody", wifi: 0, ble: 0 },
  { id: "few", label: "A few", wifi: 5, ble: 3 },
  { id: "some", label: "Some", wifi: 15, ble: 8 },
  { id: "crowd", label: "Crowded", wifi: 40, ble: 20 },
];
const NAMES = {
  time_of_day: "Time of day",
  weather: "Weather",
  crime_risk: "This area",
  news_risk: "Nearby news",
  crowd_density: "How busy",
  cellular: "Signal",
  battery: "Battery",
  internet: "Internet",
  safe_places: "Safe place",
  nearby_devices: "People nearby",
  movement: "Movement",
  isolated_night: "Quiet night",
  distress_movement: "Sudden motion",
};
const UNREACHABLE = "Can't reach the safety service. Is the server running?";
const state = { city: "gurugram", when: "now", activity: "walking", signal: "okay", internet: true, people: "few" };
let prevPin = null;
let shown = null;
let timer = 0;
let seq = 0;

function sessionId() {
  const key = "sentinel-session";
  let id = sessionStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(key, id);
  }
  return id;
}

function pad(value) {
  return String(value).padStart(2, "0");
}

function isoStamp(date) {
  const off = -date.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const abs = Math.abs(off);
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return `${shifted.toISOString().slice(0, 19)}${sign}${pad(Math.floor(abs / 60))}:${pad(abs % 60)}`;
}

function timestamp() {
  const pick = WHEN.find((item) => item.id === state.when);
  if (!pick || pick.id === "now") return isoStamp(new Date());
  const date = new Date();
  date.setHours(pick.h, pick.m, 0, 0);
  return isoStamp(date);
}

function tone(score) {
  if (score < 30) return "var(--safe)";
  if (score < 60) return "var(--caution)";
  if (score < 80) return "var(--high)";
  return "var(--critical)";
}

function bearing(from, to) {
  const rad = Math.PI / 180;
  const y = Math.sin((to.lon - from.lon) * rad) * Math.cos(to.lat * rad);
  const x = Math.cos(from.lat * rad) * Math.sin(to.lat * rad)
    - Math.sin(from.lat * rad) * Math.cos(to.lat * rad) * Math.cos((to.lon - from.lon) * rad);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

function chips(root, items, current, onPick) {
  root.replaceChildren();
  items.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = item.id === current ? "chip on" : "chip";
    button.textContent = item.emoji ? `${item.emoji} ${item.label}` : item.label;
    button.addEventListener("click", () => onPick(item.id));
    root.appendChild(button);
  });
}

function paint() {
  const cities = Object.entries(CITIES).map(([id, city]) => ({ id, label: city.name }));
  chips(document.getElementById("cities"), cities, state.city, (id) => {
    state.city = id;
    const city = CITIES[id];
    place(city.lat, city.lon, city.zoom);
    paint();
    schedule();
  });
  chips(document.getElementById("when"), WHEN, state.when, (id) => { state.when = id; paint(); schedule(); });
  chips(document.getElementById("activity"), ACTIVITIES, state.activity, (id) => { state.activity = id; paint(); schedule(); });
  chips(document.getElementById("signal"), SIGNALS, state.signal, (id) => { state.signal = id; paint(); schedule(); });
  chips(document.getElementById("people"), PEOPLE, state.people, (id) => { state.people = id; paint(); schedule(); });
  const net = document.getElementById("net");
  net.className = state.internet ? "chip on" : "chip";
  net.textContent = state.internet ? "Internet on" : "Internet off";
  net.setAttribute("aria-pressed", state.internet ? "true" : "false");
}

function place(lat, lon, zoom) {
  marker.setLatLng([lat, lon]);
  map.setView([lat, lon], zoom == null ? map.getZoom() : zoom);
}

function payload() {
  const here = marker.getLatLng();
  const pin = { lat: here.lat, lon: here.lng };
  const activity = ACTIVITIES.find((item) => item.id === state.activity);
  const signal = SIGNALS.find((item) => item.id === state.signal);
  const people = PEOPLE.find((item) => item.id === state.people);
  const location = { lat: pin.lat, lon: pin.lon, speed_mps: activity.speed };
  // Demo stand-in for GPS heading. The real app sends sensor heading.
  if (prevPin && (Math.abs(prevPin.lat - pin.lat) > 1e-6 || Math.abs(prevPin.lon - pin.lon) > 1e-6)) {
    location.heading_deg = Math.round(bearing(prevPin, pin) * 10) / 10;
  }
  prevPin = pin;
  return {
    timestamp: timestamp(),
    session_id: sessionId(),
    location,
    device: {
      cellular_dbm: signal.dbm,
      internet_available: state.internet,
      battery_pct: Number(document.getElementById("battery").value),
    },
    movement: { activity: activity.activity },
    nearby_devices: { wifi_count: people.wifi, ble_count: people.ble },
  };
}

function arrow(next, now) {
  if (next > now) return "↑";
  if (next < now) return "↓";
  return "→";
}

function animate(score) {
  const ring = document.getElementById("ring");
  const node = document.getElementById("score");
  const from = shown == null ? 0 : shown;
  const start = performance.now();
  ring.style.setProperty("--tone", tone(score));
  ring.style.setProperty("--pct", String(score));
  function frame(now) {
    const t = Math.min(1, (now - start) / 400);
    node.textContent = String(Math.round(from + (score - from) * t));
    if (t < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  shown = score;
}

function show(data) {
  document.getElementById("skeleton").hidden = true;
  document.getElementById("result").hidden = false;
  document.getElementById("error").hidden = true;
  animate(data.current_score);
  const byMin = {};
  data.predicted.forEach((item) => { byMin[item.horizon_min] = item.score; });
  document.getElementById("h5").textContent = String(byMin[5] ?? "–");
  document.getElementById("a5").textContent = arrow(byMin[5], data.current_score);
  document.getElementById("a5").style.color = tone(byMin[5]);
  document.getElementById("h10").textContent = String(byMin[10] ?? "–");
  document.getElementById("a10").textContent = arrow(byMin[10], data.current_score);
  document.getElementById("a10").style.color = tone(byMin[10]);
  const pills = document.getElementById("pills");
  pills.replaceChildren();
  [...data.explanation.contributors]
    .sort((a, b) => Math.abs(b.points) - Math.abs(a.points))
    .slice(0, 3)
    .forEach((item) => {
      const pill = document.createElement("span");
      const sign = item.points > 0 ? "+" : "";
      pill.className = "factor " + (item.points > 0 ? "raise" : item.points < 0 ? "lower" : "");
      pill.textContent = `${NAMES[item.signal] || "Factor"} ${sign}${item.points}`;
      pills.appendChild(pill);
    });
  document.getElementById("summary").textContent = data.explanation.summary;
  const tips = document.getElementById("tips");
  tips.replaceChildren();
  data.recommendations.slice(0, 2).forEach((text) => {
    const item = document.createElement("li");
    item.textContent = text;
    tips.appendChild(item);
  });
}

function fail(keep) {
  const error = document.getElementById("error");
  error.hidden = false;
  error.textContent = UNREACHABLE;
  if (!keep) {
    document.getElementById("skeleton").hidden = true;
    document.getElementById("result").hidden = true;
  }
}

async function run(explain) {
  const ticket = ++seq;
  const keep = !document.getElementById("result").hidden;
  if (!keep) document.getElementById("skeleton").hidden = false;
  try {
    const response = await fetch(explain ? "/v1/assess?explain=llm" : "/v1/assess", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload()),
    });
    if (!response.ok) throw new Error("bad");
    const data = await response.json();
    if (ticket !== seq || typeof data.current_score !== "number") throw new Error("bad");
    show(data);
  } catch {
    if (ticket !== seq) return;
    fail(keep);
  }
}

function schedule() {
  clearTimeout(timer);
  timer = setTimeout(() => run(false), 800);
}

const start = CITIES.gurugram;
const map = L.map("map").setView([start.lat, start.lon], start.zoom);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap",
}).addTo(map);
const marker = L.marker([start.lat, start.lon]).addTo(map);
map.on("click", (event) => {
  place(event.latlng.lat, event.latlng.lng);
  schedule();
});
document.getElementById("locate").addEventListener("click", () => {
  if (!navigator.geolocation) return;
  navigator.geolocation.getCurrentPosition((pos) => {
    place(pos.coords.latitude, pos.coords.longitude);
    schedule();
  });
});
document.getElementById("net").addEventListener("click", () => {
  state.internet = !state.internet;
  paint();
  schedule();
});
document.getElementById("battery").addEventListener("input", (event) => {
  document.getElementById("batteryOut").textContent = event.target.value;
  schedule();
});
document.getElementById("refresh").addEventListener("click", () => run(true));
function fitMap() {
  map.invalidateSize();
}
function bindFold(dockId, tabId) {
  const dock = document.getElementById(dockId);
  const tab = document.getElementById(tabId);
  tab.addEventListener("click", () => {
    dock.classList.toggle("is-out");
    const open = !dock.classList.contains("is-out");
    tab.setAttribute("aria-expanded", open ? "true" : "false");
    tab.setAttribute("aria-label", open ? "Collapse" : "Expand");
    requestAnimationFrame(fitMap);
  });
}
bindFold("dock-form", "tab-form");
bindFold("dock-results", "tab-results");
document.querySelectorAll(".sheet").forEach((sheet) => {
  sheet.addEventListener("transitionend", fitMap);
});
window.addEventListener("resize", fitMap);
paint();
requestAnimationFrame(fitMap);
run(false);
