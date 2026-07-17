import { blockersBetween } from './pattern.js'
import { api, previewShapes } from './api.js'
import { Board } from './Board.js'
import { Fragment, html, useEffect, useState } from './html.js'
import { ShapeLibraryModal } from './ShapeLibrary.js'
import { getState, setConfig, useStore } from './store.js'

const strokePaint = (seq) => {
  const p = {}
  ;(Array.isArray(seq) ? seq : [...seq]).forEach((n, i) => (p[n] = i === 0 ? 'paint-start' : 'paint-on'))
  return p
}

export function ShapePanel() {
  const { config } = useStore()
  const grid = Number(config.grid_size)
  const [stroke, setStroke] = useState([])
  const [note, setNote] = useState('')
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [libOpen, setLibOpen] = useState(false)
  const [library, setLibrary] = useState([])

  // fetch library previews once per grid / dict-file (selection is filtered client-side)
  useEffect(() => {
    api('/api/shapes/library', { method: 'POST', body: JSON.stringify({ config: getState().config }) })
      .then((d) => setLibrary(d.shapes || []))
      .catch(() => setLibrary([]))
  }, [config.grid_size, config.shape_dict_path])

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
  const allSelected = !(config.shape_names || []).length
  const selectedLib = library.filter(
    (s) => s.path && (allSelected || (config.shape_names || []).includes(s.name)),
  )
  const carousel = [
    ...drawn.map((s, i) => ({
      key: 'd' + i,
      path: Array.isArray(s) ? s : [...s],
      label: Array.isArray(s) ? s.join('') : s,
      kind: 'drawn',
    })),
    ...selectedLib.map((s) => ({ key: 'l' + s.name, path: [...s.path], label: s.name, kind: 'lib' })),
  ]

  return html`
    <${Fragment}>
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

      ${carousel.length
        ? html`
            <p class="section-label carousel-head">Selected shapes · ${carousel.length}</p>
            <div class="shape-carousel">
              ${carousel.map(
                (c) => html`
                  <div class="carousel-item ${c.kind === 'drawn' ? 'is-drawn' : ''}" key=${c.key}>
                    <${Board} gridSize=${grid} paint=${strokePaint(c.path)} interactive=${false} mini=${true} />
                    <span class="carousel-label">${c.label}</span>
                  </div>
                `,
              )}
            </div>
          `
        : null}

      <div class="cand-head">
        <p class="section-label">Step 2 · Candidates to try first</p>
        <button class="button button-ghost" onclick=${() => setLibOpen(true)}>Browse library</button>
      </div>
      <table class="cand-table">
        <tbody>
          <tr class="cand-lib-row">
            <td class="cand-shape">
              ${allSelected ? 'Built-in library — all shapes' : `Built-in library — ${(config.shape_names || []).length} selected`}
            </td>
            <td><span class="pill pill-library">library</span></td>
            <td class="cand-actions"><button class="button button-ghost" onclick=${() => setLibOpen(true)}>Edit</button></td>
          </tr>
          ${drawn.map(
            (s, i) => html`
              <tr>
                <td class="cand-shape">
                  <${Board} gridSize=${grid} paint=${strokePaint(s)} interactive=${false} mini=${true} />
                  <span class="mono">${Array.isArray(s) ? s.join('') : s}</span>
                </td>
                <td><span class="pill pill-drawn">drawn</span></td>
                <td class="cand-actions"><button class="chip-clear" onclick=${() => removeShape(i)}>×</button></td>
              </tr>
            `,
          )}
          ${!drawn.length
            ? html`<tr><td colspan="3" class="muted cand-empty">Draw a shape above and press <strong>Add shape</strong> to pin your own.</td></tr>`
            : null}
        </tbody>
      </table>

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
    ${libOpen ? html`<${ShapeLibraryModal} onClose=${() => setLibOpen(false)} />` : null}
    </${Fragment}>
  `
}
