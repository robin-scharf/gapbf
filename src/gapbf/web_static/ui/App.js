import { ControlsBar } from './Controls.js'
import { GraphPanel } from './Graph.js'
import { Fragment, html, useEffect } from './html.js'
import { SettingsPanel } from './Settings.js'
import { ShapePanel } from './Shape.js'
import { LogPanel, StatusPanel } from './Status.js'
import { set, setConfig, useStore } from './store.js'

const HINTS = {
  graph:
    'Enumerate the full legal pattern space, ordered by your length, distance and crossing constraints.',
  shape:
    'Try human shapes first — initials, letters, lines — expanded into every plausible variation and ranked by real-world pattern data.',
}

function StatusPill() {
  const { connection, snapshot } = useStore()
  const runStatus = snapshot?.status
  const showRun = runStatus && runStatus !== 'idle'
  const kind = showRun ? runStatus : connection
  const text = showRun ? runStatus : connection
  return html`<span class="badge badge-dot badge-${kind}">${text}</span>`
}

function ModeSwitch() {
  const { config } = useStore()
  const mode = config.search_mode === 'graph' ? 'graph' : 'shape'
  return html`
    <div class="mode-switch">
      <div class="mode-tabs" role="tablist" aria-label="Search mode">
        <button
          class="mode-tab ${mode === 'graph' ? 'is-active' : ''}"
          role="tab"
          aria-selected=${mode === 'graph'}
          onclick=${() => setConfig({ search_mode: 'graph' })}
        >
          Graph search
        </button>
        <button
          class="mode-tab ${mode === 'shape' ? 'is-active' : ''}"
          role="tab"
          aria-selected=${mode === 'shape'}
          onclick=${() => setConfig({ search_mode: 'shape' })}
        >
          Shape search
        </button>
      </div>
      <p class="mode-hint">${HINTS[mode]}</p>
    </div>
  `
}

function Toasts() {
  const { validationErrors, successPath } = useStore()
  useEffect(() => {
    if (validationErrors.length) {
      const t = setTimeout(() => set({ validationErrors: [] }), 4500)
      return () => clearTimeout(t)
    }
  }, [validationErrors])
  if (!validationErrors.length && !successPath) return null
  return html`
    <div class="toast-stack">
      ${validationErrors.map(
        (e, i) => html`
          <div class="toast toast-error" key=${i}>
            <span>${e}</span>
            <button class="chip-clear" onclick=${() => set({ validationErrors: [] })}>×</button>
          </div>
        `,
      )}
      ${successPath
        ? html`<div class="toast toast-success">
            <span>🎉 Pattern found: <strong class="mono">${Array.isArray(successPath) ? successPath.join('') : successPath}</strong></span>
            <button class="chip-clear" onclick=${() => set({ successPath: null })}>×</button>
          </div>`
        : null}
    </div>
  `
}

export function App() {
  const { config } = useStore()
  const mode = config.search_mode === 'graph' ? 'graph' : 'shape'
  return html`
    <${Fragment}>
      <div class="app-shell">
        <header class="topbar">
          <div>
            <h1>GAPBF</h1>
            <p class="overline">Android pattern recovery console</p>
          </div>
          <div class="status-strip"><${StatusPill} /></div>
        </header>
        <${ModeSwitch} />
        <main class="dashboard-grid" data-search-mode=${config.search_mode}>
          <${SettingsPanel} />
          ${mode === 'graph' ? html`<${GraphPanel} />` : html`<${ShapePanel} />`}
          <${ControlsBar} />
          <${StatusPanel} />
          <${LogPanel} />
        </main>
      </div>
      <${Toasts} />
    </${Fragment}>
  `
}
