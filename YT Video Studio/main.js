const { app, BrowserWindow, shell, ipcMain, Menu } = require("electron");
const path = require("path");
const fs = require("fs");
const http = require("http");
const { spawn } = require("child_process");
const { parse: parseUrl } = require("url");

require("dotenv").config({ path: path.join(__dirname, ".env") });

const API_PORT = 8765;
const API_BASE = `http://127.0.0.1:${API_PORT}`;

let mainWindow;
let pythonProcess = null;

function startPythonEngine() {
  const enginePath = path.join(__dirname, "engine.py");
  if (!fs.existsSync(enginePath)) {
    console.error("engine.py not found");
    return;
  }
  pythonProcess = spawn("python", [enginePath], {
    cwd: __dirname,
    env: { ...process.env, PYTHONUNBUFFERED: "1" },
  });
  pythonProcess.stdout.on("data", (data) => console.log(`[engine] ${data}`));
  pythonProcess.stderr.on("data", (data) => console.error(`[engine] ${data}`));
  pythonProcess.on("close", (code) => {
    console.log(`[engine] exited with code ${code}`);
    pythonProcess = null;
  });
}

function stopPythonEngine() {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
}

async function waitForEngine(retries = 30) {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(`${API_BASE}/api/check`);
      if (res.ok) return true;
    } catch {}
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

async function apiCall(method, endpoint, body = null) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, opts);
    const data = await res.json();
    if (!res.ok) return { ok: false, error: data.detail || "API error" };
    return { ok: true, ...data };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 720,
    minWidth: 800,
    minHeight: 600,
    backgroundColor: "#0e0e12",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js"),
    },
  });
  mainWindow.loadFile("index.html");
}

app.whenReady().then(async () => {
  if (process.platform !== "darwin") {
    Menu.setApplicationMenu(null);
  }
  startPythonEngine();
  const ready = await waitForEngine();
  if (!ready) {
    console.error("Failed to start Python engine");
  }
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  stopPythonEngine();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  stopPythonEngine();
});

ipcMain.handle("env:check", async () => {
  return apiCall("GET", "/api/check");
});

ipcMain.handle("niche:list", async () => {
  return apiCall("GET", "/api/niches");
});

ipcMain.handle("research:trending", async (_e, { period, source, query }) => {
  const params = new URLSearchParams();
  if (period) params.set("period", period);
  if (source) params.set("source", source);
  if (query) params.set("q", query);
  return apiCall("GET", `/api/research/trending?${params}`);
});

ipcMain.handle("script:generate", async (_e, { topic, duration, audioMode, niche, videoMode }) => {
  return apiCall("POST", "/api/script/generate", {
    topic,
    duration: duration || 12,
    audio_mode: audioMode || "coach_voice",
    niche: niche || "fitness_warmup",
    video_mode: videoMode || "stock",
  });
});

ipcMain.handle("job:create", async (_e, { script, audioMode, videoMode, niche }) => {
  return apiCall("POST", "/api/jobs", {
    script_json: JSON.stringify(script),
    audio_mode: audioMode,
    video_mode: videoMode,
    niche: niche || "fitness_warmup",
  });
});

ipcMain.handle("job:start", async (_e, { jobId }) => {
  return apiCall("POST", `/api/jobs/${jobId}/start`);
});

ipcMain.handle("job:status", async (_e, { jobId }) => {
  return apiCall("GET", `/api/jobs/${jobId}`);
});

ipcMain.handle("job:list", async () => {
  return apiCall("GET", "/api/jobs");
});

ipcMain.handle("job:cancel", async (_e, { jobId }) => {
  return apiCall("POST", `/api/jobs/${jobId}/cancel`);
});

ipcMain.handle("job:delete", async (_e, { jobId }) => {
  return apiCall("DELETE", `/api/jobs/${jobId}`);
});

ipcMain.handle("video:approve", async (_e, { jobId }) => {
  return apiCall("POST", `/api/jobs/${jobId}/approve`);
});

ipcMain.handle("video:reject", async (_e, { jobId }) => {
  return apiCall("POST", `/api/jobs/${jobId}/reject`);
});

ipcMain.handle("video:url", async (_e, { jobId }) => {
  return { ok: true, url: `${API_BASE}/api/jobs/${jobId}/video` };
});

ipcMain.handle("youtube:status", async () => {
  const r = await apiCall("GET", "/api/check");
  return { ok: true, connected: r.youtube_oauth || false };
});

ipcMain.handle("youtube:auth", async () => {
  return apiCall("POST", "/api/auth-youtube");
});

ipcMain.handle("youtube:publish", async (_e, { jobId, publishAt }) => {
  return apiCall("POST", `/api/jobs/${jobId}/publish`, { publish_at: publishAt });
});

ipcMain.handle("generate:direct", async (_e, { topic, duration, audioMode, niche, videoMode }) => {
  return apiCall("POST", "/api/generate", {
    topic,
    duration: duration || 12,
    audio_mode: audioMode || "coach_voice",
    niche: niche || "fitness_warmup",
    video_mode: videoMode || "stock",
  });
});
