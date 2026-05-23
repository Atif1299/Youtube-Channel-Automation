const { app, BrowserWindow } = require("electron");
const { spawn } = require("child_process");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const PORT = 8765;
let pyProcess = null;

function pythonCmd() {
  const venv = path.join(ROOT, ".venv", "Scripts", "python.exe");
  const fs = require("fs");
  return fs.existsSync(venv) ? venv : "python";
}

function startServer() {
  pyProcess = spawn(pythonCmd(), ["ui/server.py"], {
    cwd: ROOT,
    shell: true,
    stdio: "inherit",
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1100,
    height: 800,
    title: "YouTube Automations",
  });
  win.loadURL(`http://127.0.0.1:${PORT}`);
}

app.whenReady().then(() => {
  startServer();
  setTimeout(createWindow, 2000);
});

app.on("window-all-closed", () => {
  if (pyProcess) pyProcess.kill();
  if (process.platform !== "darwin") app.quit();
});
