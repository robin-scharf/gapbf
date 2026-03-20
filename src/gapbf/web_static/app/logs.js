import { formatTimestamp } from './notifications.js'
import { elements, state } from './state.js'

export function renderLogs() {
  const logs = state.logs.slice(0, 150)
  if (!logs.length) {
    elements.logTableBody.innerHTML =
      '<tr><td colspan="4" class="empty-cell">No attempts yet.</td></tr>'
    return
  }
  elements.logTableBody.innerHTML = logs
    .map(
      (entry) => `
        <tr>
          <td>${formatTimestamp(entry.timestamp)}</td>
          <td>${entry.attempt || '-'}</td>
          <td>${entry.result_classification || '-'}</td>
          <td>${entry.response || '-'}</td>
        </tr>`,
    )
    .join('')
}