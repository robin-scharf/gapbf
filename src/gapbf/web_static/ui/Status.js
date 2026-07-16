import { html } from './html.js'
import { useStore } from './store.js'

const row = (k, v) =>
  html`<div class="stat-row"><span>${k}</span><strong>${v}</strong></div>`

export function StatusPanel() {
  const { snapshot } = useStore()
  const s = snapshot || {}
  const total = s.total_paths
  const tested = s.paths_tested || 0
  const percent = total ? Math.min(100, (tested / total) * 100) : 0
  return html`
    <section class="panel panel-status">
      <div class="section-head section-head-status">
        <div><p class="section-label">Status</p><h2>Live state</h2></div>
        <div class="progress-inline">
          <div class="progress-head">
            <span>${tested.toLocaleString()} / ${total ? total.toLocaleString() : 'Unknown'}</span>
            <span>${percent.toFixed(2)}%</span>
          </div>
          <div class="progress-bar-track">
            <div class="progress-bar-fill" style=${`width:${percent}%`}></div>
          </div>
        </div>
      </div>
      <div class="stats-list">
        ${row('Device', s.device_id || '—')}
        ${row('Status', s.status || 'idle')}
        ${row('Current path', s.current_path ? html`<span class="mono">${s.current_path}</span>` : '—')}
        ${row('Total paths', total ? total.toLocaleString() : 'Unknown')}
        ${row('Feedback', s.last_feedback || '—')}
        ${row('Started', s.started_at || '—')}
        ${row('Finished', s.finished_at || '—')}
      </div>
    </section>
  `
}

export function LogPanel() {
  const { logs } = useStore()
  return html`
    <section class="panel panel-log">
      <div class="section-head">
        <div><p class="section-label">Activity</p><h2>Recent attempts</h2></div>
        <span class="muted">${logs.length ? `${logs.length} shown` : ''}</span>
      </div>
      <div class="log-scroll">
        <table class="log-table">
          <thead>
            <tr><th>Time</th><th>Path</th><th>Result</th><th>Response</th></tr>
          </thead>
          <tbody>
            ${logs.length
              ? logs.map(
                  (l) => html`
                    <tr>
                      <td class="muted">${(l.timestamp || '').slice(11, 19)}</td>
                      <td class="mono">${l.attempt}</td>
                      <td><span class="pill pill-${l.result_classification || 'unknown'}">${l.result_classification || '—'}</span></td>
                      <td class="muted ellipsis">${l.response || ''}</td>
                    </tr>
                  `,
                )
              : html`<tr><td colspan="4" class="muted empty-row">No attempts yet — start a run to see activity.</td></tr>`}
          </tbody>
        </table>
      </div>
    </section>
  `
}
