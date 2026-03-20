import { mountTopLinks } from '../components/topLinks.js'
import {
  appendSequence,
  clearBoardSelections,
  clearSequence,
  selectTool,
} from './board.js'
import {
  calculateTotalPaths,
  loadConfig,
  resetDashboard,
  saveConfig,
  syncConfigFromInputs,
  validateDraft,
} from './config.js'
import { api, buildCsv, downloadTextFile, writeClipboardText } from './io.js'
import {
  flashValidation,
  formatTimestamp,
  updateSnapshot,
} from './notifications.js'
import { applyGridConfig, renderAll, syncLengthControls } from './render.js'
import {
  fetchInitialState,
  startStatePolling,
  subscribeEvents,
} from './runtime.js'
import { elements, state } from './state.js'
import { bindTooltips } from './tooltip.js'

function collectMode() {
  return [
    elements.modeA.checked ? 'a' : null,
    elements.modeT.checked ? 't' : null,
    elements.modeP.checked ? 'p' : null,
  ]
    .filter(Boolean)
    .join('')
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

  const csv = buildCsv([header, ...body])
  const stamp = new Date()
    .toISOString()
    .replaceAll(':', '-')
    .replace(/\..+$/, '')
  downloadTextFile(`gapbf-log-${stamp}.csv`, csv, 'text/csv;charset=utf-8')
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
      selectTool(button.dataset.tool, renderAll)
    })
    button.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        selectTool(button.dataset.tool, renderAll)
      }
    })
  })

  elements.clearPrefixButton.addEventListener('click', (event) => {
    event.stopPropagation()
    clearSequence('prefix', renderAll)
  })
  elements.clearExcludedButton.addEventListener('click', (event) => {
    event.stopPropagation()
    clearSequence('exclude', renderAll)
  })
  elements.clearSuffixButton.addEventListener('click', (event) => {
    event.stopPropagation()
    clearSequence('suffix', renderAll)
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
  elements.calculateTotalPathsButton.addEventListener('click', () => {
    void calculateTotalPaths()
  })

  elements.pathMinLength.addEventListener('input', () =>
    syncLengthControls('min-range'),
  )
  elements.pathMinLengthNumber.addEventListener('input', () =>
    syncLengthControls('min-number'),
  )
  elements.pathMaxLength.addEventListener('input', () =>
    syncLengthControls('max-range'),
  )
  elements.pathMaxLengthNumber.addEventListener('input', () =>
    syncLengthControls('max-number'),
  )

  elements.gridSize.addEventListener('change', async () => {
    syncConfigFromInputs()
    const gridSize = Number(elements.gridSize.value)
    clearBoardSelections()
    applyGridConfig(
      gridSize,
      await api(`/api/config/meta?grid_size=${gridSize}`),
      {
        forceMaxLength: true,
      },
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
    updateSnapshot(
      await api('/api/run/pause', { method: 'POST', body: JSON.stringify({}) }),
    )
    renderAll()
  })
  elements.resumeButton.addEventListener('click', async () => {
    updateSnapshot(
      await api('/api/run/resume', {
        method: 'POST',
        body: JSON.stringify({}),
      }),
    )
    renderAll()
  })
  elements.stopButton.addEventListener('click', async () => {
    updateSnapshot(
      await api('/api/run/stop', { method: 'POST', body: JSON.stringify({}) }),
    )
    renderAll()
  })
  elements.resetButton.addEventListener('click', () => {
    void resetDashboard(collectMode() || 'a')
  })
  ;[
    elements.pathMinLengthNumber,
    elements.pathMaxLengthNumber,
    elements.attemptDelay,
    elements.adbTimeout,
    elements.pathMaxNodeDistance,
    elements.echoCommands,
    elements.noDiagonalCrossings,
    elements.noPerpendicularCrossings,
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

export async function init() {
  mountTopLinks(document.querySelector('#topLinks'))
  bindTooltips()
  bindInputs()
  await fetchInitialState()
  subscribeEvents()
  startStatePolling()
}
