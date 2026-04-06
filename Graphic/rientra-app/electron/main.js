const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

// ─── Dev vs Production ──────────────────────────────────────────────────────
const isDev = process.env.NODE_ENV === 'development';

// ─── Python microservice ─────────────────────────────────────────────────────
const PYTHON_PORT = 8000;
const SERVICE_DIR = path.join(__dirname, '..', 'python-service');

// Cross-platform venv & fallback Python resolution
const isWindows = process.platform === 'win32';
const VENV_PYTHON = isWindows
  ? path.join(SERVICE_DIR, '.venv', 'Scripts', 'python.exe')
  : path.join(SERVICE_DIR, '.venv', 'bin', 'python3');
const FALLBACK_PYTHON = isWindows ? 'python' : 'python3';


let pythonProcess = null;

function startPythonService() {
  // Use the virtualenv Python if it exists, fall back to system python3
  const pythonExe = fs.existsSync(VENV_PYTHON) ? VENV_PYTHON : FALLBACK_PYTHON;

  console.log(`[Python] Starting uvicorn with ${pythonExe}`);
  console.log(`[Python] Service dir: ${SERVICE_DIR}`);

  pythonProcess = spawn(
    pythonExe,
    ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(PYTHON_PORT)],
    {
      cwd: SERVICE_DIR,
      stdio: ['ignore', 'pipe', 'pipe'],  // capture stdout/stderr
    }
  );

  pythonProcess.stdout.on('data', (data) =>
    console.log('[Python]', data.toString().trim())
  );
  pythonProcess.stderr.on('data', (data) =>
    console.error('[Python ERR]', data.toString().trim())
  );
  pythonProcess.on('close', (code) =>
    console.log(`[Python] Process exited with code ${code}`)
  );
  pythonProcess.on('error', (err) =>
    console.error('[Python] Failed to start:', err)
  );
}

function stopPythonService() {
  if (pythonProcess) {
    console.log('[Python] Stopping service...');
    pythonProcess.kill('SIGTERM');
    pythonProcess = null;
  }
}

// ─── Create the main window ─────────────────────────────────────────────────
function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: 'RIENTR@ returns — Decision Support System',
    backgroundColor: '#1a2a4a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    win.loadURL('http://localhost:5173');
    // win.webContents.openDevTools({ mode: 'detach' }); // uncomment to debug
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

// ─── App lifecycle ──────────────────────────────────────────────────────────
app.whenReady().then(() => {
  startPythonService();   // ← start Python before opening the window
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  stopPythonService();
  if (process.platform !== 'darwin') app.quit();
});

app.on('will-quit', () => {
  stopPythonService();
});

// ─── IPC — expose Python port to renderer ───────────────────────────────────
ipcMain.handle('get-python-port', () => PYTHON_PORT);

