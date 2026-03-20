import { state, elements } from './state.js'
import {
  coordinatesForGrid,
  isLegalMove,
  isSelectableNode,
  validNodesForGrid,
} from './pattern.js'

export function appendSequence(tool, node, flashValidation, renderAll) {
  const gridSize = Number(state.config.grid_size)
  if (tool === 'exclude') {
    if (
      state.config.path_prefix.includes(node) ||
      state.config.path_suffix.includes(node)
    ) {
      return
    }
    if (state.config.excluded_nodes.includes(node)) {
      state.config.excluded_nodes = state.config.excluded_nodes.filter(
        (item) => item !== node,
      )
    } else {
      state.config.excluded_nodes = [...state.config.excluded_nodes, node]
    }
    renderAll()
    return
  }

  const key = tool === 'prefix' ? 'path_prefix' : 'path_suffix'
  const otherKey = tool === 'prefix' ? 'path_suffix' : 'path_prefix'
  const sequence = [...state.config[key]]
  const otherSequence = state.config[otherKey]
  if (
    sequence.includes(node) ||
    otherSequence.includes(node) ||
    state.config.excluded_nodes.includes(node)
  ) {
    return
  }
  if (
    sequence.length > 0 &&
    !isLegalMove(
      state.config,
      sequence.at(-1),
      node,
      sequence,
      state.config.excluded_nodes,
      gridSize,
    )
  ) {
    flashValidation([`Illegal ${tool} move: ${sequence.at(-1)} -> ${node}`])
    return
  }
  state.config[key] = [...sequence, node]
  const maxLength = Number(state.config.path_max_length)
  if (state.config[key].length > maxLength) {
    state.config[key] = state.config[key].slice(0, maxLength)
  }
  renderAll()
}

export function clearSequence(tool, renderAll) {
  if (tool === 'prefix') {
    state.config.path_prefix = []
  } else if (tool === 'suffix') {
    state.config.path_suffix = []
  } else {
    state.config.excluded_nodes = []
  }
  renderAll()
}

export function selectTool(tool, renderAll) {
  state.tool = tool
  renderAll()
}

export function clearBoardSelections() {
  state.config.path_prefix = []
  state.config.path_suffix = []
  state.config.excluded_nodes = []
  state.snapshot = state.snapshot
    ? { ...state.snapshot, current_path: '' }
    : state.snapshot
}

function builderNodeLabel(node) {
  const prefixIndex = state.config.path_prefix.indexOf(node)
  if (prefixIndex !== -1) {
    return String(prefixIndex + 1)
  }

  const suffixIndex = state.config.path_suffix.indexOf(node)
  if (suffixIndex !== -1) {
    return String(state.config.path_prefix.length + suffixIndex + 1)
  }

  return ''
}

export function drawBoard(target, livePath = [], options = {}) {
  const { showConstraintOrder = false, flashValidation, renderAll } = options
  const gridSize = Number(state.config.grid_size)
  const nodes = validNodesForGrid(gridSize)
  const gap = 100 / (gridSize + 1)
  const coords = new Map()

  nodes.forEach((node, index) => {
    const row = Math.floor(index / gridSize)
    const col = index % gridSize
    coords.set(node, { x: (col + 1) * gap, y: (row + 1) * gap })
  })

  target.innerHTML = ''
  target.style.setProperty('--grid-size', String(gridSize))
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  svg.setAttribute('class', 'board-svg')
  svg.setAttribute('viewBox', '0 0 100 100')

  const lines = [
    {
      path: state.config.path_prefix,
      color: 'var(--prefix)',
      width: 4,
      opacity: 0.9,
    },
    {
      path: state.config.path_suffix,
      color: 'var(--suffix)',
      width: 4,
      opacity: 0.9,
    },
    { path: livePath, color: 'var(--live)', width: 3.4, opacity: 0.95 },
  ]

  lines.forEach(({ path, color, width, opacity }) => {
    if (!Array.isArray(path) || path.length < 2) {
      return
    }
    const polyline = document.createElementNS(
      'http://www.w3.org/2000/svg',
      'polyline',
    )
    polyline.setAttribute(
      'points',
      path
        .map((node) => coords.get(node))
        .filter(Boolean)
        .map((point) => `${point.x},${point.y}`)
        .join(' '),
    )
    polyline.setAttribute('class', 'board-line')
    polyline.setAttribute('stroke', color)
    polyline.setAttribute('stroke-width', String(width))
    polyline.setAttribute('opacity', String(opacity))
    svg.append(polyline)
  })
  target.append(svg)

  const nodeLayer = document.createElement('div')
  nodeLayer.className = 'node-layer'

  nodes.forEach((node) => {
    const point = coords.get(node) || coordinatesForGrid(gridSize).get(node)
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'node-button'
    button.dataset.node = node
    button.textContent = showConstraintOrder ? builderNodeLabel(node) : node
    button.style.left = `${point.x}%`
    button.style.top = `${point.y}%`

    if (state.config.path_prefix.includes(node)) {
      button.classList.add('is-prefix')
    }
    if (state.config.path_suffix.includes(node)) {
      button.classList.add('is-suffix')
    }
    if (state.config.excluded_nodes.includes(node)) {
      button.classList.add('is-excluded')
    }
    if (livePath.includes(node)) {
      button.classList.add('is-live')
    }
    if (!isSelectableNode(state, state.tool, node, gridSize)) {
      button.classList.add('is-disabled')
      button.disabled = true
    }

    button.addEventListener('pointerdown', () => {
      state.drawing = true
      appendSequence(state.tool, node, flashValidation, renderAll)
    })
    button.addEventListener('pointerenter', () => {
      if (!state.drawing) {
        return
      }
      appendSequence(state.tool, node, flashValidation, renderAll)
    })
    button.addEventListener('click', () => {
      if (state.tool === 'exclude') {
        appendSequence('exclude', node, flashValidation, renderAll)
      }
    })
    nodeLayer.append(button)
  })

  target.append(nodeLayer)
}

export function renderSequences() {
  elements.prefixDisplay.textContent = state.config.path_prefix.join('') || '-'
  elements.excludedDisplay.textContent =
    state.config.excluded_nodes.join(', ') || '-'
  elements.suffixDisplay.textContent = state.config.path_suffix.join('') || '-'
}
