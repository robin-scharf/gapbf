import { elements, state } from './state.js'

export function flashValidation(errors) {
  state.validationErrors = errors
  renderNotifications()
}

export function flashMessage(message) {
  state.validationErrors = [message]
  renderNotifications()
}

export function formatTimestamp(value) {
  if (!value) {
    return '-'
  }

  const text = String(value).trim()
  if (!text) {
    return '-'
  }

  return text.replace('T', ' ').replace(/(?:Z|[+-]\d{2}:\d{2})$/, '')
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

export function renderNotifications() {
  renderValidation()
  renderSuccessNotice()
}

export function updateSnapshot(snapshot, options = {}) {
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

export function createIdleSnapshot(defaultConfigPath, mode = 'a') {
  return {
    default_config_path: defaultConfigPath,
    active: false,
    status: 'idle',
    mode,
    config: null,
    paths_tested: 0,
    total_paths: null,
    total_paths_state: 'unknown',
    total_paths_elapsed_seconds: 0,
    total_paths_timeout_seconds: 30,
    current_path: '',
    last_feedback: 'Ready',
    device_id: null,
    resume_info: null,
    started_at: null,
    finished_at: null,
    successful_path: null,
    error_message: null,
    paused: false,
    stop_requested: false,
    run_id: null,
    log_tail: [],
  }
}
