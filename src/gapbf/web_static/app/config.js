import { api } from './io.js'
import {
  createIdleSnapshot,
  flashMessage,
  flashValidation,
  updateSnapshot,
} from './notifications.js'
import { elements, state } from './state.js'
import {
  applyGridConfig,
  hideTooltipOverlay,
  renderAll,
  syncLengthControls,
} from './render.js'

export function syncConfigFromInputs() {
  syncLengthControls('min-number')
  state.config.grid_size = Number(elements.gridSize.value)
  state.config.path_min_length = Number(elements.pathMinLengthNumber.value)
  state.config.path_max_length = Number(elements.pathMaxLengthNumber.value)
  state.config.attempt_delay = Number(elements.attemptDelay.value)
  state.config.adb_timeout = Number(elements.adbTimeout.value)
  state.config.path_max_node_distance = Number(
    elements.pathMaxNodeDistance.value,
  )
  state.config.echo_commands = elements.echoCommands.checked
  state.config.no_diagonal_crossings = elements.noDiagonalCrossings.checked
  state.config.no_perpendicular_crossings =
    elements.noPerpendicularCrossings.checked
  state.config.stdout_success = elements.stdoutSuccess.value
  state.config.stdout_normal = elements.stdoutNormal.value
  state.config.stdout_error = elements.stdoutError.value
  state.config.db_path = elements.dbPath.value
  state.config.test_path = elements.testPath.value
    .trim()
    .split('')
    .filter(Boolean)
  state.config.total_paths = Number(elements.totalPaths.value)
  state.config.config_file_path = elements.configPath.value
}

export async function validateDraft() {
  syncConfigFromInputs()
  try {
    const payload = await api('/api/config/validate', {
      method: 'POST',
      body: JSON.stringify({ config: state.config }),
    })
    state.validationErrors = []
    state.config = payload.config
    applyGridConfig(Number(payload.config.grid_size), payload.meta)
    renderAll()
    return true
  } catch (error) {
    flashValidation([error.message])
    return false
  }
}

export async function loadConfig(path) {
  try {
    const payload = await api('/api/config/load', {
      method: 'POST',
      body: JSON.stringify({ path }),
    })
    state.config = payload.config
    applyGridConfig(Number(payload.config.grid_size), payload.meta)
    state.validationErrors = []
    renderAll()
  } catch (error) {
    flashValidation([error.message])
  }
}

export async function resetDashboard(mode) {
  if (state.snapshot?.active) {
    flashValidation(['Stop the active run before resetting the dashboard.'])
    return
  }

  const configPath =
    elements.configPath.value ||
    state.snapshot?.default_config_path ||
    state.config.config_file_path ||
    'config.yaml'

  state.tool = 'prefix'
  state.drawing = false
  state.validationErrors = []
  state.successNoticePath = null
  state.logs = []
  updateSnapshot(createIdleSnapshot(configPath, mode), {
    preserveNotifications: false,
  })
  hideTooltipOverlay()
  renderAll()
  await loadConfig(configPath)
}

export async function saveConfig(path) {
  const valid = await validateDraft()
  if (!valid) {
    return
  }
  try {
    const payload = await api('/api/config/save', {
      method: 'POST',
      body: JSON.stringify({ path, config: state.config }),
    })
    state.config = payload.config
    applyGridConfig(Number(payload.config.grid_size), payload.meta)
    flashMessage(`Saved config to ${payload.saved_path}`)
    renderAll()
  } catch (error) {
    flashValidation([error.message])
  }
}

export async function calculateTotalPaths() {
  const valid = await validateDraft()
  if (!valid) {
    return
  }

  state.isCalculatingTotalPaths = true
  renderAll()
  await new Promise((resolve) => window.requestAnimationFrame(resolve))

  try {
    updateSnapshot(
      await api('/api/config/calculate-total-paths', {
        method: 'POST',
        body: JSON.stringify({ config: state.config }),
      }),
      { preserveNotifications: true },
    )
    renderAll()
  } catch (error) {
    flashValidation([error.message])
  } finally {
    state.isCalculatingTotalPaths = false
    renderAll()
  }
}
