import { isLegalMove } from './pattern.js'
import { Board } from './Board.js'
import { html, useState } from './html.js'
import { setConfig, useStore } from './store.js'

const TOOLS = [
  { key: 'prefix', label: 'Prefix', configKey: 'path_prefix' },
  { key: 'exclude', label: 'Excluded', configKey: 'excluded_nodes' },
  { key: 'suffix', label: 'Suffix', configKey: 'path_suffix' },
]

export function GraphPanel() {
  const { config, snapshot } = useStore()
  const [tool, setTool] = useState('prefix')
  const grid = Number(config.grid_size)

  const paint = {}
  ;(config.path_prefix || []).forEach((n) => (paint[n] = 'paint-prefix'))
  ;(config.excluded_nodes || []).forEach((n) => (paint[n] = 'paint-excluded'))
  ;(config.path_suffix || []).forEach((n) => (paint[n] = 'paint-suffix'))
  ;(snapshot?.current_path || '').split('').forEach((n) => {
    if (!paint[n]) paint[n] = 'paint-live'
  })

  const onNode = (node) => {
    if (tool === 'exclude') {
      if (config.path_prefix.includes(node) || config.path_suffix.includes(node)) return
      const has = config.excluded_nodes.includes(node)
      setConfig({
        excluded_nodes: has
          ? config.excluded_nodes.filter((x) => x !== node)
          : [...config.excluded_nodes, node],
      })
      return
    }
    const key = tool === 'prefix' ? 'path_prefix' : 'path_suffix'
    const other = tool === 'prefix' ? 'path_suffix' : 'path_prefix'
    const seq = config[key]
    if (seq.includes(node) || config[other].includes(node) || config.excluded_nodes.includes(node))
      return
    if (seq.length > 0 && !isLegalMove(config, seq.at(-1), node, seq, config.excluded_nodes, grid))
      return
    setConfig({ [key]: [...seq, node] })
  }

  return html`
    <section class="panel panel-visualizer">
      <div class="section-head">
        <div><p class="section-label">Graph search</p><h2>Pattern builder</h2></div>
      </div>
      <div class="tool-tabs">
        ${TOOLS.map(
          (t) => html`
            <button
              type="button"
              class="tool-chip chip-${t.key} ${tool === t.key ? 'is-active' : ''}"
              onclick=${() => setTool(t.key)}
            >
              <span class="chip-name">${t.label}</span>
              <span class="chip-value mono">${(config[t.configKey] || []).join('') || '—'}</span>
              <span
                class="chip-clear"
                role="button"
                onclick=${(e) => {
                  e.stopPropagation()
                  setConfig({ [t.configKey]: [] })
                }}
                >×</span
              >
            </button>
          `,
        )}
      </div>
      <${Board} gridSize=${grid} paint=${paint} onNode=${onNode} />
      <p class="field-note">
        Select a tool, then draw a prefix/suffix you're sure of or exclude dots you never
        touched — every constraint shrinks the search.
      </p>
    </section>
  `
}
