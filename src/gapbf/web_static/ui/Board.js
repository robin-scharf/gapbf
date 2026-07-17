// One reusable grid board — dots you click or drag across. Used by both the
// graph pattern builder and the shape drawing panel.
import { html, useRef } from './html.js'
import { validNodesForGrid } from './pattern.js'

export function Board({ gridSize, paint = {}, onNode, interactive = true, mini = false }) {
  const drawing = useRef(false)
  const nodes = validNodesForGrid(gridSize)
  const stop = () => {
    drawing.current = false
  }
  return html`
    <div
      class="board2 ${interactive ? '' : 'board2-static'} ${mini ? 'board2-mini' : ''}"
      style=${`grid-template-columns: repeat(${gridSize}, minmax(0, 1fr))`}
      onpointerup=${stop}
      onpointerleave=${stop}
    >
      ${nodes.map(
        (node) => html`
          <button
            type="button"
            class="board2-dot ${paint[node] || ''}"
            data-node=${node}
            disabled=${!interactive}
            onpointerdown=${(e) => {
              if (!interactive) return
              e.preventDefault()
              drawing.current = true
              onNode?.(node)
            }}
            onpointerenter=${() => {
              if (interactive && drawing.current) onNode?.(node)
            }}
          >
            <span>${node}</span>
          </button>
        `,
      )}
    </div>
  `
}
