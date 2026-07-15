// Little Harness desktop shell.
//
// Architecture: the Python harness runs as a sidecar in --server-only mode
// (the same FastAPI + SSE server that has powered the web client since v1),
// and this Electron window renders that web UI. All product features live in
// the sidecar; this process only manages its lifecycle, the window, and
// desktop integration (tray, notifications identity, updates, shortcuts).
"use strict";

const { app, BrowserWindow, Menu, Tray, globalShortcut, ipcMain,
        shell } = require("electron");
const { spawn, spawnSync } = require("node:child_process");
const path = require("node:path");
const fs = require("node:fs");

const SMOKE = process.argv.includes("--smoke");
const REPO_ROOT = path.resolve(__dirname, "..");

let sidecar = null;
let mainWindow = null;
let tray = null;
let quitting = false;

// Windows toast notifications need a stable app identity.
app.setAppUserModelId("dev.littleharness.app");

// Second launches focus the existing window instead of tripping over the
// sidecar's instance lock.
if (!SMOKE && !app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => showWindow());
}

function iconPath() {
  const packaged = path.join(process.resourcesPath || "", "icon.ico");
  if (fs.existsSync(packaged)) return packaged;
  return path.join(REPO_ROOT, "packaging", "littleharness.ico");
}

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

function showWindow() {
  if (!mainWindow) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

function toggleWindow() {
  if (!mainWindow) return;
  if (mainWindow.isVisible() && mainWindow.isFocused()) mainWindow.hide();
  else showWindow();
}

function setupTray() {
  tray = new Tray(iconPath());
  tray.setToolTip("Little Harness");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open Little Harness", click: showWindow },
    { label: "Quit", click: () => { quitting = true; app.quit(); } },
  ]));
  tray.on("click", showWindow);
}

function setupContextMenu(win) {
  win.webContents.on("context-menu", (_event, params) => {
    const items = [];
    for (const suggestion of params.dictionarySuggestions.slice(0, 5)) {
      items.push({
        label: suggestion,
        click: () => win.webContents.replaceMisspelling(suggestion),
      });
    }
    if (params.misspelledWord) {
      items.push({
        label: "Add to dictionary",
        click: () => win.webContents.session.addWordToSpellCheckerDictionary(
          params.misspelledWord),
      }, { type: "separator" });
    }
    const flags = params.editFlags;
    if (params.isEditable) {
      items.push(
        { role: "cut", enabled: flags.canCut },
        { role: "copy", enabled: flags.canCopy },
        { role: "paste", enabled: flags.canPaste },
        { type: "separator" },
        { role: "selectAll" });
    } else if (params.selectionText.trim()) {
      items.push({ role: "copy" });
    } else if (params.linkURL) {
      items.push({ label: "Copy link",
        click: () => require("electron").clipboard
          .writeText(params.linkURL) });
    } else {
      return;
    }
    Menu.buildFromTemplate(items).popup({ window: win });
  });
}

function setupAutoUpdate() {
  if (!app.isPackaged) return;
  try {
    const { autoUpdater } = require("electron-updater");
    autoUpdater.autoDownload = true;
    autoUpdater.autoInstallOnAppQuit = true;
    // Notifies via a native toast when an update has downloaded; it
    // installs on quit. Offline or missing releases are silently fine.
    autoUpdater.checkForUpdatesAndNotify().catch(() => {});
  } catch (error) {
    console.error(`[shell] auto-update unavailable: ${error.message}`);
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
    icon: iconPath(),
    // The web app draws its own themed window bar; the native caption
    // buttons render as a themed overlay on top of it.
    titleBarStyle: "hidden",
    titleBarOverlay: { color: "#2b2a27", symbolColor: "#a3a094", height: 36 },
    webPreferences: {
      // The renderer is the served web app; it needs no Node access
      // beyond the tiny titlebar-theming bridge in preload.js.
      preload: path.join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      spellcheck: true,
    },
  });
  ipcMain.handle("titlebar-overlay", (_event, colors) => {
    if (!mainWindow || typeof colors !== "object" || colors === null) return;
    const hex = (value) => typeof value === "string"
      && /^#[0-9a-fA-F]{6}$/.test(value);
    if (hex(colors.color) && hex(colors.symbolColor)
        && typeof mainWindow.setTitleBarOverlay === "function") {
      mainWindow.setTitleBarOverlay({
        color: colors.color, symbolColor: colors.symbolColor, height: 36 });
    }
  });
  // External links open in the system browser, never inside the shell.
  mainWindow.webContents.setWindowOpenHandler(({ url: target }) => {
    shell.openExternal(target);
    return { action: "deny" };
  });
  setupContextMenu(mainWindow);
  // Closing hides to the tray; the sidecar (and any running agent task)
  // keeps going. Quit comes from the tray menu.
  mainWindow.on("close", (event) => {
    if (!quitting && !SMOKE) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
  await mainWindow.loadURL(url + "/?desktop=1&shell=electron");
  if (SMOKE) {
    console.log("SMOKE OK: loaded " + url);
    app.exit(0);
  }
}

app.whenReady().then(async () => {
  await createWindow();
  if (SMOKE) return;
  setupTray();
  try {
    globalShortcut.register("Control+Alt+Space", toggleWindow);
  } catch { /* another app owns the shortcut; not fatal */ }
  setupAutoUpdate();
});
app.on("window-all-closed", () => app.quit());
app.on("before-quit", () => { quitting = true; stopSidecar(); });
app.on("will-quit", () => globalShortcut.unregisterAll());
process.on("exit", stopSidecar);
