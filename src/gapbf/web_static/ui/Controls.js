import {
  applySnapshot,
  calcTotalPaths,
  runPause,
  runResume,
  runStart,
  runStop,
  validateConfig,
} from './api.js'
import { html, useState } from './html.js'
import { getState, set, useStore } from './store.js'

const MODE_LABELS = { a: 'ADB', t: 'Test', p: 'Print' }

export function ControlsBar() {
  const { snapshot, runModes } = useStore()
  const [busy, setBusy] = useState(false)
  const active = !!snapshot?.active
  const controllable = !!snapshot?.controllable

  const modeString = () =>
    ['a', 't', 'p'].filter((k) => getState().runModes[k]).join('')

  const toggleMode = (k) =>
    set({ runModes: { ...getState().runModes, [k]: !getState().runModes[k] } })

  const guarded = (fn) => async () => {
    setBusy(true)
    try {
      applySnapshot(await fn())
    } catch (e) {
      set({ validationErrors: [e.message] })
    } finally {
      setBusy(false)
    }
  }

  const start = async () => {
    const mode = modeString()
    if (!mode) {
      set({ validationErrors: ['Select at least one run mode.'] })
      return
    }
    setBusy(true)
    try {
      const validated = await validateConfig(getState().config)
      set({ config: validated.config, meta: validated.meta, validationErrors: [] })
      applySnapshot(await runStart(mode, validated.config))
    } catch (e) {
      set({ validationErrors: [e.message] })
    } finally {
      setBusy(false)
    }
  }

  const calculate = guarded(() => calcTotalPaths(getState().config))

  return html`
    <section class="panel panel-controls">
      <div class="controls-inner">
        <div class="run-modes">
          <span class="section-label">Run modes</span>
          ${['a', 't', 'p'].map(
            (k) => html`
              <label class="toggle-pill">
                <input type="checkbox" checked=${runModes[k]} onchange=${() => toggleMode(k)} />
                ${MODE_LABELS[k]}
              </label>
            `,
          )}
        </div>
        <div class="controls-row">
          <button class="button button-ghost" disabled=${busy} onclick=${calculate}>
            Calculate total
          </button>
          <button class="button button-start" disabled=${busy || active} onclick=${start}>
            Start
          </button>
          <button class="button button-ghost" disabled=${!controllable} onclick=${guarded(runPause)}>
            Pause
          </button>
          <button
            class="button button-ghost"
            disabled=${!controllable}
            onclick=${guarded(runResume)}
          >
            Resume
          </button>
          <button class="button button-stop" disabled=${!active} onclick=${guarded(runStop)}>
            Stop
          </button>
        </div>
      </div>
    </section>
  `
}
