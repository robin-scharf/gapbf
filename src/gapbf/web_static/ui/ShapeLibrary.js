import { api } from './api.js'
import { Board } from './Board.js'
import { html, useEffect, useState } from './html.js'
import { getState, setConfig, useStore } from './store.js'

function pathPaint(path) {
  const p = {}
  ;[...path].forEach((n, i) => (p[n] = i === 0 ? 'paint-start' : 'paint-on'))
  return p
}

// category order: digits < letters < common shapes
const category = (tags) =>
  tags.includes('digit') ? 0 : tags.includes('letter') || tags.includes('initial') ? 1 : 2

export function ShapeLibraryModal({ onClose }) {
  const { config } = useStore()
  const [lib, setLib] = useState(null)
  const [dictPath, setDictPath] = useState(config.shape_dict_path || '')
  const [sort, setSort] = useState('length')

  const load = async () => {
    setLib(null)
    try {
      setLib(
        await api('/api/shapes/library', {
          method: 'POST',
          body: JSON.stringify({ config: getState().config }),
        }),
      )
    } catch (e) {
      setLib({ error: e.message })
    }
  }
  useEffect(() => {
    void load()
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const shapes = lib?.shapes || []
  const sorted = [...shapes].sort((a, b) => {
    const byLen = a.path.length - b.path.length
    const byCat = category(a.tags) - category(b.tags)
    const byName = a.name.localeCompare(b.name)
    return sort === 'length' ? byLen || byCat || byName : byCat || byLen || byName
  })
  const allNames = shapes.map((s) => s.name)
  const allSelected = !(config.shape_names || []).length
  const isSel = (name) => allSelected || (config.shape_names || []).includes(name)

  const toggle = (name) => {
    const cur = new Set(allSelected ? allNames : config.shape_names)
    if (cur.has(name)) cur.delete(name)
    else cur.add(name)
    setConfig({ shape_names: cur.size === allNames.length ? [] : [...cur] })
  }
  const loadDict = () => {
    setConfig({ shape_dict_path: dictPath })
    void load()
  }

  return html`
    <div class="modal-overlay" onclick=${onClose}>
      <div class="modal" onclick=${(e) => e.stopPropagation()}>
        <div class="modal-head">
          <div>
            <p class="section-label">Shape library</p>
            <h3>Pick which shapes to try</h3>
          </div>
          <button class="chip-clear modal-close" onclick=${onClose}>×</button>
        </div>
        <div class="modal-toolbar">
          <span class="muted">
            ${allSelected ? `All ${shapes.length} shapes` : `${(config.shape_names || []).length} of ${shapes.length} selected`}
          </span>
          <button class="button button-ghost" onclick=${() => setConfig({ shape_names: [] })}>Use all</button>
          <label class="sort-select">Sort
            <select value=${sort} onchange=${(e) => setSort(e.target.value)}>
              <option value="length">by length</option>
              <option value="category">digits, letters, shapes</option>
            </select>
          </label>
          <input type="text" placeholder="custom shapes JSON path (optional)" value=${dictPath}
            oninput=${(e) => setDictPath(e.target.value)} />
          <button class="button button-ghost" onclick=${loadDict}>Load file</button>
        </div>
        ${lib?.error ? html`<p class="shape-preview error">${lib.error}</p>` : null}
        ${!lib ? html`<p class="muted">Loading…</p>` : null}
        <div class="shape-grid">
          ${sorted.map(
            (s) => html`
              <button
                type="button"
                class="shape-card ${isSel(s.name) ? 'is-selected' : ''}"
                title=${s.tags.join(', ')}
                onclick=${() => toggle(s.name)}
              >
                <${Board} gridSize=${lib.grid_size} paint=${pathPaint(s.path)} interactive=${false} mini=${true} />
                <span class="shape-card-name">${s.name}</span>
              </button>
            `,
          )}
        </div>
      </div>
    </div>
  `
}
