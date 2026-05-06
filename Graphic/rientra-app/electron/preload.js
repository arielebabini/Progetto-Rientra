const { contextBridge, ipcRenderer } = require('electron');

// Expose a safe API to the React renderer process.
contextBridge.exposeInMainWorld('electronAPI', {
  // Platform info (useful for OS-specific logic)
  platform: process.platform,

  // ── File dialog (used by "Add Worker" import) ─────────────────────────────
  // Opens a native file-picker and returns { canceled, filePaths }
  showOpenDialog: (options) => ipcRenderer.invoke('show-open-dialog', options),

  // Read a file from disk and return its bytes as a number[] (safe to transfer)
  readFileBuffer: (filePath) => ipcRenderer.invoke('read-file-buffer', filePath),
});
