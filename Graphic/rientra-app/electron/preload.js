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

  // Check if the ontology file (Rientra.rdf) exists
  checkOntologyExists: () => ipcRenderer.invoke('check-ontology-exists'),

  // Copy the selected ontology file and restart the Python service
  uploadOntologyFile: (filePath) => ipcRenderer.invoke('upload-ontology-file', filePath),

  // Export HTML content to PDF file via native Save Dialog and printToPDF
  exportPdf: (options) => ipcRenderer.invoke('export-pdf', options),

  // Reveal saved file in macOS Finder / Windows Explorer / Linux file manager
  showItemInFolder: (filePath) => ipcRenderer.invoke('show-item-in-folder', filePath),
});

