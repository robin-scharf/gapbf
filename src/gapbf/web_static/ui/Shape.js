import { blockersBetween } from './pattern.js'
import { previewShapes } from './api.js'
import { Board } from './Board.js'
import { html, useState } from './html.js'
import { getState, setConfig, useStore } from './store.js'

export function ShapePanel() {
  const { config } = useStore()
  const grid = Number(config.grid_size)
  const [stroke, setStroke] = useState([])
  const [note, setNote] = useState('')
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)

  const addNode = (node) => {
    setStroke((cur) => {
      if (cur.includes(node)) return cur
      const next = [...cur]
      if (next.length > 0) {
        for (const b of blockersBetween(next.at(-1), node, grid)) {
          if (!next.includes(b)) next.push(b)
        }
      }
      if (!next.includes(node)) next.push(node)
      return next
    })
  }

  const paint = {}
  stroke.forEach((n, i) => (paint[n] = i === 0 ? 'paint-start' : 'paint-on'))

  const addShape = () => {
    if (stroke.length < 2) return
    setConfig({ drawn_shapes: [...(config.drawn_shapes || []), [...stroke]] })
    setStroke([])
    setNote('')
  }
  const removeShape = (i) =>
    setConfig({ drawn_shapes: config.drawn_shapes.filter((_, j) => j !== i) })

  const runPreview = async () => {
    setBusy(true)
    try {
      setPreview(await previewShapes(getState().config))
    } catch (e) {
      setPreview({ error: e.message })
    } finally {
      setBusy(false)
    }
  }

  const drawn = config.drawn_shapes || []

  return html`
    <section class="panel panel-shape">
      <div class="section-head">
        <div><p class="section-label">Step 1 · Draw</p><h2>Draw the pattern you remember</h2></div>
      </div>
      <p class="field-note">
        Trace the shape you think you used — your initials, a letter, a line. GAPBF scales,
        rotates and mirrors it into every plausible variation and tries those first.
      </p>

      <label class="field field-wildness">
        <span class="field-label-row">Variation breadth<span class="wild-badge">${config.shape_wildness}</span></span>
        <input
          type="range"
          min="0"
          max="3"
          value=${config.shape_wildness}
          oninput=${(e) => setConfig({ shape_wildness: Number(e.target.value) })}
        />
        <small class="field-note">0 = exact only · 3 = broadest (more candidates, longer run)</small>
      </label>

      <${Board} gridSize=${grid} paint=${paint} onNode=${addNode} />

      <div class="shape-actions">
        <span class="current-seq">Current: <span class="mono strong">${stroke.join('') || '—'}</span></span>
        <input
          type="text"
          placeholder="note (optional)"
          maxlength="80"
          value=${note}
          oninput=${(e) => setNote(e.target.value)}
        />
        <button class="button button-ghost" onclick=${addShape}>Add shape</button>
        <button class="button button-ghost" onclick=${() => setStroke([])}>Clear</button>
      </div>

      <p class="section-label">Shapes to try first</p>
      <ul class="drawn-list">
        ${drawn.length
          ? drawn.map(
              (s, i) => html`
                <li class="drawn-item">
                  <span class="mono">${Array.isArray(s) ? s.join('') : s}</span>
                  <button class="chip-clear" onclick=${() => removeShape(i)}>×</button>
                </li>
              `,
            )
          : html`<li class="drawn-item muted">No shapes added yet.</li>`}
      </ul>

      <div class="shape-preview-row">
        <button class="button button-ghost" disabled=${busy} onclick=${runPreview}>
          ${busy ? 'Previewing…' : 'Preview candidates'}
        </button>
      </div>
      ${preview && !preview.error
        ? html`<div class="shape-preview">
            <strong>${preview.count.toLocaleString()}</strong> candidates ·
            ${preview.king_count.toLocaleString()} king-move first ·
            ~${(preview.eta_seconds / 3600).toFixed(1)} h<br />
            <span class="mono muted">first: ${preview.sample.slice(0, 8).join('  ')}</span>
          </div>`
        : null}
      ${preview?.error ? html`<div class="shape-preview error">${preview.error}</div>` : null}
    </section>
  `
}
