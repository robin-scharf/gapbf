// Tiny reactive store. Components subscribe via useStore() and re-render on
// change — component-based reactivity without a build step.
import { useEffect, useState } from './html.js'

const DEFAULT_CONFIG = {
  grid_size: 3,
  path_min_length: 4,
  path_max_length: 9,
  path_max_node_distance: 2,
  no_diagonal_crossings: false,
  no_perpendicular_crossings: false,
  path_prefix: [],
  path_suffix: [],
  excluded_nodes: [],
  attempt_delay: 10.1,
  test_path: [],
  stdout_normal: '',
  stdout_success: '',
  stdout_error: '',
  db_path: '~/.gapbf/gapbf.db',
  adb_timeout: 30,
  total_paths: 0,
  echo_commands: true,
  config_file_path: 'config.yaml',
  search_mode: 'graph',
  shape_wildness: 1,
  shape_names: [],
  drawn_shapes: [],
}

const state = {
  config: { ...DEFAULT_CONFIG },
  meta: null,
  snapshot: null,
  logs: [],
  validationErrors: [],
  successPath: null,
  connection: 'connecting',
  runModes: { a: true, t: false, p: false },
  shapePreview: null,
}

const listeners = new Set()

function emit() {
  for (const l of listeners) l()
}

export function getState() {
  return state
}

export function set(patch) {
  Object.assign(state, typeof patch === 'function' ? patch(state) : patch)
  emit()
}

export function setConfig(patch) {
  state.config = { ...state.config, ...patch }
  emit()
}

export function useStore(selector = (s) => s) {
  const [, force] = useState(0)
  useEffect(() => {
    const l = () => force((n) => n + 1)
    listeners.add(l)
    // Reconcile once: the store may have changed between render and this
    // effect committing (e.g. async boot/SSE updates), so pull the latest.
    l()
    return () => listeners.delete(l)
  }, [])
  return selector(state)
}
