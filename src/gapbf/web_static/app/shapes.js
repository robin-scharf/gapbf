import { api } from './io.js'
import { blockersBetween, validNodesForGrid } from './pattern.js'
import { state } from './state.js'

// UI-local: notes live client-side; state.config.drawn_shapes holds the sequences.
const shapeState = { current: [], drawing: false, notes: [] }

function gridSize() {
  return Number(state.config.grid_size) || 3
}

function el(id) {
  return document.querySelector(`#${id}`)
}

function buildGrid() {
  const grid = el('shapeGrid')
  if (!grid) {
    return
  }
  const n = gridSize()
  const nodes = validNodesForGrid(n)
  grid.style.gridTemplateColumns = `repeat(${n}, auto)`
  grid.innerHTML = ''
  nodes.forEach((node) => {
    const dot = document.createElement('button')
    dot.type = 'button'
    dot.className = 'shape-dot'
    dot.dataset.node = node
    dot.textContent = node
    dot.addEventListener('pointerdown', (event) => {
      event.preventDefault()
      shapeState.drawing = true
      addNode(node)
    })
    dot.addEventListener('pointerenter', () => {
      if (shapeState.drawing) {
        addNode(node)
      }
    })
    grid.appendChild(dot)
  })
}

function addNode(node) {
  const stroke = shapeState.current
  if (stroke.includes(node)) {
    return
  }
  if (stroke.length > 0) {
    const prev = stroke.at(-1)
    for (const blocker of blockersBetween(prev, node, gridSize())) {
      if (!stroke.includes(blocker)) {
        stroke.push(blocker)
      }
    }
  }
  if (!stroke.includes(node)) {
    stroke.push(node)
  }
  renderCurrent()
}

function renderCurrent() {
  const seq = el('shapeCurrentSeq')
  if (seq) {
    seq.textContent = shapeState.current.length ? shapeState.current.join('') : '-'
  }
  const on = new Set(shapeState.current)
  const start = shapeState.current[0]
  document.querySelectorAll('#shapeGrid .shape-dot').forEach((dot) => {
    dot.classList.toggle('is-on', on.has(dot.dataset.node))
    dot.classList.toggle('is-start', dot.dataset.node === start)
  })
}

function renderDrawnList() {
  const list = el('shapeDrawnList')
  if (!list) {
    return
  }
  const drawn = state.config.drawn_shapes || []
  list.innerHTML = ''
  if (!drawn.length) {
    const empty = document.createElement('li')
    empty.className = 'drawn-item'
    empty.textContent = 'No shapes added yet.'
    list.appendChild(empty)
    return
  }
  drawn.forEach((seq, index) => {
    const item = document.createElement('li')
    item.className = 'drawn-item'
    const note = shapeState.notes[index] ? ` — ${shapeState.notes[index]}` : ''
    const label = document.createElement('span')
    label.textContent = `${Array.isArray(seq) ? seq.join('') : seq}${note}`
    const remove = document.createElement('button')
    remove.type = 'button'
    remove.className = 'ghost'
    remove.textContent = '×'
    remove.addEventListener('click', () => {
      state.config.drawn_shapes = drawn.filter((_, i) => i !== index)
      shapeState.notes.splice(index, 1)
      renderDrawnList()
    })
    item.append(label, remove)
    list.appendChild(item)
  })
}

async function preview() {
  const target = el('shapePreview')
  if (target) {
    target.textContent = 'Previewing…'
  }
  try {
    const result = await api('/api/shapes/preview', {
      method: 'POST',
      body: JSON.stringify({ config: state.config }),
    })
    const hours = (result.eta_seconds / 3600).toFixed(1)
    target.innerHTML =
      `<strong>${result.count.toLocaleString()}</strong> candidates ` +
      `(${result.king_count.toLocaleString()} king-move first) · ` +
      `~${hours} h at ${state.config.attempt_delay}s/attempt<br>` +
      `<span class="sample">first: ${result.sample.slice(0, 10).join('  ')}</span>`
  } catch (error) {
    if (target) {
      target.textContent = `Preview failed: ${error.message}`
    }
  }
}

export function refreshShapePanel() {
  const searchMode = el('shapeSearchMode')
  const wildness = el('shapeWildness')
  if (searchMode) {
    searchMode.value = state.config.search_mode || 'graph'
  }
  if (wildness) {
    wildness.value = String(state.config.shape_wildness ?? 1)
    const label = el('shapeWildnessValue')
    if (label) {
      label.textContent = wildness.value
    }
  }
  buildGrid()
  renderCurrent()
  renderDrawnList()
}

export function initShapePanel() {
  const grid = el('shapeGrid')
  if (!grid) {
    return
  }
  document.addEventListener('pointerup', () => {
    shapeState.drawing = false
  })
  el('shapeSearchMode')?.addEventListener('change', (event) => {
    state.config.search_mode = event.target.value
  })
  el('shapeWildness')?.addEventListener('input', (event) => {
    state.config.shape_wildness = Number(event.target.value)
    const label = el('shapeWildnessValue')
    if (label) {
      label.textContent = event.target.value
    }
  })
  el('shapeClearButton')?.addEventListener('click', () => {
    shapeState.current = []
    renderCurrent()
  })
  el('shapeAddButton')?.addEventListener('click', () => {
    if (shapeState.current.length < 2) {
      return
    }
    state.config.drawn_shapes = [
      ...(state.config.drawn_shapes || []),
      [...shapeState.current],
    ]
    shapeState.notes.push(el('shapeNote')?.value || '')
    const noteInput = el('shapeNote')
    if (noteInput) {
      noteInput.value = ''
    }
    shapeState.current = []
    renderCurrent()
    renderDrawnList()
  })
  el('shapePreviewButton')?.addEventListener('click', () => {
    void preview()
  })
  refreshShapePanel()
}
