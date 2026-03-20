import { tooltipState } from './state.js'

function ensureTooltipOverlay() {
  if (tooltipState.overlay) {
    return tooltipState.overlay
  }

  const overlay = document.createElement('div')
  overlay.className = 'floating-tooltip hidden'
  overlay.setAttribute('role', 'tooltip')

  const content = document.createElement('div')
  content.className = 'floating-tooltip-content'

  const arrow = document.createElement('div')
  arrow.className = 'floating-tooltip-arrow'

  overlay.append(content, arrow)
  document.body.append(overlay)

  tooltipState.overlay = overlay
  tooltipState.content = content
  tooltipState.arrow = arrow
  return overlay
}

export function hideTooltipOverlay() {
  if (!tooltipState.overlay) {
    return
  }
  tooltipState.activeTrigger = null
  tooltipState.overlay.classList.add('hidden')
}

function positionTooltipOverlay(trigger) {
  const overlay = ensureTooltipOverlay()
  const triggerRect = trigger.getBoundingClientRect()

  overlay.classList.remove('hidden')
  const overlayRect = overlay.getBoundingClientRect()
  const margin = 12
  const arrowSize = 12
  const idealLeft =
    triggerRect.left + triggerRect.width / 2 - overlayRect.width / 2
  const left = Math.min(
    Math.max(margin, idealLeft),
    window.innerWidth - overlayRect.width - margin,
  )
  const top = Math.max(margin, triggerRect.top - overlayRect.height - arrowSize)
  const arrowLeft = Math.min(
    Math.max(
      14,
      triggerRect.left + triggerRect.width / 2 - left - arrowSize / 2,
    ),
    overlayRect.width - 26,
  )

  overlay.style.left = `${left}px`
  overlay.style.top = `${top}px`
  tooltipState.arrow.style.left = `${arrowLeft}px`
}

function showTooltipOverlay(trigger) {
  const bubble = trigger.querySelector('.info-tooltip-bubble')
  if (!bubble) {
    return
  }

  ensureTooltipOverlay()
  tooltipState.activeTrigger = trigger
  tooltipState.content.textContent = bubble.textContent.trim()
  positionTooltipOverlay(trigger)
}

export function bindTooltips() {
  const triggers = Array.from(document.querySelectorAll('.info-tooltip'))
  triggers.forEach((trigger) => {
    trigger.addEventListener('pointerenter', () => showTooltipOverlay(trigger))
    trigger.addEventListener('pointerleave', hideTooltipOverlay)
    trigger.addEventListener('focusin', () => showTooltipOverlay(trigger))
    trigger.addEventListener('focusout', hideTooltipOverlay)
  })

  window.addEventListener('scroll', () => {
    if (tooltipState.activeTrigger) {
      positionTooltipOverlay(tooltipState.activeTrigger)
    }
  })

  window.addEventListener('resize', () => {
    if (tooltipState.activeTrigger) {
      positionTooltipOverlay(tooltipState.activeTrigger)
    }
  })
}
