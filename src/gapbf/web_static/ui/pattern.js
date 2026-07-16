function gcd(a, b) {
  if (!b) {
    return a
  }
  return gcd(b, a % b)
}

export function validNodesForGrid(gridSize) {
  const sequence = [
    '1',
    '2',
    '3',
    '4',
    '5',
    '6',
    '7',
    '8',
    '9',
    ':',
    ';',
    '<',
    '=',
    '>',
    '?',
    '@',
    'A',
    'B',
    'C',
    'D',
    'E',
    'F',
    'G',
    'H',
    'I',
    'J',
    'K',
    'L',
    'M',
    'N',
    'O',
    'P',
    'Q',
    'R',
    'S',
    'T',
  ]
  return sequence.slice(0, gridSize * gridSize)
}

export function coordinatesForGrid(gridSize) {
  const nodes = validNodesForGrid(gridSize)
  const coords = new Map()
  nodes.forEach((node, index) => {
    coords.set(node, { x: index % gridSize, y: Math.floor(index / gridSize) })
  })
  return coords
}

export function blockersBetween(start, end, gridSize) {
  const coords = coordinatesForGrid(gridSize)
  const startPoint = coords.get(start)
  const endPoint = coords.get(end)
  if (!startPoint || !endPoint) {
    return []
  }

  const dx = endPoint.x - startPoint.x
  const dy = endPoint.y - startPoint.y
  const steps = gcd(Math.abs(dx), Math.abs(dy))
  if (steps <= 1) {
    return []
  }
  const stepX = dx / steps
  const stepY = dy / steps
  const blockers = []
  for (let step = 1; step < steps; step += 1) {
    const targetX = startPoint.x + stepX * step
    const targetY = startPoint.y + stepY * step
    for (const [node, point] of coords.entries()) {
      if (point.x === targetX && point.y === targetY) {
        blockers.push(node)
      }
    }
  }
  return blockers
}

export function segmentCrossingTypes(
  start,
  end,
  otherStart,
  otherEnd,
  gridSize,
) {
  if (new Set([start, end, otherStart, otherEnd]).size < 4) {
    return new Set()
  }

  const coords = coordinatesForGrid(gridSize)
  const startPoint = coords.get(start)
  const endPoint = coords.get(end)
  const otherStartPoint = coords.get(otherStart)
  const otherEndPoint = coords.get(otherEnd)
  if (!startPoint || !endPoint || !otherStartPoint || !otherEndPoint) {
    return new Set()
  }

  const orientation = (pointA, pointB, pointC) =>
    (pointB.x - pointA.x) * (pointC.y - pointA.y) -
    (pointB.y - pointA.y) * (pointC.x - pointA.x)

  const firstOrientationStart = orientation(
    startPoint,
    endPoint,
    otherStartPoint,
  )
  const firstOrientationEnd = orientation(startPoint, endPoint, otherEndPoint)
  const secondOrientationStart = orientation(
    otherStartPoint,
    otherEndPoint,
    startPoint,
  )
  const secondOrientationEnd = orientation(
    otherStartPoint,
    otherEndPoint,
    endPoint,
  )

  const properlyIntersects =
    firstOrientationStart * firstOrientationEnd < 0 &&
    secondOrientationStart * secondOrientationEnd < 0
  if (!properlyIntersects) {
    return new Set()
  }

  const dx = endPoint.x - startPoint.x
  const dy = endPoint.y - startPoint.y
  const otherDx = otherEndPoint.x - otherStartPoint.x
  const otherDy = otherEndPoint.y - otherStartPoint.y
  const crossingTypes = new Set()

  if (dx !== 0 && dy !== 0 && otherDx !== 0 && otherDy !== 0) {
    crossingTypes.add('diagonal')
  }
  if (dx * otherDx + dy * otherDy === 0) {
    crossingTypes.add('perpendicular')
  }
  return crossingTypes
}

export function violatesCrossingConstraints(
  config,
  start,
  end,
  sequence,
  gridSize,
) {
  const selectedCrossingTypes = []
  if (config.no_diagonal_crossings) {
    selectedCrossingTypes.push('diagonal')
  }
  if (config.no_perpendicular_crossings) {
    selectedCrossingTypes.push('perpendicular')
  }
  if (!selectedCrossingTypes.length || sequence.length < 2) {
    return false
  }

  for (let index = 1; index < sequence.length; index += 1) {
    const crossingTypes = segmentCrossingTypes(
      start,
      end,
      sequence[index - 1],
      sequence[index],
      gridSize,
    )
    if (selectedCrossingTypes.some((type) => crossingTypes.has(type))) {
      return true
    }
  }

  return false
}

export function isWithinMaxNodeDistance(config, start, end, gridSize) {
  const coords = coordinatesForGrid(gridSize)
  const startPoint = coords.get(start)
  const endPoint = coords.get(end)
  if (!startPoint || !endPoint) {
    return false
  }

  const maxDistance = Number(config.path_max_node_distance) || 1
  return (
    Math.max(
      Math.abs(endPoint.x - startPoint.x),
      Math.abs(endPoint.y - startPoint.y),
    ) <= maxDistance
  )
}

export function isLegalMove(config, start, end, visited, excluded, gridSize) {
  if (start === end || visited.includes(end) || excluded.includes(end)) {
    return false
  }
  if (!isWithinMaxNodeDistance(config, start, end, gridSize)) {
    return false
  }
  if (violatesCrossingConstraints(config, start, end, visited, gridSize)) {
    return false
  }
  return blockersBetween(start, end, gridSize).every((node) =>
    visited.includes(node),
  )
}

export function isSelectableNode(state, tool, node, gridSize) {
  if (tool === 'exclude') {
    return (
      !state.config.path_prefix.includes(node) &&
      !state.config.path_suffix.includes(node)
    )
  }

  const key = tool === 'prefix' ? 'path_prefix' : 'path_suffix'
  const otherKey = tool === 'prefix' ? 'path_suffix' : 'path_prefix'
  const sequence = state.config[key]
  const otherSequence = state.config[otherKey]

  if (
    sequence.includes(node) ||
    otherSequence.includes(node) ||
    state.config.excluded_nodes.includes(node)
  ) {
    return false
  }

  if (sequence.length === 0) {
    return true
  }

  return isLegalMove(
    state.config,
    sequence.at(-1),
    node,
    sequence,
    state.config.excluded_nodes,
    gridSize,
  )
}
