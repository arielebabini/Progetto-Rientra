const { contextBridge, ipcRenderer } = require('electron');

// Expose a safe API to the React renderer process.
// Add more methods here when you need Python ↔ UI communication.
contextBridge.exposeInMainWorld('electronAPI', {
  // Future Python bridge method:
  // sendToPython: (payload) => ipcRenderer.invoke('python-request', payload),

  // Platform info (useful for future OS-specific logic)
  platform: process.platform,
});
