// Backend API + live event stream. Updates the reactive store.
import { getState, set } from './store.js'

export async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'content-type': 'application/json' },
    ...opts,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(data.detail || res.statusText || 'Request failed')
  }
  return data
}

export const configMeta = (grid) => api(`/api/config/meta?grid_size=${grid}`)
export const loadConfigFile = (path) =>
  api('/api/config/load', { method: 'POST', body: JSON.stringify({ path }) })
export const saveConfigFile = (path, config) =>
  api('/api/config/save', { method: 'POST', body: JSON.stringify({ path, config }) })
export const validateConfig = (config) =>
  api('/api/config/validate', { method: 'POST', body: JSON.stringify({ config }) })
export const calcTotalPaths = (config) =>
  api('/api/config/calculate-total-paths', {
    method: 'POST',
    body: JSON.stringify({ config }),
  })
export const previewShapes = (config) =>
  api('/api/shapes/preview', { method: 'POST', body: JSON.stringify({ config }) })
export const runStart = (mode, config) =>
  api('/api/run/start', { method: 'POST', body: JSON.stringify({ mode, config }) })
export const runPause = () => api('/api/run/pause', { method: 'POST', body: '{}' })
export const runResume = () => api('/api/run/resume', { method: 'POST', body: '{}' })
export const runStop = () => api('/api/run/stop', { method: 'POST', body: '{}' })

export function applySnapshot(snapshot) {
  const patch = { snapshot }
  if (snapshot.successful_path) {
    patch.successPath = snapshot.successful_path
  }
  if (Array.isArray(snapshot.log_tail) && snapshot.log_tail.length) {
    patch.logs = snapshot.log_tail
  }
  set(patch)
}

export function startRuntime() {
  api('/api/state')
    .then((snapshot) => {
      applySnapshot(snapshot)
      set({ connection: 'live' })
    })
    .catch(() => set({ connection: 'offline' }))
  const events = new EventSource('/api/events')
  events.addEventListener('open', () => set({ connection: 'live' }))
  events.addEventListener('error', () => {
    if (getState().connection !== 'live') set({ connection: 'reconnecting' })
  })
  events.addEventListener('snapshot', (e) => applySnapshot(JSON.parse(e.data)))
  events.addEventListener('attempt', (e) => {
    const entry = JSON.parse(e.data)
    set({ logs: [entry, ...getState().logs].slice(0, 250) })
  })
  return events
}
