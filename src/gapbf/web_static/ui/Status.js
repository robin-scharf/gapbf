import { html, useEffect, useState } from './html.js'
import { useStore } from './store.js'

const row = (k, v) =>
  html`<div class="stat-row"><span>${k}</span><strong>${v}</strong></div>`

function parseTs(ts) {
  if (!ts) return null
  const d = new Date(ts)
  return Number.isNaN(d.getTime()) ? null : d
}
function fmtClock(ts) {
  const d = parseTs(ts)
  return d ? d.toLocaleString() : '—'
}
function fmtElapsed(sec) {
  if (sec == null || sec < 0) return '—'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = Math.floor(sec % 60)
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export function StatusPanel() {
  const { snapshot } = useStore()
  const s = snapshot || {}
  const [, tick] = useState(0)

  const running = s.status === 'running'
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [running])

  const total = s.total_paths
  const tested = s.paths_tested || 0
  const percent = total ? Math.min(100, (tested / total) * 100) : 0
  const started = parseTs(s.started_at)
  const finished = parseTs(s.finished_at)
  const elapsedSec = started ? ((finished || new Date()) - started) / 1000 : null

  return html`
    <section class="panel panel-status">
      <div class="section-head">
        <div><p class="section-label">Status</p><h2>Live state</h2></div>
        <span class="pill pill-${s.status || 'idle'}">${s.status || 'idle'}</span>
      </div>
      <div class="status-cols">
        <div class="status-col">
          ${row('Device', s.device_id ? html`<span class="mono">${s.device_id}</span>` : '—')}
          ${row('Status', s.status || 'idle')}
          ${row('Feedback', s.last_feedback || '—')}
        </div>
        <div class="status-col">
          <div class="stat-row stat-progress">
            <span>Progress</span>
            <div class="progress-mini">
              <div class="progress-mini-head">
                <span>${tested.toLocaleString()} / ${total ? total.toLocaleString() : '—'}</span>
                <span>${percent.toFixed(1)}%</span>
              </div>
              <div class="progress-bar-track">
                <div class="progress-bar-fill" style=${`width:${percent}%`}></div>
              </div>
            </div>
          </div>
          ${row('Current path', s.current_path ? html`<span class="mono">${s.current_path}</span>` : '—')}
          ${row('Total paths', total ? total.toLocaleString() : 'Unknown')}
        </div>
        <div class="status-col">
          ${row('Started', fmtClock(s.started_at))}
          ${row('Elapsed', fmtElapsed(elapsedSec))}
          ${row('Finished', fmtClock(s.finished_at))}
        </div>
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
