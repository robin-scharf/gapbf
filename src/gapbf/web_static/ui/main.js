import { api, configMeta, loadConfigFile, startRuntime } from './api.js'
import { App } from './App.js'
import { html, render } from './html.js'
import { getState, set } from './store.js'

async function boot() {
  // Load config into the store BEFORE first render so components mount with the
  // real values (avoids a mount-time re-render race).
  let path = 'config.yaml'
  try {
    const state = await api('/api/state')
    if (state.default_config_path) path = state.default_config_path
  } catch {
    /* offline — keep defaults */
  }
  try {
    const loaded = await loadConfigFile(path)
    set({ config: { ...getState().config, ...loaded.config }, meta: loaded.meta })
  } catch {
    /* no config file — keep defaults */
  }
  try {
    set({ meta: await configMeta(getState().config.grid_size) })
  } catch {
    /* ignore */
  }

  render(html`<${App} />`, document.getElementById('app'))
  startRuntime()
}

void boot()
