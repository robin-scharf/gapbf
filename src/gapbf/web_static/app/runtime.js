import { api } from './io.js'
import { renderLogs } from './logs.js'
import { updateSnapshot } from './notifications.js'
import { applyGridConfig } from './render.js'
import { renderAll } from './render.js'
import { elements, state } from './state.js'
import { loadConfig } from './config.js'

let statePollTimer = null
let statePollInFlight = false

export async function fetchInitialState() {
  const health = await api('/api/health')
  elements.connectionBadge.textContent = health.ok ? 'API ready' : 'API offline'
  const snapshot = await api('/api/state')
  updateSnapshot(snapshot, { preserveNotifications: false })
  if (snapshot.default_config_path) {
    elements.configPath.value = snapshot.default_config_path
    await loadConfig(snapshot.default_config_path)
  } else {
    applyGridConfig(3, await api('/api/config/meta?grid_size=3'), {
      forceMaxLength: true,
    })
  }
  renderAll()
}

export function subscribeEvents() {
  const events = new EventSource('/api/events')
  events.addEventListener('snapshot', (event) => {
    updateSnapshot(JSON.parse(event.data))
    renderAll()
  })
  events.addEventListener('attempt', (event) => {
    const entry = JSON.parse(event.data)
    state.logs = [entry, ...state.logs].slice(0, 250)
    renderLogs()
  })
  events.onerror = () => {
    elements.connectionBadge.textContent = 'Reconnecting'
  }
  events.onopen = () => {
    elements.connectionBadge.textContent = 'API ready'
  }
}

export function startStatePolling() {
  if (statePollTimer !== null) {
    return
  }

  statePollTimer = window.setInterval(async () => {
    if (statePollInFlight) {
      return
    }
    if (
      !state.snapshot?.active &&
      elements.connectionBadge.textContent === 'API ready'
    ) {
      return
    }

    statePollInFlight = true
    try {
      const snapshot = await api('/api/state')
      updateSnapshot(snapshot)
      renderAll()
      elements.connectionBadge.textContent = 'API ready'
    } catch (_error) {
      elements.connectionBadge.textContent = 'Reconnecting'
    } finally {
      statePollInFlight = false
    }
  }, 1000)
}
