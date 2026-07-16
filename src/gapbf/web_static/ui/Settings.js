import { configMeta, loadConfigFile, saveConfigFile } from './api.js'
import { html, useState } from './html.js'
import { getState, set, setConfig, useStore } from './store.js'

function Hint({ text }) {
  return html`<span class="field-hint" tabindex="0" title=${text} aria-label=${text}>i</span>`
}

export function SettingsPanel() {
  const { config, meta } = useStore()
  const [saved, setSaved] = useState('')

  const num = (key) => (e) => setConfig({ [key]: Number(e.target.value) })
  const str = (key) => (e) => setConfig({ [key]: e.target.value })
  const bool = (key) => (e) => setConfig({ [key]: e.target.checked })

  const maxLen = meta?.max_path_length || config.grid_size ** 2
  const maxDist = meta?.max_path_max_node_distance || config.grid_size - 1

  const onGrid = async (e) => {
    const grid = Number(e.target.value)
    setConfig({ grid_size: grid })
    try {
      const m = await configMeta(grid)
      const cfg = getState().config
      const valid = new Set(m.nodes)
      setConfig({
        grid_size: grid,
        path_max_length: Math.min(cfg.path_max_length, m.max_path_length),
        path_min_length: Math.min(cfg.path_min_length, m.max_path_length),
        path_max_node_distance: Math.min(
          cfg.path_max_node_distance,
          m.max_path_max_node_distance,
        ),
        path_prefix: (cfg.path_prefix || []).filter((n) => valid.has(n)),
        path_suffix: (cfg.path_suffix || []).filter((n) => valid.has(n)),
        excluded_nodes: (cfg.excluded_nodes || []).filter((n) => valid.has(n)),
      })
      set({ meta: m })
    } catch {
      /* ignore meta fetch errors */
    }
  }

  const save = async () => {
    try {
      const r = await saveConfigFile(config.config_file_path, getState().config)
      set({ config: r.config, meta: r.meta })
      setSaved('Saved ✓')
      setTimeout(() => setSaved(''), 1600)
    } catch (e) {
      set({ validationErrors: [e.message] })
    }
  }
  const load = async () => {
    try {
      const r = await loadConfigFile(config.config_file_path)
      set({ config: r.config, meta: r.meta })
    } catch (e) {
      set({ validationErrors: [e.message] })
    }
  }

  return html`
    <section class="panel panel-settings">
      <div class="section-head">
        <div><p class="section-label">Configure</p><h2>Search settings</h2></div>
        <span class="muted save-note">${saved}</span>
      </div>

      <div class="settings-stack">
        <div class="subsection">
          <p class="section-label">Search space</p>
          <div class="form-grid">
            <label class="field">
              <span class="field-label-row">Grid size<${Hint} text="Android pattern grid. Updates valid nodes and limits." /></span>
              <select value=${String(config.grid_size)} onchange=${onGrid}>
                ${[3, 4, 5, 6].map((n) => html`<option value=${n}>${n} × ${n}</option>`)}
              </select>
            </label>
            <label class="field">
              <span class="field-label-row">Min length<${Hint} text="Shortest pattern to try (Android minimum is 4)." /></span>
              <input type="number" min="4" max=${maxLen} value=${config.path_min_length} onchange=${num('path_min_length')} />
            </label>
            <label class="field">
              <span class="field-label-row">Max length<${Hint} text="Longest pattern to generate." /></span>
              <input type="number" min="4" max=${maxLen} value=${config.path_max_length} onchange=${num('path_max_length')} />
            </label>
            <label class="field">
              <span class="field-label-row">Move distance<${Hint} text="Cap on how far a single move may travel. Lower prunes long jumps." /></span>
              <input type="number" min="1" max=${maxDist} value=${config.path_max_node_distance} onchange=${num('path_max_node_distance')} />
            </label>
          </div>
          <div class="toggle-row">
            <label class="toggle-pill"><input type="checkbox" checked=${config.no_diagonal_crossings} onchange=${bool('no_diagonal_crossings')} />No diagonal crossings</label>
            <label class="toggle-pill"><input type="checkbox" checked=${config.no_perpendicular_crossings} onchange=${bool('no_perpendicular_crossings')} />No perpendicular crossings</label>
          </div>
        </div>

        <div class="subsection">
          <p class="section-label">Device & matching</p>
          <div class="form-grid">
            <label class="field">
              <span class="field-label-row">Attempt delay (s)<${Hint} text="Wait between attempts. TWRP enforces a hidden ~10s throttle — do not go below ~10." /></span>
              <input type="number" step="0.1" min="0" value=${config.attempt_delay} onchange=${num('attempt_delay')} />
            </label>
            <label class="field">
              <span class="field-label-row">ADB timeout (s)</span>
              <input type="number" min="1" value=${config.adb_timeout} onchange=${num('adb_timeout')} />
            </label>
            <label class="field field-wide">
              <span class="field-label-row">Success marker</span>
              <input type="text" value=${config.stdout_success} placeholder="Data successfully decrypted" onchange=${str('stdout_success')} />
            </label>
            <label class="field field-wide">
              <span class="field-label-row">Failure marker</span>
              <input type="text" value=${config.stdout_normal} placeholder="Failed to decrypt" onchange=${str('stdout_normal')} />
            </label>
            <label class="field field-wide">
              <span class="field-label-row">Database path</span>
              <input type="text" value=${config.db_path} onchange=${str('db_path')} />
            </label>
          </div>
          <div class="toggle-row">
            <label class="toggle-pill"><input type="checkbox" checked=${config.echo_commands} onchange=${bool('echo_commands')} />Echo pattern in command</label>
          </div>
        </div>

        <div class="subsection">
          <p class="section-label">Config file</p>
          <div class="config-path-row">
            <input type="text" value=${config.config_file_path} onchange=${str('config_file_path')} />
            <button class="button button-ghost" onclick=${load}>Load</button>
            <button class="button button-ghost" onclick=${save}>Save</button>
          </div>
        </div>
      </div>
    </section>
  `
}
