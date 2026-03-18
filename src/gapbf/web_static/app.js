const state = {
  tool: "prefix",
  drawing: false,
  validationErrors: [],
  snapshot: null,
  config: {
    grid_size: 3,
    path_min_length: 4,
    path_max_length: 9,
    path_max_node_distance: 1,
    path_prefix: [],
    path_suffix: [],
    excluded_nodes: [],
    attempt_delay: 10.1,
    test_path: [],
    stdout_normal: "",
    stdout_success: "",
    stdout_error: "",
    db_path: "~/.gapbf/gapbf.db",
    adb_timeout: 30,
    total_paths: 0,
    echo_commands: true,
    config_file_path: "config.yaml",
  },
  meta: null,
  logs: [],
};

const elements = {
  connectionBadge: document.querySelector("#connectionBadge"),
  runStatusBadge: document.querySelector("#runStatusBadge"),
  validationBanner: document.querySelector("#validationBanner"),
  configPath: document.querySelector("#configPath"),
  loadConfigButton: document.querySelector("#loadConfigButton"),
  gridSize: document.querySelector("#gridSize"),
  modeA: document.querySelector("#modeA"),
  modeT: document.querySelector("#modeT"),
  modeP: document.querySelector("#modeP"),
  pathMinLength: document.querySelector("#pathMinLength"),
  pathMinLengthNumber: document.querySelector("#pathMinLengthNumber"),
  pathMaxLength: document.querySelector("#pathMaxLength"),
  pathMaxLengthNumber: document.querySelector("#pathMaxLengthNumber"),
  attemptDelay: document.querySelector("#attemptDelay"),
  adbTimeout: document.querySelector("#adbTimeout"),
  pathMaxNodeDistance: document.querySelector("#pathMaxNodeDistance"),
  distanceNote: document.querySelector("#distanceNote"),
  echoCommands: document.querySelector("#echoCommands"),
  stdoutSuccess: document.querySelector("#stdoutSuccess"),
  stdoutNormal: document.querySelector("#stdoutNormal"),
  stdoutError: document.querySelector("#stdoutError"),
  dbPath: document.querySelector("#dbPath"),
  testPath: document.querySelector("#testPath"),
  totalPaths: document.querySelector("#totalPaths"),
  prefixDisplay: document.querySelector("#prefixDisplay"),
  excludedDisplay: document.querySelector("#excludedDisplay"),
  suffixDisplay: document.querySelector("#suffixDisplay"),
  patternBoard: document.querySelector("#patternBoard"),
  liveBoard: document.querySelector("#liveBoard"),
  startButton: document.querySelector("#startButton"),
  pauseButton: document.querySelector("#pauseButton"),
  resumeButton: document.querySelector("#resumeButton"),
  stopButton: document.querySelector("#stopButton"),
  progressLabel: document.querySelector("#progressLabel"),
  progressPercent: document.querySelector("#progressPercent"),
  progressBar: document.querySelector("#progressBar"),
  statusValue: document.querySelector("#statusValue"),
  currentPathValue: document.querySelector("#currentPathValue"),
  totalPathsValue: document.querySelector("#totalPathsValue"),
  deviceValue: document.querySelector("#deviceValue"),
  startedAtValue: document.querySelector("#startedAtValue"),
  feedbackValue: document.querySelector("#feedbackValue"),
  logTableBody: document.querySelector("#logTableBody"),
  clearPrefixButton: document.querySelector("#clearPrefixButton"),
  clearExcludedButton: document.querySelector("#clearExcludedButton"),
  clearSuffixButton: document.querySelector("#clearSuffixButton"),
  toolButtons: Array.from(document.querySelectorAll("[data-tool]")),
};

function gcd(a, b) {
  if (!b) {
    return a;
  }
  return gcd(b, a % b);
}

function validNodesForGrid(gridSize) {
  const sequence = ["1", "2", "3", "4", "5", "6", "7", "8", "9", ":", ";", "<", "=", ">", "?", "@", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T"];
  return sequence.slice(0, gridSize * gridSize);
}

function coordinatesForGrid(gridSize) {
  const nodes = validNodesForGrid(gridSize);
  const coords = new Map();
  nodes.forEach((node, index) => {
    coords.set(node, { x: index % gridSize, y: Math.floor(index / gridSize) });
  });
  return coords;
}

function blockersBetween(start, end, gridSize) {
  const coords = coordinatesForGrid(gridSize);
  const startPoint = coords.get(start);
  const endPoint = coords.get(end);
  if (!startPoint || !endPoint) {
    return [];
  }
  const dx = endPoint.x - startPoint.x;
  const dy = endPoint.y - startPoint.y;
  const steps = gcd(Math.abs(dx), Math.abs(dy));
  if (steps <= 1) {
    return [];
  }
  const stepX = dx / steps;
  const stepY = dy / steps;
  const blockers = [];
  for (let step = 1; step < steps; step += 1) {
    const targetX = startPoint.x + stepX * step;
    const targetY = startPoint.y + stepY * step;
    for (const [node, point] of coords.entries()) {
      if (point.x === targetX && point.y === targetY) {
        blockers.push(node);
      }
    }
  }
  return blockers;
}

function isLegalMove(start, end, visited, excluded, gridSize) {
  if (start === end || visited.includes(end) || excluded.includes(end)) {
    return false;
  }
  return blockersBetween(start, end, gridSize).every((node) => visited.includes(node));
}

function appendSequence(tool, node) {
  const gridSize = Number(state.config.grid_size);
  if (tool === "exclude") {
    if (state.config.path_prefix.includes(node) || state.config.path_suffix.includes(node)) {
      return;
    }
    if (state.config.excluded_nodes.includes(node)) {
      state.config.excluded_nodes = state.config.excluded_nodes.filter((item) => item !== node);
    } else {
      state.config.excluded_nodes = [...state.config.excluded_nodes, node];
    }
    renderAll();
    return;
  }

  const key = tool === "prefix" ? "path_prefix" : "path_suffix";
  const otherKey = tool === "prefix" ? "path_suffix" : "path_prefix";
  const sequence = [...state.config[key]];
  const otherSequence = state.config[otherKey];
  if (sequence.includes(node) || otherSequence.includes(node) || state.config.excluded_nodes.includes(node)) {
    return;
  }
  if (sequence.length > 0 && !isLegalMove(sequence.at(-1), node, sequence, state.config.excluded_nodes, gridSize)) {
    flashValidation([`Illegal ${tool} move: ${sequence.at(-1)} -> ${node}`]);
    return;
  }
  state.config[key] = [...sequence, node];
  const maxLength = Number(state.config.path_max_length);
  if (state.config[key].length > maxLength) {
    state.config[key] = state.config[key].slice(0, maxLength);
  }
  renderAll();
}

function clearSequence(tool) {
  if (tool === "prefix") {
    state.config.path_prefix = [];
  } else if (tool === "suffix") {
    state.config.path_suffix = [];
  } else {
    state.config.excluded_nodes = [];
  }
  renderAll();
}

function flashValidation(errors) {
  state.validationErrors = errors;
  renderValidation();
}

function renderValidation() {
  if (!state.validationErrors.length) {
    elements.validationBanner.classList.add("hidden");
    elements.validationBanner.textContent = "";
    return;
  }
  elements.validationBanner.classList.remove("hidden");
  elements.validationBanner.textContent = state.validationErrors.join(" | ");
}

function drawBoard(target, livePath = []) {
  const gridSize = Number(state.config.grid_size);
  const nodes = validNodesForGrid(gridSize);
  const gap = 100 / (gridSize + 1);
  const coords = new Map();
  nodes.forEach((node, index) => {
    const row = Math.floor(index / gridSize);
    const col = index % gridSize;
    coords.set(node, { x: (col + 1) * gap, y: (row + 1) * gap });
  });

  target.innerHTML = "";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "board-svg");
  svg.setAttribute("viewBox", "0 0 100 100");

  const lines = [
    { path: state.config.path_prefix, color: "var(--prefix)", width: 4, opacity: 0.9 },
    { path: state.config.path_suffix, color: "var(--suffix)", width: 4, opacity: 0.9 },
    { path: livePath, color: "var(--live)", width: 3.4, opacity: 0.95 },
  ];

  lines.forEach(({ path, color, width, opacity }) => {
    if (!Array.isArray(path) || path.length < 2) {
      return;
    }
    const polyline = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    polyline.setAttribute(
      "points",
      path
        .map((node) => coords.get(node))
        .filter(Boolean)
        .map((point) => `${point.x},${point.y}`)
        .join(" "),
    );
    polyline.setAttribute("class", "board-line");
    polyline.setAttribute("stroke", color);
    polyline.setAttribute("stroke-width", String(width));
    polyline.setAttribute("opacity", String(opacity));
    svg.append(polyline);
  });
  target.append(svg);

  const nodeLayer = document.createElement("div");
  nodeLayer.className = "node-layer";

  nodes.forEach((node) => {
    const point = coords.get(node);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "node-button";
    button.dataset.node = node;
    button.textContent = node;
    button.style.left = `${point.x}%`;
    button.style.top = `${point.y}%`;

    if (state.config.path_prefix.includes(node)) {
      button.classList.add("is-prefix");
    }
    if (state.config.path_suffix.includes(node)) {
      button.classList.add("is-suffix");
    }
    if (state.config.excluded_nodes.includes(node)) {
      button.classList.add("is-excluded");
    }
    if (livePath.includes(node)) {
      button.classList.add("is-live");
    }
    if (state.tool !== "exclude") {
      const otherSequence = state.tool === "prefix" ? state.config.path_suffix : state.config.path_prefix;
      if (otherSequence.includes(node) || state.config.excluded_nodes.includes(node)) {
        button.classList.add("is-disabled");
      }
    }

    button.addEventListener("pointerdown", () => {
      state.drawing = true;
      appendSequence(state.tool, node);
    });
    button.addEventListener("pointerenter", () => {
      if (!state.drawing) {
        return;
      }
      appendSequence(state.tool, node);
    });
    button.addEventListener("click", () => {
      if (state.tool === "exclude") {
        appendSequence("exclude", node);
      }
    });
    nodeLayer.append(button);
  });

  target.append(nodeLayer);
}

function renderSequences() {
  elements.prefixDisplay.textContent = state.config.path_prefix.join("") || "-";
  elements.excludedDisplay.textContent = state.config.excluded_nodes.join(", ") || "-";
  elements.suffixDisplay.textContent = state.config.path_suffix.join("") || "-";
}

function renderInputs() {
  elements.configPath.value = state.config.config_file_path || elements.configPath.value;
  elements.gridSize.value = String(state.config.grid_size);
  elements.pathMinLength.value = String(state.config.path_min_length);
  elements.pathMinLengthNumber.value = String(state.config.path_min_length);
  elements.pathMaxLength.value = String(state.config.path_max_length);
  elements.pathMaxLengthNumber.value = String(state.config.path_max_length);
  elements.attemptDelay.value = String(state.config.attempt_delay);
  elements.adbTimeout.value = String(state.config.adb_timeout);
  elements.pathMaxNodeDistance.value = String(state.config.path_max_node_distance);
  elements.distanceNote.textContent = state.meta?.path_max_node_distance_note || "";
  elements.echoCommands.checked = Boolean(state.config.echo_commands);
  elements.stdoutSuccess.value = state.config.stdout_success || "";
  elements.stdoutNormal.value = state.config.stdout_normal || "";
  elements.stdoutError.value = state.config.stdout_error || "";
  elements.dbPath.value = state.config.db_path || "~/.gapbf/gapbf.db";
  elements.testPath.value = Array.isArray(state.config.test_path) ? state.config.test_path.join("") : "";
  elements.totalPaths.value = String(state.config.total_paths || 0);

  const maxLength = state.meta?.max_path_length || Number(state.config.grid_size) ** 2;
  [elements.pathMinLength, elements.pathMinLengthNumber, elements.pathMaxLength, elements.pathMaxLengthNumber].forEach((input) => {
    input.max = String(maxLength);
  });
}

function renderProgress() {
  const snapshot = state.snapshot;
  if (!snapshot) {
    return;
  }
  const total = snapshot.total_paths;
  const tested = snapshot.paths_tested || 0;
  const percent = total ? (tested / total) * 100 : 0;
  elements.progressLabel.textContent = `${tested.toLocaleString()} / ${total ? total.toLocaleString() : "Unknown"}`;
  elements.progressPercent.textContent = `${percent.toFixed(2)}%`;
  elements.progressBar.style.width = `${Math.max(0, Math.min(percent, 100))}%`;
  elements.statusValue.textContent = snapshot.status || "Idle";
  elements.currentPathValue.textContent = snapshot.current_path || "-";
  elements.totalPathsValue.textContent = total ? total.toLocaleString() : snapshot.total_paths_state || "Unknown";
  elements.deviceValue.textContent = snapshot.device_id || "-";
  elements.startedAtValue.textContent = snapshot.started_at || "-";
  elements.feedbackValue.textContent = snapshot.last_feedback || "Ready";
  elements.runStatusBadge.textContent = snapshot.status || "Idle";
  elements.pauseButton.disabled = !snapshot.active || snapshot.paused;
  elements.resumeButton.disabled = !snapshot.active || !snapshot.paused;
  elements.stopButton.disabled = !snapshot.active;
  drawBoard(elements.liveBoard, (snapshot.current_path || "").split("").filter(Boolean));
}

function renderLogs() {
  const logs = state.logs.slice(0, 150);
  if (!logs.length) {
    elements.logTableBody.innerHTML = '<tr><td colspan="5" class="empty-cell">No attempts yet.</td></tr>';
    return;
  }
  elements.logTableBody.innerHTML = logs
    .map((entry) => {
      const duration = entry.duration_ms ? `${Number(entry.duration_ms).toFixed(1)} ms` : "-";
      return `
        <tr>
          <td>${entry.timestamp || "-"}</td>
          <td>${entry.attempt || "-"}</td>
          <td>${entry.result_classification || "-"}</td>
          <td>${duration}</td>
          <td>${entry.response || "-"}</td>
        </tr>`;
    })
    .join("");
}

function renderAll() {
  renderValidation();
  renderInputs();
  renderSequences();
  drawBoard(elements.patternBoard, (state.snapshot?.current_path || "").split("").filter(Boolean));
  renderProgress();
  renderLogs();
  elements.toolButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tool === state.tool);
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: [response.statusText] }));
    const detail = Array.isArray(payload.detail) ? payload.detail.join(" | ") : payload.detail;
    throw new Error(detail || response.statusText);
  }
  return response.json();
}

function collectMode() {
  return [
    elements.modeA.checked ? "a" : null,
    elements.modeT.checked ? "t" : null,
    elements.modeP.checked ? "p" : null,
  ]
    .filter(Boolean)
    .join("");
}

function syncConfigFromInputs() {
  state.config.grid_size = Number(elements.gridSize.value);
  state.config.path_min_length = Number(elements.pathMinLengthNumber.value);
  state.config.path_max_length = Number(elements.pathMaxLengthNumber.value);
  state.config.attempt_delay = Number(elements.attemptDelay.value);
  state.config.adb_timeout = Number(elements.adbTimeout.value);
  state.config.path_max_node_distance = Number(elements.pathMaxNodeDistance.value);
  state.config.echo_commands = elements.echoCommands.checked;
  state.config.stdout_success = elements.stdoutSuccess.value;
  state.config.stdout_normal = elements.stdoutNormal.value;
  state.config.stdout_error = elements.stdoutError.value;
  state.config.db_path = elements.dbPath.value;
  state.config.test_path = elements.testPath.value.trim().split("").filter(Boolean);
  state.config.total_paths = Number(elements.totalPaths.value);
  state.config.config_file_path = elements.configPath.value;
}

async function validateDraft() {
  syncConfigFromInputs();
  try {
    const payload = await api("/api/config/validate", {
      method: "POST",
      body: JSON.stringify({ config: state.config }),
    });
    state.validationErrors = [];
    state.config = payload.config;
    state.meta = payload.meta;
    renderAll();
    return true;
  } catch (error) {
    flashValidation([error.message]);
    return false;
  }
}

async function loadConfig(path) {
  try {
    const payload = await api("/api/config/load", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    state.config = payload.config;
    state.meta = payload.meta;
    state.validationErrors = [];
    renderAll();
  } catch (error) {
    flashValidation([error.message]);
  }
}

async function fetchInitialState() {
  const health = await api("/api/health");
  elements.connectionBadge.textContent = health.ok ? "API ready" : "API offline";
  const snapshot = await api("/api/state");
  state.snapshot = snapshot;
  state.logs = snapshot.log_tail || [];
  if (snapshot.default_config_path) {
    elements.configPath.value = snapshot.default_config_path;
    await loadConfig(snapshot.default_config_path);
  } else {
    state.meta = await api("/api/config/meta?grid_size=3");
  }
  renderAll();
}

function subscribeEvents() {
  const events = new EventSource("/api/events");
  events.addEventListener("snapshot", (event) => {
    state.snapshot = JSON.parse(event.data);
    state.logs = state.snapshot.log_tail || state.logs;
    renderAll();
  });
  events.addEventListener("attempt", (event) => {
    const entry = JSON.parse(event.data);
    state.logs = [entry, ...state.logs].slice(0, 250);
    renderLogs();
  });
  events.onerror = () => {
    elements.connectionBadge.textContent = "Reconnecting";
  };
  events.onopen = () => {
    elements.connectionBadge.textContent = "API ready";
  };
}

function bindInputs() {
  [3, 4, 5, 6].forEach((size) => {
    const option = document.createElement("option");
    option.value = String(size);
    option.textContent = `${size} x ${size}`;
    elements.gridSize.append(option);
  });

  document.addEventListener("pointerup", () => {
    state.drawing = false;
  });

  elements.toolButtons.forEach((button) => {
    button.addEventListener("click", () => {
      state.tool = button.dataset.tool;
      renderAll();
    });
  });

  elements.clearPrefixButton.addEventListener("click", () => clearSequence("prefix"));
  elements.clearExcludedButton.addEventListener("click", () => clearSequence("exclude"));
  elements.clearSuffixButton.addEventListener("click", () => clearSequence("suffix"));
  elements.loadConfigButton.addEventListener("click", () => loadConfig(elements.configPath.value));

  elements.pathMinLength.addEventListener("input", () => {
    elements.pathMinLengthNumber.value = elements.pathMinLength.value;
  });
  elements.pathMinLengthNumber.addEventListener("input", () => {
    elements.pathMinLength.value = elements.pathMinLengthNumber.value;
  });
  elements.pathMaxLength.addEventListener("input", () => {
    elements.pathMaxLengthNumber.value = elements.pathMaxLength.value;
  });
  elements.pathMaxLengthNumber.addEventListener("input", () => {
    elements.pathMaxLength.value = elements.pathMaxLengthNumber.value;
  });

  elements.gridSize.addEventListener("change", async () => {
    syncConfigFromInputs();
    const gridSize = Number(elements.gridSize.value);
    state.meta = await api(`/api/config/meta?grid_size=${gridSize}`);
    state.config.grid_size = gridSize;
    const maxLength = state.meta.max_path_length;
    state.config.path_max_length = Math.min(Number(state.config.path_max_length), maxLength) || maxLength;
    state.config.path_min_length = Math.min(Number(state.config.path_min_length), state.config.path_max_length);
    const validNodes = new Set(state.meta.nodes);
    ["path_prefix", "path_suffix", "excluded_nodes", "test_path"].forEach((key) => {
      state.config[key] = (state.config[key] || []).filter((node) => validNodes.has(node));
    });
    renderAll();
  });

  elements.startButton.addEventListener("click", async () => {
    if (!collectMode()) {
      flashValidation(["Select at least one mode."]);
      return;
    }
    const valid = await validateDraft();
    if (!valid) {
      return;
    }
    try {
      state.snapshot = await api("/api/run/start", {
        method: "POST",
        body: JSON.stringify({ mode: collectMode(), config: state.config }),
      });
      state.logs = state.snapshot.log_tail || [];
      renderAll();
    } catch (error) {
      flashValidation([error.message]);
    }
  });

  elements.pauseButton.addEventListener("click", async () => {
    state.snapshot = await api("/api/run/pause", { method: "POST", body: JSON.stringify({}) });
    renderAll();
  });
  elements.resumeButton.addEventListener("click", async () => {
    state.snapshot = await api("/api/run/resume", { method: "POST", body: JSON.stringify({}) });
    renderAll();
  });
  elements.stopButton.addEventListener("click", async () => {
    state.snapshot = await api("/api/run/stop", { method: "POST", body: JSON.stringify({}) });
    renderAll();
  });

  [
    elements.pathMinLengthNumber,
    elements.pathMaxLengthNumber,
    elements.attemptDelay,
    elements.adbTimeout,
    elements.pathMaxNodeDistance,
    elements.echoCommands,
    elements.stdoutSuccess,
    elements.stdoutNormal,
    elements.stdoutError,
    elements.dbPath,
    elements.testPath,
    elements.totalPaths,
  ].forEach((input) => {
    input.addEventListener("change", () => {
      state.validationErrors = [];
      syncConfigFromInputs();
      renderAll();
    });
  });
}

async function init() {
  bindInputs();
  await fetchInitialState();
  subscribeEvents();
}

init();