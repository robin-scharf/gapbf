import { ControlsBar } from './Controls.js'
import { GraphPanel } from './Graph.js'
import { Fragment, html } from './html.js'
import { SettingsPanel } from './Settings.js'
import { ShapePanel } from './Shape.js'
import { LogPanel, StatusPanel } from './Status.js'
import { setConfig, useStore } from './store.js'

const HINTS = {
  graph:
    'Enumerate the full legal pattern space, ordered by your length, distance and crossing constraints.',
  shape:
    'Try human shapes first — initials, letters, lines — expanded into every plausible variation and ranked by real-world pattern data.',
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

function Banners() {
  const { validationErrors, successPath } = useStore()
  return html`
    <${Fragment}>
      ${validationErrors.length
        ? html`<div class="validation-banner">${validationErrors.join(' · ')}</div>`
        : null}
      ${successPath
        ? html`<div class="status-banner status-banner-success">
            🎉 Pattern found:
            <strong class="mono">${Array.isArray(successPath) ? successPath.join('') : successPath}</strong>
          </div>`
        : null}
    </${Fragment}>
  `
}

export function App() {
  const { config, connection, snapshot } = useStore()
  const mode = config.search_mode === 'graph' ? 'graph' : 'shape'
  const running = snapshot?.status || 'idle'
  return html`
    <div class="app-shell">
      <header class="topbar">
        <div>
          <h1>GAPBF</h1>
          <p class="overline">Android pattern recovery console</p>
        </div>
        <div class="status-strip">
          <span class="badge badge-dot badge-${connection}">${connection}</span>
          <span class="badge badge-muted">${running}</span>
        </div>
      </header>
      <${Banners} />
      <${ModeSwitch} />
      <main class="dashboard-grid" data-search-mode=${config.search_mode}>
        <${SettingsPanel} />
        ${mode === 'graph' ? html`<${GraphPanel} />` : html`<${ShapePanel} />`}
        <${StatusPanel} />
        <${LogPanel} />
        <${ControlsBar} />
      </main>
    </div>
  `
}
