import { drawBoard, renderSequences } from './board.js'
import { flashValidation, formatTimestamp, renderNotifications } from './notifications.js'
import { renderLogs } from './logs.js'
import { hideTooltipOverlay } from './tooltip.js'
import { elements, state } from './state.js'
function formatDuration(startedAt, finishedAt) {
  if (!startedAt) {
    return '-'
  }

  const startedMs = Date.parse(startedAt)
  const endedMs = finishedAt ? Date.parse(finishedAt) : Date.now()
  if (!Number.isFinite(startedMs) || !Number.isFinite(endedMs)) {
    return '-'
  }

  const totalSeconds = Math.max(0, Math.floor((endedMs - startedMs) / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return [hours, minutes, seconds]
    .map((value) => String(value).padStart(2, '0'))
    .join(':')
}

export function applyGridConfig(gridSize, meta, options = {}) {
  const { forceMaxLength = false } = options
  state.meta = meta
  state.config.grid_size = gridSize
  const minLength = Number(meta.min_path_length || 4)
  const maxLength = Number(meta.max_path_length || gridSize ** 2)
  const validNodes = new Set(meta.nodes || [])

  ;['path_prefix', 'path_suffix', 'excluded_nodes', 'test_path'].forEach(
    (key) => {
      state.config[key] = (state.config[key] || []).filter((node) =>
        validNodes.has(node),
      )
    },
  )

  state.config.path_max_length = forceMaxLength
    ? maxLength
    : Math.min(Number(state.config.path_max_length) || maxLength, maxLength)
  state.config.path_min_length = Math.max(
    minLength,
    Math.min(
      Number(state.config.path_min_length) ||
        Number(meta.default_path_min_length) ||
        minLength,
      state.config.path_max_length,
    ),
  )
  state.config.path_max_node_distance = Math.min(
    Number(state.config.path_max_node_distance) ||
      Number(meta.default_path_max_node_distance) ||
      Math.max(1, gridSize - 1),
    Math.max(1, gridSize - 1),
  )
}

function clampNumber(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

export function syncLengthControls(source) {
  const minLength = Number(state.meta?.min_path_length || 4)
  const maxLength = Number(
    state.meta?.max_path_length || state.config.grid_size ** 2,
  )
  let nextMin = Number(elements.pathMinLengthNumber.value)
  let nextMax = Number(elements.pathMaxLengthNumber.value)

  if (source === 'min-range') {
    nextMin = Number(elements.pathMinLength.value)
  }
  if (source === 'max-range') {
    nextMax = Number(elements.pathMaxLength.value)
  }
  if (source === 'min-number') {
    nextMin = Number(elements.pathMinLengthNumber.value)
  }
  if (source === 'max-number') {
    nextMax = Number(elements.pathMaxLengthNumber.value)
  }

  nextMin = clampNumber(
    Number.isFinite(nextMin) ? nextMin : minLength,
    minLength,
    maxLength,
  )
  nextMax = clampNumber(
    Number.isFinite(nextMax) ? nextMax : maxLength,
    minLength,
    maxLength,
  )

  if (nextMin > nextMax) {
    if (source === 'max-range' || source === 'max-number') {
      nextMin = nextMax
    } else {
      nextMax = nextMin
    }
  }

  elements.pathMinLength.value = String(nextMin)
  elements.pathMinLengthNumber.value = String(nextMin)
  elements.pathMaxLength.value = String(nextMax)
  elements.pathMaxLengthNumber.value = String(nextMax)
}

function renderInputs() {
  elements.configPath.value =
    state.config.config_file_path || elements.configPath.value
  elements.gridSize.value = String(state.config.grid_size)
  elements.pathMinLength.value = String(state.config.path_min_length)
  elements.pathMinLengthNumber.value = String(state.config.path_min_length)
  elements.pathMaxLength.value = String(state.config.path_max_length)
  elements.pathMaxLengthNumber.value = String(state.config.path_max_length)
  elements.attemptDelay.value = String(state.config.attempt_delay)
  elements.adbTimeout.value = String(state.config.adb_timeout)
  elements.pathMaxNodeDistance.value = String(
    state.config.path_max_node_distance,
  )
  elements.distanceNote.textContent =
    state.meta?.path_max_node_distance_note || ''
  elements.echoCommands.checked = Boolean(state.config.echo_commands)
  elements.noDiagonalCrossings.checked = Boolean(
    state.config.no_diagonal_crossings,
  )
  elements.noPerpendicularCrossings.checked = Boolean(
    state.config.no_perpendicular_crossings,
  )
  elements.stdoutSuccess.value = state.config.stdout_success || ''
  elements.stdoutNormal.value = state.config.stdout_normal || ''
  elements.stdoutError.value = state.config.stdout_error || ''
  elements.dbPath.value = state.config.db_path || '~/.gapbf/gapbf.db'
  elements.testPath.value = Array.isArray(state.config.test_path)
    ? state.config.test_path.join('')
    : ''
  elements.totalPaths.value = String(state.config.total_paths || 0)

  const maxLength =
    state.meta?.max_path_length || Number(state.config.grid_size) ** 2
  const minLength = state.meta?.min_path_length || 4
  ;[
    elements.pathMinLength,
    elements.pathMinLengthNumber,
    elements.pathMaxLength,
    elements.pathMaxLengthNumber,
  ].forEach((input) => {
    input.min = String(minLength)
    input.max = String(maxLength)
  })
  elements.pathMaxNodeDistance.max = String(
    Math.max(1, Number(state.config.grid_size) - 1),
  )
}

function renderProgress() {
  const snapshot = state.snapshot
  if (!snapshot) {
    return
  }
  const total = snapshot.total_paths
  const tested = snapshot.paths_tested || 0
  const percent = total ? (tested / total) * 100 : 0

  elements.progressLabel.textContent = `${tested.toLocaleString()} / ${
    total ? total.toLocaleString() : 'Unknown'
  }`
  elements.progressPercent.textContent = `${percent.toFixed(2)}%`
  elements.progressBar.style.width = `${Math.max(0, Math.min(percent, 100))}%`
  elements.statusValue.textContent = snapshot.status || 'Idle'
  elements.currentPathValue.textContent = snapshot.current_path || '-'
  elements.totalPathsValue.textContent = total
    ? total.toLocaleString()
    : snapshot.total_paths_state || 'Unknown'

  if (snapshot.total_paths_state === 'counting') {
    elements.totalPathsStateValue.textContent = `Counting exact total ${
      snapshot.total_paths_elapsed_seconds || 0
    }s / ${snapshot.total_paths_timeout_seconds || 0}s`
  } else if (snapshot.total_paths_state === 'ready') {
    elements.totalPathsStateValue.textContent = 'Exact total ready'
  } else if (snapshot.total_paths_state === 'timeout') {
    elements.totalPathsStateValue.textContent = `Timed out after ${
      snapshot.total_paths_timeout_seconds || 0
    }s; using unknown total`
  } else if (snapshot.total_paths_state === 'error') {
    elements.totalPathsStateValue.textContent = 'Exact total unavailable'
  } else {
    elements.totalPathsStateValue.textContent = 'Not started'
  }

  elements.deviceValue.textContent = snapshot.device_id || '-'
  elements.startedAtValue.textContent = formatTimestamp(snapshot.started_at)
  elements.finishedAtValue.textContent = formatTimestamp(snapshot.finished_at)
  elements.durationValue.textContent = formatDuration(
    snapshot.started_at,
    snapshot.finished_at,
  )
  elements.runStatusBadge.textContent = snapshot.status || 'Idle'
  elements.pauseButton.disabled = !snapshot.active || snapshot.paused
  elements.resumeButton.disabled = !snapshot.active || !snapshot.paused
  elements.stopButton.disabled = !snapshot.active
  elements.resetButton.disabled = Boolean(snapshot.active)
  elements.calculateTotalPathsButton.disabled =
    Boolean(snapshot.active) ||
    snapshot.total_paths_state === 'counting' ||
    state.isCalculatingTotalPaths
  elements.calculateTotalPathsButton.classList.toggle(
    'is-loading',
    state.isCalculatingTotalPaths,
  )
  elements.calculateTotalPathsButton.textContent = state.isCalculatingTotalPaths
    ? 'Calculating exact total'
    : 'Calculate total paths'
  drawBoard(
    elements.liveBoard,
    (snapshot.current_path || '').split('').filter(Boolean),
    {
      flashValidation,
      renderAll,
    },
  )
}

export function renderAll() {
  renderNotifications()
  renderInputs()
  renderSequences()
  drawBoard(
    elements.patternBoard,
    (state.snapshot?.current_path || '').split('').filter(Boolean),
    {
      showConstraintOrder: true,
      flashValidation,
      renderAll,
    },
  )
  renderProgress()
  renderLogs()
  elements.toolButtons.forEach((button) => {
    const isActive = button.dataset.tool === state.tool
    button.classList.toggle('is-active', isActive)
    button.setAttribute('aria-pressed', String(isActive))
  })
}
export { hideTooltipOverlay }
