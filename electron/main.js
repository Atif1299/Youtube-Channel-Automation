const { app, BrowserWindow, dialog } = require("electron");
const { spawn, execSync } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");

const ROOT = path.join(__dirname, "..");
const PORT = 8765;
const HEALTH_URL = `http://127.0.0.1:${PORT}/api/check`;
let pyProcess = null;

function pythonCmd() {
  const venv = path.join(ROOT, ".venv", "Scripts", "python.exe");
  return fs.existsSync(venv) ? venv : "python";
}

function enrichedEnv() {
  const env = { ...process.env };
  const extra = [
    path.join(process.env.LOCALAPPDATA || "", "Microsoft", "WinGet", "Links"),
  ];
  const sep = process.platform === "win32" ? ";" : ":";
  env.PATH = [...extra, env.PATH || ""].filter(Boolean).join(sep);
  return env;
}

function freePort(port) {
  if (process.platform !== "win32") return;
  try {
    const out = execSync(`netstat -ano | findstr :${port}`, { encoding: "utf8" });
    const pids = new Set();
    for (const line of out.split("\n")) {
      if (!line.includes("LISTENING")) continue;
      const pid = line.trim().split(/\s+/).pop();
      if (pid && pid !== "0") pids.add(pid);
    }
    for (const pid of pids) {
      try {
        execSync(`taskkill /PID ${pid} /F`, { stdio: "ignore" });
      } catch {
        /* ignore */
      }
    }
  } catch {
    /* port not in use */
  }
}

function startServer() {
  return new Promise((resolve, reject) => {
    pyProcess = spawn(pythonCmd(), ["backend/server.py"], {
      cwd: ROOT,
      shell: false,
      stdio: "pipe",
      env: enrichedEnv(),
    });
    pyProcess.on("error", reject);
    pyProcess.stderr.on("data", (d) => process.stderr.write(d));
    pyProcess.stdout.on("data", (d) => process.stdout.write(d));
    resolve();
  });
}

function waitForHealth(maxMs = 30000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      http
        .get(HEALTH_URL, (res) => {
          let body = "";
          res.on("data", (c) => (body += c));
          res.on("end", () => {
            if (res.statusCode !== 200) {
              retry();
              return;
            }
            try {
              resolve(JSON.parse(body));
            } catch {
              retry();
            }
          });
        })
        .on("error", retry);
    };
    const retry = () => {
      if (Date.now() - start > maxMs) {
        reject(new Error("Backend did not start in time"));
        return;
      }
      setTimeout(tick, 500);
    };
    tick();
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1100,
    height: 800,
    title: "YouTube Automations",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
}

function isReady(check) {
  if (typeof check.ready === "boolean") return check.ready;
  return Boolean(check.openai && check.pexels && check.ffmpeg);
}

function missingDetail(check) {
  return [
    !check.openai && "• Set OPENAI_API_KEY in .env",
    !check.pexels && "• Set PEXELS_API_KEY in .env",
    !check.ffmpeg && `• Install FFmpeg: ${check.ffmpeg_msg || "not on PATH"}`,
  ]
    .filter(Boolean)
    .join("\n");
}

app.whenReady().then(async () => {
  try {
    freePort(PORT);
    await startServer();
    const check = await waitForHealth();
    if (!isReady(check)) {
      await dialog.showMessageBox({
        type: "warning",
        title: "Setup required",
        message: "Some dependencies are missing.",
        detail:
          missingDetail(check) ||
          "Close any old server on port 8765 and restart the app.",
      });
    }
    createWindow();
  } catch (err) {
    dialog.showErrorBox("Startup failed", String(err.message || err));
    app.quit();
  }
});

app.on("window-all-closed", () => {
  if (pyProcess) pyProcess.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (pyProcess) pyProcess.kill();
});
