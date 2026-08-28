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
  piCpuValue: document.querySelector("#piCpuValue"),
  cpuCapacity: document.querySelector("#cpuCapacity"),
  smolvlaCpuValue: document.querySelector("#smolvlaCpuValue"),
  otherCpuValue: document.querySelector("#otherCpuValue"),
  runAverageCpuValue: document.querySelector("#runAverageCpuValue"),
  runPeakCpuValue: document.querySelector("#runPeakCpuValue"),
  cpuSmolvlaBar: document.querySelector("#cpuSmolvlaBar"),
  cpuOtherBar: document.querySelector("#cpuOtherBar"),
  piMemoryValue: document.querySelector("#piMemoryValue"),
  memoryCapacity: document.querySelector("#memoryCapacity"),
  smolvlaMemoryValue: document.querySelector("#smolvlaMemoryValue"),
  otherMemoryValue: document.querySelector("#otherMemoryValue"),
  availableMemoryValue: document.querySelector("#availableMemoryValue"),
  runPeakMemoryValue: document.querySelector("#runPeakMemoryValue"),
  memorySmolvlaBar: document.querySelector("#memorySmolvlaBar"),
  memoryOtherBar: document.querySelector("#memoryOtherBar"),
  temperatureValue: document.querySelector("#temperatureValue"),
  temperaturePeak: document.querySelector("#temperaturePeak"),
  temperatureStatus: document.querySelector("#temperatureStatus"),
  temperatureCard: document.querySelector(".temperature-card"),
  modeToggle: document.querySelector("#modeToggle"),
  modeDescription: document.querySelector("#modeDescription"),
};

const buttons = Object.fromEntries(
  [...document.querySelectorAll("[data-action]")].map((button) => [button.dataset.action, button]),
);

let latestStatus = null;

function selectedMode() {
  return elements.modeToggle.checked ? "REAL_ROBOT" : "DRY_RUN";
}

function renderModeDescription() {
  elements.modeDescription.textContent = elements.modeToggle.checked
    ? "Live cameras + live /joint_states. Inference only; command output remains disabled."
    : "Live cameras + zero joint state. Inference only; command output is disabled.";
}

elements.modeToggle.addEventListener("change", renderModeDescription);
renderModeDescription();

const tabs = [...document.querySelectorAll("[data-tab]")];
const inferenceView = document.querySelector("#inferenceView");
const cameraView = document.querySelector("#cameraView");
const cameraCards = [...document.querySelectorAll("[data-camera]")];

tabs.forEach((tab) => tab.addEventListener("click", () => {
  tabs.forEach((item) => item.classList.toggle("active", item === tab));
  inferenceView.classList.toggle("active", tab.dataset.tab === "inference");
  cameraView.classList.toggle("active", tab.dataset.tab === "camera");
}));

document.querySelector("#cameraPerformance").append(
  ...[...document.querySelector(".performance-grid").children].map((card) => card.cloneNode(true)),
);

function mirrorPerformance() {
  const target = document.querySelector("#cameraPerformance");
  target.replaceChildren(
    ...[...document.querySelector("#inferenceView .performance-grid").children]
      .map((card) => card.cloneNode(true)),
  );
}

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
  elements.modeToggle.disabled = busy;
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

function percent(value) {
  return value == null ? "—" : `${Number(value).toFixed(1)}%`;
}

function gib(value) {
  return value == null ? "—" : `${Number(value).toFixed(2)} GiB`;
}

async function refreshSystem() {
  try {
    const response = await fetch("/api/system", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const piCpu = data.cpu.pi_percent;
    const smolvlaCpu = Math.min(data.cpu.smolvla_percent ?? 0, piCpu ?? 0);
    const otherCpu = Math.max((piCpu ?? 0) - smolvlaCpu, 0);
    elements.piCpuValue.textContent = percent(piCpu);
    elements.cpuCapacity.textContent = `100% · ${data.cpu.cores} cores`;
    elements.smolvlaCpuValue.textContent = percent(data.cpu.smolvla_percent);
    elements.otherCpuValue.textContent = percent(piCpu == null ? null : otherCpu);
    elements.runAverageCpuValue.textContent = percent(data.cpu.run_average_percent);
    elements.runPeakCpuValue.textContent = percent(data.cpu.run_peak_percent);
    elements.cpuSmolvlaBar.style.width = `${smolvlaCpu}%`;
    elements.cpuOtherBar.style.width = `${otherCpu}%`;

    const memory = data.memory;
    const otherMemoryPercent = Math.max(memory.used_percent - memory.smolvla_percent, 0);
    elements.memoryCapacity.textContent = gib(memory.total_gib);
    elements.piMemoryValue.textContent = gib(memory.used_gib);
    elements.smolvlaMemoryValue.textContent = gib(memory.smolvla_rss_gib);
    elements.otherMemoryValue.textContent = gib(Math.max(memory.used_gib - memory.smolvla_rss_gib, 0));
    elements.availableMemoryValue.textContent = gib(memory.available_gib);
    elements.runPeakMemoryValue.textContent = gib(memory.run_peak_used_gib);
    elements.memorySmolvlaBar.style.width = `${memory.smolvla_percent}%`;
    elements.memoryOtherBar.style.width = `${otherMemoryPercent}%`;

    const temperature = data.temperature;
    elements.temperatureValue.textContent = temperature.current_c == null ? "Unavailable" : `${temperature.current_c.toFixed(1)}°C`;
    elements.temperaturePeak.textContent = temperature.run_peak_c == null ? "—" : `${temperature.run_peak_c.toFixed(1)}°C`;
    elements.temperatureStatus.textContent = temperature.status;
    elements.temperatureCard.classList.toggle("warm", temperature.current_c >= 70 && temperature.current_c < 80);
    elements.temperatureCard.classList.toggle("hot", temperature.current_c >= 80);
    mirrorPerformance();
  } catch (error) {
    elements.temperatureStatus.textContent = "UNREACHABLE";
  }
}

async function request(action) {
  const payloads = {
    load: { model: elements.modelSelect.value },
    run: { task: elements.taskInput.value, seed: 0, mode: selectedMode() },
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

function renderCameras(data) {
  cameraCards.forEach((card) => {
    const name = card.dataset.camera;
    const camera = data.cameras[name];
    const running = camera.state === "RUNNING";
    card.querySelector(".camera-state").textContent = camera.state;
    card.querySelector(".camera-state").classList.toggle("running", running);
    card.querySelector('[data-camera-action="run"]').disabled = running;
    card.querySelector('[data-camera-action="stop"]').disabled = !running;
    const image = card.querySelector("img");
    if (running && !image.src) image.src = `/api/camera/stream/${name}?t=${Date.now()}`;
    if (!running) image.removeAttribute("src");
    card.querySelector(".camera-message").textContent = camera.error
      ? camera.error
      : running ? `Running · PID ${camera.pid}` : "Camera is stopped.";
  });
}

async function refreshCameras() {
  try {
    const response = await fetch("/api/cameras", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderCameras(await response.json());
  } catch (error) {
    cameraCards.forEach((card) => { card.querySelector(".camera-message").textContent = error.message; });
  }
}

cameraCards.forEach((card) => {
  card.querySelectorAll("[data-camera-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const name = card.dataset.camera;
      const action = button.dataset.cameraAction;
      card.querySelector(".camera-message").textContent = `Sending ${action} request…`;
      try {
        const response = await fetch(`/api/camera/${name}/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error ?? `HTTP ${response.status}`);
      } catch (error) {
        card.querySelector(".camera-message").textContent = error.message;
      }
      await refreshCameras();
    });
  });
});

Object.entries(buttons).forEach(([action, button]) => {
  button.addEventListener("click", () => request(action));
});

refreshStatus().then(refreshModels);
setInterval(refreshStatus, 2000);
refreshSystem();
setInterval(refreshSystem, 2000);
refreshCameras();
setInterval(refreshCameras, 2000);
