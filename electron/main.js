// Little Harness desktop shell.
//
// Architecture: the Python harness runs as a sidecar in --server-only mode
// (the same FastAPI + SSE server that has powered the web client since v1),
// and this Electron window renders that web UI. All product features live in
// the sidecar; this process only manages its lifecycle and the window.
"use strict";

const { app, BrowserWindow, shell } = require("electron");
const { spawn, spawnSync } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");

const SMOKE = process.argv.includes("--smoke");
const REPO_ROOT = path.resolve(__dirname, "..");

let sidecar = null;
let mainWindow = null;

function sidecarCommand() {
  // Packaged builds ship the PyInstaller sidecar next to the app; dev runs
  // use the repo's Python.
  const packaged = path.join(process.resourcesPath || "", "sidecar",
    process.platform === "win32" ? "LittleHarness.exe" : "LittleHarness");
  if (fs.existsSync(packaged)) {
    return { command: packaged, args: ["--server-only"], cwd: undefined };
  }
  const python = process.platform === "win32" ? "python" : "python3";
  return {
    command: python,
    args: [path.join(REPO_ROOT, "run_app.py"), "--server-only"],
    cwd: REPO_ROOT,
  };
}

function startSidecar() {
  return new Promise((resolve, reject) => {
    const { command, args, cwd } = sidecarCommand();
    sidecar = spawn(command, args, {
      cwd,
      env: { ...process.env, LMH_NO_WINDOW: "1", PYTHONUNBUFFERED: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    const deadline = setTimeout(
      () => reject(new Error("sidecar did not report a URL within 60s")),
      60_000);
    let buffer = "";
    const watch = (chunk) => {
      buffer += chunk.toString("utf8");
      const match = buffer.match(/running at (http:\/\/127\.0\.0\.1:\d+)/);
      if (match) {
        clearTimeout(deadline);
        resolve(match[1]);
      }
    };
    sidecar.stdout.on("data", watch);
    sidecar.stderr.on("data", watch);
    sidecar.on("exit", (code) => {
      clearTimeout(deadline);
      reject(new Error(`sidecar exited early with code ${code}`));
    });
  });
}

function stopSidecar() {
  if (!sidecar || sidecar.exitCode !== null) return;
  if (process.platform === "win32") {
    // Kill the whole tree: the sidecar owns browser/MCP/ConPTY children.
    spawnSync("taskkill", ["/pid", String(sidecar.pid), "/T", "/F"]);
  } else {
    sidecar.kill("SIGTERM");
  }
}

async function createWindow() {
  let url;
  try {
    url = await startSidecar();
  } catch (error) {
    console.error(`[shell] ${error.message}`);
    app.exit(1);
    return;
  }
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 980,
    minHeight: 640,
    backgroundColor: "#262624",
    autoHideMenuBar: true,
    title: "Little Harness",
    webPreferences: {
      // The renderer is the served web app; it needs no Node access.
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });
  // External links open in the system browser, never inside the shell.
  mainWindow.webContents.setWindowOpenHandler(({ url: target }) => {
    shell.openExternal(target);
    return { action: "deny" };
  });
  await mainWindow.loadURL(url);
  if (SMOKE) {
    console.log("SMOKE OK: loaded " + url);
    app.exit(0);
  }
}

app.whenReady().then(createWindow);
app.on("window-all-closed", () => app.quit());
app.on("before-quit", stopSidecar);
process.on("exit", stopSidecar);
