const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');

// ─── Dev vs Production ──────────────────────────────────────────────────────
const isDev = process.env.NODE_ENV === 'development';

// ─── Create the main window ─────────────────────────────────────────────────
function createWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 780,
    minWidth: 900,
    minHeight: 600,
    title: 'RIENTR@ returns — Decision Support System',
    // Frameless / native window options (optional, uncomment for custom chrome)
    // frame: false,
    // titleBarStyle: 'hiddenInset',
    backgroundColor: '#1a2a4a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    // Load Vite dev server
    win.loadURL('http://localhost:5173');
    win.webContents.openDevTools({ mode: 'detach' });
  } else {
    // Load the production build
    win.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

// ─── App lifecycle ──────────────────────────────────────────────────────────
app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    // macOS: re-create window when dock icon is clicked with no open windows
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  // On macOS the convention is to keep the process alive until Cmd+Q
  if (process.platform !== 'darwin') app.quit();
});

// ─── IPC – Python bridge (placeholder for future use) ───────────────────────
// When the renderer sends a 'python-request' message, you can spawn a Python
// child process here and send the result back.
//
// Example:
// const { spawn } = require('child_process');
// ipcMain.handle('python-request', async (event, payload) => {
//   return new Promise((resolve, reject) => {
//     const py = spawn('python3', ['path/to/your_script.py', JSON.stringify(payload)]);
//     let result = '';
//     py.stdout.on('data', (data) => (result += data.toString()));
//     py.stderr.on('data', (err) => console.error('Python error:', err.toString()));
//     py.on('close', () => resolve(JSON.parse(result)));
//   });
// });
