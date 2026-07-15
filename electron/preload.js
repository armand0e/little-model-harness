// Minimal bridge: the web app themes the native title bar overlay when the
// user switches between light and dark. Nothing else crosses the boundary.
"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("lmhShell", {
  setTitleBarOverlay: (colors) => ipcRenderer.invoke("titlebar-overlay", colors),
});
