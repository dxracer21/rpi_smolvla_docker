const elements = {
  connectionBadge: document.querySelector("#connectionBadge"),
  connectionText: document.querySelector("#connectionText"),
  backendStatus: document.querySelector("#backendStatus"),
  modelStatus: document.querySelector("#modelStatus"),
  robotStatus: document.querySelector("#robotStatus"),
  modeStatus: document.querySelector("#modeStatus"),
  sessionState: document.querySelector("#sessionState"),
  actionMessage: document.querySelector("#actionMessage"),
  lastUpdated: document.querySelector("#lastUpdated"),
  taskInput: document.querySelector("#taskInput"),
  modelSelect: document.querySelector("#modelSelect"),
  actionValues: document.querySelectorAll("#actionValues span"),
  finiteBadge: document.querySelector("#finiteBadge"),
  loadTime: document.querySelector("#loadTime"),
  inferenceTime: document.querySelector("#inferenceTime"),
  peakRss: document.querySelector("#peakRss"),
  sessionId: document.querySelector("#sessionId"),
  zenohStatus: document.querySelector("#zenohStatus"),
};

const buttons = Object.fromEntries(
  [...document.querySelectorAll("[data-action]")].map((button) => [button.dataset.action, button]),
);

let latestStatus = null;

function basename(path) {
  return path ? path.split("/").filter(Boolean).at(-1) : "UNLOADED";
}

function seconds(value) {
  return value == null ? "—" : `${Number(value).toFixed(2)}s`;
}

function renderStatus(data) {
  latestStatus = data;
  const busy = ["LOADING", "INFERENCING", "STOPPING", "RESETTING"].includes(data.state);
  const loaded = ["IDLE", "RESULT_READY", "STOPPED"].includes(data.state);
  const result = data.result;

  elements.connectionBadge.className = "connection online";
  elements.connectionText.textContent = "Backend connected";
  elements.backendStatus.textContent = data.state;
  elements.modelStatus.textContent = basename(data.model);
  elements.robotStatus.textContent = data.robot;
  elements.modeStatus.textContent = data.mode.replace("_", " ");
  elements.sessionState.textContent = data.state;
  elements.loadTime.textContent = seconds(data.load_seconds);
  elements.inferenceTime.textContent = seconds(result?.seconds);
  elements.peakRss.textContent = result ? `${result.peak_rss_gib.toFixed(3)} GiB` : "—";
  elements.sessionId.textContent = data.session_id == null ? "Not started" : `#${data.session_id}`;
  elements.zenohStatus.textContent = !data.zenoh.enabled
    ? "Disabled"
    : data.zenoh.connected
      ? "Connected"
      : "Reconnecting";
  elements.lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;

  buttons.load.disabled = busy;
  buttons.run.disabled = busy || !loaded;
  buttons.stop.disabled = !busy;
  buttons.reset.disabled = busy && !["INFERENCING", "STOPPING"].includes(data.state);
  elements.taskInput.disabled = busy;
  elements.modelSelect.disabled = busy;

  if (result?.action?.[0]) {
    result.action[0].forEach((value, index) => {
      elements.actionValues[index].textContent = Number(value).toFixed(4);
    });
    elements.finiteBadge.textContent = result.finite ? "FINITE" : "INVALID";
  } else {
    elements.actionValues.forEach((item) => { item.textContent = "—"; });
    elements.finiteBadge.textContent = "NO RESULT";
  }

  if (data.error) {
    elements.actionMessage.textContent = data.error;
  } else if (data.state === "LOADING") {
    elements.actionMessage.textContent = "Loading the model into Raspberry Pi memory…";
  } else if (data.state === "INFERENCING") {
    elements.actionMessage.textContent = "Inference is running. Stop will discard this session result.";
  } else if (data.state === "STOPPING") {
    elements.actionMessage.textContent = "Session invalidated. Waiting for the CPU calculation to finish safely…";
  } else if (data.state === "RESULT_READY") {
    elements.actionMessage.textContent = "Dry-run inference completed. No robot command was sent.";
  } else if (data.state === "IDLE") {
    elements.actionMessage.textContent = "Model loaded. Ready to run inference.";
  } else if (data.state === "STOPPED") {
    elements.actionMessage.textContent = "Session stopped. The model remains loaded and ready.";
  } else if (data.state === "UNLOADED") {
    elements.actionMessage.textContent = "Select a checkpoint and load the model.";
  }
}

async function refreshModels() {
  try {
    const response = await fetch("/api/models", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const { models } = await response.json();
    const selected = latestStatus?.model ?? elements.modelSelect.value;
    elements.modelSelect.replaceChildren();
    models.forEach((model) => {
      const option = document.createElement("option");
      option.value = model.path;
      option.textContent = model.name;
      option.selected = model.path === selected;
      elements.modelSelect.append(option);
    });
    if (models.length === 0) {
      const option = document.createElement("option");
      option.textContent = "No checkpoints found in /models";
      option.value = "";
      elements.modelSelect.append(option);
      buttons.load.disabled = true;
    }
  } catch (error) {
    elements.actionMessage.textContent = `Could not list checkpoints: ${error.message}`;
  }
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderStatus(await response.json());
  } catch (error) {
    elements.connectionBadge.className = "connection offline";
    elements.connectionText.textContent = "Backend offline";
    elements.backendStatus.textContent = "UNREACHABLE";
    elements.lastUpdated.textContent = error.message;
  }
}

async function request(action) {
  const payloads = {
    load: { model: elements.modelSelect.value },
    run: { task: elements.taskInput.value, seed: 0 },
    stop: {},
    reset: {},
  };
  elements.actionMessage.textContent = `Sending ${action} request…`;
  try {
    const response = await fetch(`/api/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payloads[action]),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error ?? `HTTP ${response.status}`);
    renderStatus({ ...data, zenoh: latestStatus?.zenoh ?? { enabled: false, connected: false } });
  } catch (error) {
    elements.actionMessage.textContent = error.message;
  } finally {
    await refreshStatus();
  }
}

Object.entries(buttons).forEach(([action, button]) => {
  button.addEventListener("click", () => request(action));
});

refreshStatus().then(refreshModels);
setInterval(refreshStatus, 2000);
