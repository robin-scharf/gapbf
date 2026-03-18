import { mountTopLinks } from './components/topLinks.js'

const state = {
  tool: 'prefix',
  drawing: false,
  validationErrors: [],
  successNoticePath: null,
  snapshot: null,
  config: {
    grid_size: 3,
    path_min_length: 4,
    path_max_length: 9,
    path_max_node_distance: 1,
    path_prefix: [],
    path_suffix: [],
    excluded_nodes: [],
    attempt_delay: 10.1,
    test_path: [],
    stdout_normal: '',
    stdout_success: '',
    stdout_error: '',
    db_path: '~/.gapbf/gapbf.db',
    adb_timeout: 30,
    total_paths: 0,
    echo_commands: true,
    config_file_path: 'config.yaml',
  },
  meta: null,
  logs: [],
}

const elements = {
  connectionBadge: document.querySelector('#connectionBadge'),
  runStatusBadge: document.querySelector('#runStatusBadge'),
  validationBanner: document.querySelector('#validationBanner'),
  successBanner: document.querySelector('#successBanner'),
  copyConfigButton: document.querySelector('#copyConfigButton'),
  downloadCsvButton: document.querySelector('#downloadCsvButton'),
  configPath: document.querySelector('#configPath'),
  loadConfigButton: document.querySelector('#loadConfigButton'),
  saveConfigButton: document.querySelector('#saveConfigButton'),
  gridSize: document.querySelector('#gridSize'),
  modeA: document.querySelector('#modeA'),
  modeT: document.querySelector('#modeT'),
  modeP: document.querySelector('#modeP'),
  pathMinLength: document.querySelector('#pathMinLength'),
  pathMinLengthNumber: document.querySelector('#pathMinLengthNumber'),
  pathMaxLength: document.querySelector('#pathMaxLength'),
  pathMaxLengthNumber: document.querySelector('#pathMaxLengthNumber'),
  attemptDelay: document.querySelector('#attemptDelay'),
  adbTimeout: document.querySelector('#adbTimeout'),
  pathMaxNodeDistance: document.querySelector('#pathMaxNodeDistance'),
  distanceNote: document.querySelector('#distanceNote'),
  echoCommands: document.querySelector('#echoCommands'),
  stdoutSuccess: document.querySelector('#stdoutSuccess'),
  stdoutNormal: document.querySelector('#stdoutNormal'),
  stdoutError: document.querySelector('#stdoutError'),
  dbPath: document.querySelector('#dbPath'),
  testPath: document.querySelector('#testPath'),
  totalPaths: document.querySelector('#totalPaths'),
  prefixDisplay: document.querySelector('#prefixDisplay'),
  excludedDisplay: document.querySelector('#excludedDisplay'),
  suffixDisplay: document.querySelector('#suffixDisplay'),
  patternBoard: document.querySelector('#patternBoard'),
  liveBoard: document.querySelector('#liveBoard'),
  startButton: document.querySelector('#startButton'),
  pauseButton: document.querySelector('#pauseButton'),
  resumeButton: document.querySelector('#resumeButton'),
  stopButton: document.querySelector('#stopButton'),
  progressLabel: document.querySelector('#progressLabel'),
  progressPercent: document.querySelector('#progressPercent'),
  progressBar: document.querySelector('#progressBar'),
  statusValue: document.querySelector('#statusValue'),
  currentPathValue: document.querySelector('#currentPathValue'),
  totalPathsValue: document.querySelector('#totalPathsValue'),
  deviceValue: document.querySelector('#deviceValue'),
  startedAtValue: document.querySelector('#startedAtValue'),
  finishedAtValue: document.querySelector('#finishedAtValue'),
  durationValue: document.querySelector('#durationValue'),
  logTableBody: document.querySelector('#logTableBody'),
  clearPrefixButton: document.querySelector('#clearPrefixButton'),
  clearExcludedButton: document.querySelector('#clearExcludedButton'),
  clearSuffixButton: document.querySelector('#clearSuffixButton'),
  toolButtons: Array.from(document.querySelectorAll('[data-tool]')),
}

const tooltipState = {
  activeTrigger: null,
  overlay: null,
  content: null,
  arrow: null,
}

let statePollTimer = null
let statePollInFlight = false

function gcd(a, b) {
  if (!b) {
    return a
  }
  return gcd(b, a % b)
}

function validNodesForGrid(gridSize) {
  const sequence = [
    '1',
    '2',
    '3',
    '4',
    '5',
    '6',
    '7',
    '8',
    '9',
    ':',
    ';',
    '<',
    '=',
    '>',
    '?',
    '@',
    'A',
    'B',
    'C',
    'D',
    'E',
    'F',
    'G',
    'H',
    'I',
    'J',
    'K',
    'L',
    'M',
    'N',
    'O',
    'P',
    'Q',
    'R',
    'S',
    'T',
  ]
  return sequence.slice(0, gridSize * gridSize)
}

function coordinatesForGrid(gridSize) {
  const nodes = validNodesForGrid(gridSize)
  const coords = new Map()
  nodes.forEach((node, index) => {
    coords.set(node, { x: index % gridSize, y: Math.floor(index / gridSize) })
  })
  return coords
}

function blockersBetween(start, end, gridSize) {
  const coords = coordinatesForGrid(gridSize)
  const startPoint = coords.get(start)
  const endPoint = coords.get(end)
  if (!startPoint || !endPoint) {
    return []
  }

  const dx = endPoint.x - startPoint.x
  const dy = endPoint.y - startPoint.y
  const steps = gcd(Math.abs(dx), Math.abs(dy))
  if (steps <= 1) {
    return []
  }

  const stepX = dx / steps
  const stepY = dy / steps
  const blockers = []
  for (let step = 1; step < steps; step += 1) {
    const targetX = startPoint.x + stepX * step
    const targetY = startPoint.y + stepY * step
    for (const [node, point] of coords.entries()) {
      if (point.x === targetX && point.y === targetY) {
        blockers.push(node)
      }
    }
  }
  return blockers
}

function isWithinMaxNodeDistance(start, end, gridSize) {
  const coords = coordinatesForGrid(gridSize)
  const startPoint = coords.get(start)
  const endPoint = coords.get(end)
  if (!startPoint || !endPoint) {
    return false
  }

  const maxDistance = Number(state.config.path_max_node_distance) || 1
  return (
    Math.max(
      Math.abs(endPoint.x - startPoint.x),
      Math.abs(endPoint.y - startPoint.y),
    ) <= maxDistance
  )
}

function isLegalMove(start, end, visited, excluded, gridSize) {
  if (start === end || visited.includes(end) || excluded.includes(end)) {
    return false
  }
  if (!isWithinMaxNodeDistance(start, end, gridSize)) {
    return false
  }
  return blockersBetween(start, end, gridSize).every((node) =>
    visited.includes(node),
  )
}

function isSelectableNode(tool, node, gridSize) {
  if (tool === 'exclude') {
    return (
      !state.config.path_prefix.includes(node) &&
      !state.config.path_suffix.includes(node)
    )
  }

  const key = tool === 'prefix' ? 'path_prefix' : 'path_suffix'
  const otherKey = tool === 'prefix' ? 'path_suffix' : 'path_prefix'
  const sequence = state.config[key]
  const otherSequence = state.config[otherKey]

  if (
    sequence.includes(node) ||
    otherSequence.includes(node) ||
    state.config.excluded_nodes.includes(node)
  ) {
    return false
  }

  if (sequence.length === 0) {
    return true
  }

  return isLegalMove(
    sequence.at(-1),
    node,
    sequence,
    state.config.excluded_nodes,
    gridSize,
  )
}

function applyGridConfig(gridSize, meta, options = {}) {
  const { forceMaxLength = false } = options
  state.meta = meta
  state.config.grid_size = gridSize

  const minLength = Number(meta.min_path_length || 4)
  const maxLength = Number(meta.max_path_length || gridSize ** 2)
  const validNodes = new Set(meta.nodes || validNodesForGrid(gridSize))

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
    Number(state.config.path_max_node_distance) || 1,
    Math.max(1, gridSize - 1),
  )
}

function appendSequence(tool, node) {
  const gridSize = Number(state.config.grid_size)
  if (tool === 'exclude') {
    if (
      state.config.path_prefix.includes(node) ||
      state.config.path_suffix.includes(node)
    ) {
      return
    }
    if (state.config.excluded_nodes.includes(node)) {
      state.config.excluded_nodes = state.config.excluded_nodes.filter(
        (item) => item !== node,
      )
    } else {
      state.config.excluded_nodes = [...state.config.excluded_nodes, node]
    }
    renderAll()
    return
  }

  const key = tool === 'prefix' ? 'path_prefix' : 'path_suffix'
  const otherKey = tool === 'prefix' ? 'path_suffix' : 'path_prefix'
  const sequence = [...state.config[key]]
  const otherSequence = state.config[otherKey]
  if (
    sequence.includes(node) ||
    otherSequence.includes(node) ||
    state.config.excluded_nodes.includes(node)
  ) {
    return
  }
  if (
    sequence.length > 0 &&
    !isLegalMove(
      sequence.at(-1),
      node,
      sequence,
      state.config.excluded_nodes,
      gridSize,
    )
  ) {
    flashValidation([`Illegal ${tool} move: ${sequence.at(-1)} -> ${node}`])
    return
  }
  state.config[key] = [...sequence, node]
  const maxLength = Number(state.config.path_max_length)
  if (state.config[key].length > maxLength) {
    state.config[key] = state.config[key].slice(0, maxLength)
  }
  renderAll()
}

function clearSequence(tool) {
  if (tool === 'prefix') {
    state.config.path_prefix = []
  } else if (tool === 'suffix') {
    state.config.path_suffix = []
  } else {
    state.config.excluded_nodes = []
  }
  renderAll()
}

function selectTool(tool) {
  state.tool = tool
  renderAll()
}

function clearBoardSelections() {
  state.config.path_prefix = []
  state.config.path_suffix = []
  state.config.excluded_nodes = []
  state.snapshot = state.snapshot
    ? {
        ...state.snapshot,
        current_path: '',
      }
    : state.snapshot
}

function ensureTooltipOverlay() {
  if (tooltipState.overlay) {
    return tooltipState.overlay
  }

  const overlay = document.createElement('div')
  overlay.className = 'floating-tooltip hidden'
  overlay.setAttribute('role', 'tooltip')

  const content = document.createElement('div')
  content.className = 'floating-tooltip-content'

  const arrow = document.createElement('div')
  arrow.className = 'floating-tooltip-arrow'

  overlay.append(content, arrow)
  document.body.append(overlay)

  tooltipState.overlay = overlay
  tooltipState.content = content
  tooltipState.arrow = arrow
  return overlay
}

function hideTooltipOverlay() {
  if (!tooltipState.overlay) {
    return
  }
  tooltipState.activeTrigger = null
  tooltipState.overlay.classList.add('hidden')
}

function positionTooltipOverlay(trigger) {
  const overlay = ensureTooltipOverlay()
  const triggerRect = trigger.getBoundingClientRect()

  overlay.classList.remove('hidden')
  const overlayRect = overlay.getBoundingClientRect()

  const margin = 12
  const arrowSize = 12
  const idealLeft =
    triggerRect.left + triggerRect.width / 2 - overlayRect.width / 2
  const left = Math.min(
    Math.max(margin, idealLeft),
    window.innerWidth - overlayRect.width - margin,
  )
  const top = Math.max(margin, triggerRect.top - overlayRect.height - arrowSize)
  const arrowLeft = Math.min(
    Math.max(
      14,
      triggerRect.left + triggerRect.width / 2 - left - arrowSize / 2,
    ),
    overlayRect.width - 26,
  )

  overlay.style.left = `${left}px`
  overlay.style.top = `${top}px`
  tooltipState.arrow.style.left = `${arrowLeft}px`
}

function showTooltipOverlay(trigger) {
  const bubble = trigger.querySelector('.info-tooltip-bubble')
  if (!bubble) {
    return
  }

  ensureTooltipOverlay()
  tooltipState.activeTrigger = trigger
  tooltipState.content.textContent = bubble.textContent.trim()
  positionTooltipOverlay(trigger)
}

function bindTooltips() {
  const triggers = Array.from(document.querySelectorAll('.info-tooltip'))
  triggers.forEach((trigger) => {
    trigger.addEventListener('pointerenter', () => showTooltipOverlay(trigger))
    trigger.addEventListener('pointerleave', hideTooltipOverlay)
    trigger.addEventListener('focusin', () => showTooltipOverlay(trigger))
    trigger.addEventListener('focusout', hideTooltipOverlay)
  })

  window.addEventListener('scroll', () => {
    if (tooltipState.activeTrigger) {
      positionTooltipOverlay(tooltipState.activeTrigger)
    }
  })

  window.addEventListener('resize', () => {
    if (tooltipState.activeTrigger) {
      positionTooltipOverlay(tooltipState.activeTrigger)
    }
  })
}

function flashValidation(errors) {
  state.validationErrors = errors
  renderValidation()
}

function flashMessage(message) {
  state.validationErrors = [message]
  renderValidation()
}

function formatTimestamp(value) {
  if (!value) {
    return '-'
  }

  const text = String(value).trim()
  if (!text) {
    return '-'
  }

  return text
    .replace('T', ' ')
    .replace(/(?:Z|[+-]\d{2}:\d{2})$/, '')
}

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

function renderValidation() {
  if (!state.validationErrors.length) {
    elements.validationBanner.classList.add('hidden')
    elements.validationBanner.textContent = ''
    return
  }
  elements.validationBanner.classList.remove('hidden')
  elements.validationBanner.textContent = state.validationErrors.join(' | ')
}

function renderSuccessNotice() {
  if (!state.successNoticePath) {
    elements.successBanner.classList.add('hidden')
    elements.successBanner.textContent = ''
    return
  }

  elements.successBanner.classList.remove('hidden')
  elements.successBanner.textContent = `Correct path found: ${state.successNoticePath}`
}

function updateSnapshot(snapshot, options = {}) {
  const { preserveNotifications = true } = options
  const previousSnapshot = state.snapshot

  state.snapshot = snapshot
  state.logs = snapshot.log_tail || state.logs

  if (!preserveNotifications) {
    state.successNoticePath = null
    return
  }

  if (
    snapshot?.status === 'success' &&
    snapshot.successful_path &&
    (previousSnapshot?.status !== 'success' ||
      previousSnapshot?.successful_path !== snapshot.successful_path)
  ) {
    state.successNoticePath = snapshot.successful_path
  }
}

function builderNodeLabel(node) {
  const prefixIndex = state.config.path_prefix.indexOf(node)
  if (prefixIndex !== -1) {
    return String(prefixIndex + 1)
  }

  const suffixIndex = state.config.path_suffix.indexOf(node)
  if (suffixIndex !== -1) {
    const prefixCount = state.config.path_prefix.length
    return String(prefixCount + suffixIndex + 1)
  }

  return ''
}

function drawBoard(target, livePath = [], options = {}) {
  const { showConstraintOrder = false } = options
  const gridSize = Number(state.config.grid_size)
  const nodes = validNodesForGrid(gridSize)
  const gap = 100 / (gridSize + 1)
  const coords = new Map()
  nodes.forEach((node, index) => {
    const row = Math.floor(index / gridSize)
    const col = index % gridSize
    coords.set(node, { x: (col + 1) * gap, y: (row + 1) * gap })
  })

  target.innerHTML = ''
  target.style.setProperty('--grid-size', String(gridSize))
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  svg.setAttribute('class', 'board-svg')
  svg.setAttribute('viewBox', '0 0 100 100')

  const lines = [
    {
      path: state.config.path_prefix,
      color: 'var(--prefix)',
      width: 4,
      opacity: 0.9,
    },
    {
      path: state.config.path_suffix,
      color: 'var(--suffix)',
      width: 4,
      opacity: 0.9,
    },
    { path: livePath, color: 'var(--live)', width: 3.4, opacity: 0.95 },
  ]

  lines.forEach(({ path, color, width, opacity }) => {
    if (!Array.isArray(path) || path.length < 2) {
      return
    }
    const polyline = document.createElementNS(
      'http://www.w3.org/2000/svg',
      'polyline',
    )
    polyline.setAttribute(
      'points',
      path
        .map((node) => coords.get(node))
        .filter(Boolean)
        .map((point) => `${point.x},${point.y}`)
        .join(' '),
    )
    polyline.setAttribute('class', 'board-line')
    polyline.setAttribute('stroke', color)
    polyline.setAttribute('stroke-width', String(width))
    polyline.setAttribute('opacity', String(opacity))
    svg.append(polyline)
  })
  target.append(svg)

  const nodeLayer = document.createElement('div')
  nodeLayer.className = 'node-layer'

  nodes.forEach((node) => {
    const point = coords.get(node)
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'node-button'
    button.dataset.node = node
    button.textContent = showConstraintOrder ? builderNodeLabel(node) : node
    button.style.left = `${point.x}%`
    button.style.top = `${point.y}%`

    if (state.config.path_prefix.includes(node)) {
      button.classList.add('is-prefix')
    }
    if (state.config.path_suffix.includes(node)) {
      button.classList.add('is-suffix')
    }
    if (state.config.excluded_nodes.includes(node)) {
      button.classList.add('is-excluded')
    }
    if (livePath.includes(node)) {
      button.classList.add('is-live')
    }
    if (!isSelectableNode(state.tool, node, gridSize)) {
      button.classList.add('is-disabled')
      button.disabled = true
    }

    button.addEventListener('pointerdown', () => {
      state.drawing = true
      appendSequence(state.tool, node)
    })
    button.addEventListener('pointerenter', () => {
      if (!state.drawing) {
        return
      }
      appendSequence(state.tool, node)
    })
    button.addEventListener('click', () => {
      if (state.tool === 'exclude') {
        appendSequence('exclude', node)
      }
    })
    nodeLayer.append(button)
  })

  target.append(nodeLayer)
}

function renderSequences() {
  elements.prefixDisplay.textContent = state.config.path_prefix.join('') || '-'
  elements.excludedDisplay.textContent =
    state.config.excluded_nodes.join(', ') || '-'
  elements.suffixDisplay.textContent = state.config.path_suffix.join('') || '-'
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

function clampNumber(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function syncLengthControls(source) {
  const minLength = Number(state.meta?.min_path_length || 4)
  const maxLength = Number(state.meta?.max_path_length || state.config.grid_size ** 2)

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

  nextMin = clampNumber(Number.isFinite(nextMin) ? nextMin : minLength, minLength, maxLength)
  nextMax = clampNumber(Number.isFinite(nextMax) ? nextMax : maxLength, minLength, maxLength)

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

function renderProgress() {
  const snapshot = state.snapshot
  if (!snapshot) {
    return
  }
  const total = snapshot.total_paths
  const tested = snapshot.paths_tested || 0
  const percent = total ? (tested / total) * 100 : 0
  elements.progressLabel.textContent = `${tested.toLocaleString()} / ${total ? total.toLocaleString() : 'Unknown'}`
  elements.progressPercent.textContent = `${percent.toFixed(2)}%`
  elements.progressBar.style.width = `${Math.max(0, Math.min(percent, 100))}%`
  elements.statusValue.textContent = snapshot.status || 'Idle'
  elements.currentPathValue.textContent = snapshot.current_path || '-'
  elements.totalPathsValue.textContent = total
    ? total.toLocaleString()
    : snapshot.total_paths_state || 'Unknown'
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
  drawBoard(
    elements.liveBoard,
    (snapshot.current_path || '').split('').filter(Boolean),
  )
}

function renderLogs() {
  const logs = state.logs.slice(0, 150)
  if (!logs.length) {
    elements.logTableBody.innerHTML =
      '<tr><td colspan="4" class="empty-cell">No attempts yet.</td></tr>'
    return
  }
  elements.logTableBody.innerHTML = logs
    .map((entry) => {
      return `
        <tr>
          <td>${formatTimestamp(entry.timestamp)}</td>
          <td>${entry.attempt || '-'}</td>
          <td>${entry.result_classification || '-'}</td>
          <td>${entry.response || '-'}</td>
        </tr>`
    })
    .join('')
}

function renderAll() {
  renderValidation()
  renderSuccessNotice()
  renderInputs()
  renderSequences()
  drawBoard(
    elements.patternBoard,
    (state.snapshot?.current_path || '').split('').filter(Boolean),
    { showConstraintOrder: true },
  )
  renderProgress()
  renderLogs()
  elements.toolButtons.forEach((button) => {
    const isActive = button.dataset.tool === state.tool
    button.classList.toggle('is-active', isActive)
    button.setAttribute('aria-pressed', String(isActive))
  })
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!response.ok) {
    const payload = await response
      .json()
      .catch(() => ({ detail: [response.statusText] }))
    const detail = Array.isArray(payload.detail)
      ? payload.detail.join(' | ')
      : payload.detail
    throw new Error(detail || response.statusText)
  }
  return response.json()
}

function collectMode() {
  return [
    elements.modeA.checked ? 'a' : null,
    elements.modeT.checked ? 't' : null,
    elements.modeP.checked ? 'p' : null,
  ]
    .filter(Boolean)
    .join('')
}

async function writeClipboardText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'absolute'
  textarea.style.left = '-9999px'
  document.body.append(textarea)
  textarea.select()

  try {
    const copied = document.execCommand('copy')
    if (!copied) {
      throw new Error('Copy command was rejected by the browser')
    }
  } finally {
    textarea.remove()
  }
}

function escapeCsvValue(value) {
  const text = value == null ? '' : String(value)
  return `"${text.replaceAll('"', '""')}"`
}

function downloadTextFile(filename, text, mimeType) {
  const blob = new Blob([text], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

function buildCurrentConfigPayload() {
  syncConfigFromInputs()
  return {
    ...state.config,
    path_prefix: [...(state.config.path_prefix || [])],
    path_suffix: [...(state.config.path_suffix || [])],
    excluded_nodes: [...(state.config.excluded_nodes || [])],
    test_path: [...(state.config.test_path || [])],
  }
}

async function copyConfigToClipboard() {
  const serialized = JSON.stringify(buildCurrentConfigPayload(), null, 2)
  const originalLabel = elements.copyConfigButton.textContent

  try {
    await writeClipboardText(serialized)
    elements.copyConfigButton.textContent = 'Copied'
  } catch (error) {
    flashValidation([`Unable to copy config: ${error.message}`])
    return
  }

  window.setTimeout(() => {
    elements.copyConfigButton.textContent = originalLabel
  }, 1400)
}

function downloadLogsAsCsv() {
  const rows = state.logs.slice(0, 150)
  if (!rows.length) {
    flashValidation(['No log entries available to export.'])
    return
  }

  const header = ['timestamp', 'path', 'result', 'duration_ms', 'response']
  const body = rows.map((entry) => [
    formatTimestamp(entry.timestamp),
    entry.attempt || '',
    entry.result_classification || '',
    entry.duration_ms == null ? '' : Number(entry.duration_ms).toFixed(1),
    entry.response || '',
  ])

  const csv = [header, ...body]
    .map((row) => row.map((value) => escapeCsvValue(value)).join(','))
    .join('\n')
  const stamp = new Date().toISOString().replaceAll(':', '-').replace(/\..+$/, '')
  downloadTextFile(`gapbf-log-${stamp}.csv`, csv, 'text/csv;charset=utf-8')
}

function syncConfigFromInputs() {
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

async function validateDraft() {
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

async function loadConfig(path) {
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

async function saveConfig(path) {
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

async function fetchInitialState() {
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

function subscribeEvents() {
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

function startStatePolling() {
  if (statePollTimer !== null) {
    return
  }

  statePollTimer = window.setInterval(async () => {
    if (statePollInFlight) {
      return
    }

    if (!state.snapshot?.active && elements.connectionBadge.textContent === 'API ready') {
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

function bindInputs() {
  ;[3, 4, 5, 6].forEach((size) => {
    const option = document.createElement('option')
    option.value = String(size)
    option.textContent = `${size} x ${size}`
    elements.gridSize.append(option)
  })

  document.addEventListener('pointerup', () => {
    state.drawing = false
  })

  elements.toolButtons.forEach((button) => {
    button.addEventListener('click', () => {
      selectTool(button.dataset.tool)
    })
    button.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        selectTool(button.dataset.tool)
      }
    })
  })

  elements.clearPrefixButton.addEventListener('click', (event) => {
    event.stopPropagation()
    clearSequence('prefix')
  })
  elements.clearExcludedButton.addEventListener('click', (event) => {
    event.stopPropagation()
    clearSequence('exclude')
  })
  elements.clearSuffixButton.addEventListener('click', (event) => {
    event.stopPropagation()
    clearSequence('suffix')
  })
  elements.loadConfigButton.addEventListener('click', () =>
    loadConfig(elements.configPath.value),
  )
  elements.copyConfigButton.addEventListener('click', () => {
    void copyConfigToClipboard()
  })
  elements.downloadCsvButton.addEventListener('click', downloadLogsAsCsv)
  elements.saveConfigButton.addEventListener('click', () =>
    saveConfig(elements.configPath.value),
  )

  elements.pathMinLength.addEventListener('input', () => {
    syncLengthControls('min-range')
  })
  elements.pathMinLengthNumber.addEventListener('input', () => {
    syncLengthControls('min-number')
  })
  elements.pathMaxLength.addEventListener('input', () => {
    syncLengthControls('max-range')
  })
  elements.pathMaxLengthNumber.addEventListener('input', () => {
    syncLengthControls('max-number')
  })

  elements.gridSize.addEventListener('change', async () => {
    syncConfigFromInputs()
    const gridSize = Number(elements.gridSize.value)
    clearBoardSelections()
    applyGridConfig(
      gridSize,
      await api(`/api/config/meta?grid_size=${gridSize}`),
      { forceMaxLength: true },
    )
    renderAll()
  })

  elements.startButton.addEventListener('click', async () => {
    if (!collectMode()) {
      flashValidation(['Select at least one mode.'])
      return
    }
    const valid = await validateDraft()
    if (!valid) {
      return
    }
    try {
      updateSnapshot(
        await api('/api/run/start', {
        method: 'POST',
        body: JSON.stringify({ mode: collectMode(), config: state.config }),
        }),
        { preserveNotifications: false },
      )
      renderAll()
    } catch (error) {
      flashValidation([error.message])
    }
  })

  elements.pauseButton.addEventListener('click', async () => {
    updateSnapshot(await api('/api/run/pause', {
      method: 'POST',
      body: JSON.stringify({}),
    }))
    renderAll()
  })

  elements.resumeButton.addEventListener('click', async () => {
    updateSnapshot(await api('/api/run/resume', {
      method: 'POST',
      body: JSON.stringify({}),
    }))
    renderAll()
  })

  elements.stopButton.addEventListener('click', async () => {
    updateSnapshot(await api('/api/run/stop', {
      method: 'POST',
      body: JSON.stringify({}),
    }))
    renderAll()
  })
  ;[
    elements.pathMinLengthNumber,
    elements.pathMaxLengthNumber,
    elements.attemptDelay,
    elements.adbTimeout,
    elements.pathMaxNodeDistance,
    elements.echoCommands,
    elements.stdoutSuccess,
    elements.stdoutNormal,
    elements.stdoutError,
    elements.dbPath,
    elements.testPath,
    elements.totalPaths,
  ].forEach((input) => {
    input.addEventListener('change', () => {
      state.validationErrors = []
      syncConfigFromInputs()
      renderAll()
    })
  })
}

async function init() {
  mountTopLinks(document.querySelector('#topLinks'))
  bindTooltips()
  bindInputs()
  await fetchInitialState()
  subscribeEvents()
  startStatePolling()
}

init()
