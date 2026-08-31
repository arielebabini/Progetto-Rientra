const { app, BrowserWindow, ipcMain, dialog, Menu, shell } = require('electron');
const path = require('path');
const { spawn, execSync } = require('child_process');
const fs = require('fs');

// ─── Dev vs Production ──────────────────────────────────────────────────────
const isDev = process.env.NODE_ENV === 'development';
const isWindows = process.platform === 'win32';

// On macOS, GUI apps do not inherit shell environment variables. Prepend Homebrew, keg-only OpenJDK, and standard local bins to PATH.
if (process.platform === 'darwin') {
  process.env.PATH = `/opt/homebrew/bin:/opt/homebrew/opt/openjdk/bin:/usr/local/bin:/usr/local/opt/openjdk/bin:${process.env.PATH}`;
}

// ─── Python microservice configuration ───────────────────────────────────────
const PYTHON_PORT = 8000;

function getServiceDir() {
  return isDev
    ? path.join(__dirname, '..', 'python-service')
    : path.join(app.getPath('userData'), 'python-service');
}

function getRuntimeDir() {
  return isDev
    ? path.join(__dirname, '..', 'python-service')
    : path.join(process.resourcesPath, 'python-service');
}

function getVenvPython() {
  const serviceDir = getServiceDir();
  return isWindows
    ? path.join(serviceDir, '.venv', 'Scripts', 'python.exe')
    : path.join(serviceDir, '.venv', 'bin', 'python3');
}

function getFallbackPython() {
  const runtimeDir = getRuntimeDir();
  const bundledWinPython = path.join(runtimeDir, 'python-win', 'python.exe');
  
  if (isWindows && fs.existsSync(bundledWinPython)) {
    console.log('[Python Check] Using bundled Python.');
    return bundledWinPython;
  }

  const candidates = isWindows ? ['python', 'python3'] : ['python3', 'python'];
  for (const cmd of candidates) {
    try {
      execSync(`"${cmd}" --version`, { stdio: 'ignore' });
      return cmd;
    } catch (e) {
      // continue
    }
  }
  return isWindows ? 'python' : 'python3';
}

// ─── System Prerequisites Verification ───────────────────────────────────────
function checkPythonInstalled() {
  try {
    execSync(`"${getFallbackPython()}" --version`, { stdio: 'ignore' });
    return true;
  } catch (e) {
    return false;
  }
}

function getBundledJavaExe() {
  const runtimeDir = getRuntimeDir();
  const serviceDir = getServiceDir();

  const candidates = isWindows
    ? [
        path.join(runtimeDir, 'jre', 'bin', 'java.exe'),
        path.join(runtimeDir, 'jre-win', 'bin', 'java.exe'),
        path.join(serviceDir, 'jre', 'bin', 'java.exe'),
        path.join(serviceDir, 'jre-win', 'bin', 'java.exe'),
      ]
    : [
        path.join(runtimeDir, 'jre', 'Contents', 'Home', 'bin', 'java'),
        path.join(runtimeDir, 'jre-mac', 'Contents', 'Home', 'bin', 'java'),
        path.join(serviceDir, 'jre', 'Contents', 'Home', 'bin', 'java'),
        path.join(serviceDir, 'jre-mac', 'Contents', 'Home', 'bin', 'java'),
      ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

function checkJavaInstalled() {
  const bundledJava = getBundledJavaExe();
  if (bundledJava) {
    console.log(`[Java Check] Using bundled JRE at ${bundledJava}`);
    return true;
  }

  try {
    execSync('java -version', { stdio: 'ignore' });
    return true;
  } catch (e) {
    return false;
  }
}

// ─── Production Environment Sync & Setup ─────────────────────────────────────
function preparePythonService() {
  if (isDev) return;

  const srcDir = path.join(process.resourcesPath, 'python-service');
  const serviceDir = getServiceDir();

  if (!fs.existsSync(serviceDir)) {
    fs.mkdirSync(serviceDir, { recursive: true });
  }

  // Delete legacy/old runtime directories and .venv from userData if they exist from older runs
  const legacyJre = path.join(serviceDir, 'jre');
  const legacyPython = path.join(serviceDir, 'python');
  if (fs.existsSync(legacyJre) || fs.existsSync(legacyPython)) {
    console.log('[Python Setup] Cleaning up legacy runtimes from userData...');
    try { fs.rmSync(legacyJre, { recursive: true, force: true }); } catch (e) {}
    try { fs.rmSync(legacyPython, { recursive: true, force: true }); } catch (e) {}
    // Delete .venv to force recreation with new base Python
    const legacyVenv = path.join(serviceDir, '.venv');
    try { fs.rmSync(legacyVenv, { recursive: true, force: true }); } catch (e) {}
  }

  console.log(`[Python Setup] Syncing python-service to ${serviceDir}`);
  fs.cpSync(srcDir, serviceDir, {
    recursive: true,
    filter: (src) => {
      const relative = path.relative(srcDir, src);
      if (
        relative.startsWith('.venv') ||
        relative.startsWith('__pycache__') ||
        relative.startsWith('reasoning_cache') ||
        relative.startsWith('jre') ||
        relative.startsWith('jre-mac') ||
        relative.startsWith('jre-win') ||
        relative.startsWith('python-win')
      ) {
        return false;
      }
      if (relative === 'Rientra.rdf' && fs.existsSync(path.join(serviceDir, 'Rientra.rdf'))) {
        return false;
      }
      return true;
    }
  });
}

const crypto = require('crypto');

function runCommandAsync(command, args, options, onLog) {
  return new Promise((resolve, reject) => {
    const proc = spawn(command, args, {
      ...options,
      shell: true,
      stdio: ['ignore', 'pipe', 'pipe']
    });

    let stderrData = '';
    let stdoutData = '';

    if (proc.stdout) {
      proc.stdout.on('data', (chunk) => {
        const text = chunk.toString();
        stdoutData += text;
        if (onLog) onLog(text.trim());
      });
    }

    if (proc.stderr) {
      proc.stderr.on('data', (chunk) => {
        const text = chunk.toString();
        stderrData += text;
        if (onLog) onLog(text.trim());
      });
    }

    proc.on('close', (code) => {
      if (code === 0) {
        resolve(stdoutData);
      } else {
        reject(new Error(`Comando terminato con codice ${code}: ${stderrData || stdoutData}`));
      }
    });

    proc.on('error', (err) => {
      reject(err);
    });
  });
}

async function ensureVenvAndDeps(updateStatus) {
  const serviceDir = getServiceDir();
  const venvDir = path.join(serviceDir, '.venv');
  const reqFile = path.join(serviceDir, 'requirements.txt');
  const hashFile = path.join(serviceDir, '.deps_installed_hash');

  const pipExe = isWindows
    ? path.join(venvDir, 'Scripts', 'pip.exe')
    : path.join(venvDir, 'bin', 'pip');

  let currentHash = '';
  if (fs.existsSync(reqFile)) {
    currentHash = crypto.createHash('md5').update(fs.readFileSync(reqFile)).digest('hex');
  }

  const installedHash = fs.existsSync(hashFile) ? fs.readFileSync(hashFile, 'utf8').trim() : '';
  const venvExists = fs.existsSync(venvDir) && fs.existsSync(pipExe);
  const needsInstall = !venvExists || installedHash !== currentHash;

  if (needsInstall) {
    if (!venvExists) {
      console.log('[Python Setup] .venv not found. Creating virtual environment...');
      if (updateStatus) {
        updateStatus(
          'Configurazione ambiente Python...',
          'Creazione dell\'ambiente virtuale isolato (.venv)...'
        );
      }

      const pythonCmd = getFallbackPython();
      try {
        await runCommandAsync(pythonCmd, ['-m', 'venv', '.venv'], { cwd: serviceDir });
        console.log('[Python Setup] .venv created successfully.');
      } catch (err) {
        console.error('[Python Setup] Error during environment setup:', err);
        throw new Error('Errore durante la creazione dell\'ambiente virtuale Python:\n' + err.message);
      }
    }

    if (updateStatus) {
      updateStatus(
        'Installazione librerie Python...',
        'Installazione dei moduli (FastAPI, Owlready2, morph-kgc, ecc.). Attendere 1-3 minuti...'
      );
    }

    try {
      console.log('[Python Setup] Installing/updating dependencies...');
      await runCommandAsync(pipExe, ['install', '-r', 'requirements.txt'], { cwd: serviceDir }, (log) => {
        console.log('[Pip]', log);
      });
      if (currentHash) {
        fs.writeFileSync(hashFile, currentHash, 'utf8');
      }
      console.log('[Python Setup] Dependencies installed successfully.');
    } catch (err) {
      console.error('[Python Setup] Error during dependencies installation:', err);
      throw new Error('Errore durante l\'installazione delle dipendenze Python:\n' + err.message);
    }
  }
}

// ─── Process Control ────────────────────────────────────────────────────────
let pythonProcess = null;

function startPythonService() {
  const serviceDir = getServiceDir();
  const venvPython = getVenvPython();
  const pythonExe = fs.existsSync(venvPython) ? venvPython : getFallbackPython();

  console.log(`[Python] Starting uvicorn with ${pythonExe}`);
  console.log(`[Python] Service dir: ${serviceDir}`);

  // If a bundled JRE exists, set the JAVA_EXE env variable to point to it
  const bundledJava = getBundledJavaExe();
  const env = { ...process.env };

  if (bundledJava) {
    env.JAVA_EXE = bundledJava;
    console.log(`[Python Setup] Passing JRE JAVA_EXE: ${env.JAVA_EXE}`);
  }

  pythonProcess = spawn(
    pythonExe,
    ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(PYTHON_PORT)],
    {
      cwd: serviceDir,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: env,
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

// ─── Splash & Main Windows ──────────────────────────────────────────────────
let splashWindow = null;

function createSplashWindow() {
  if (!isWindows) return;

  splashWindow = new BrowserWindow({
    width: 520,
    height: 330,
    resizable: false,
    movable: true,
    center: true,
    frame: false,
    alwaysOnTop: true,
    backgroundColor: '#0b1329',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'splash-preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  splashWindow.loadFile(path.join(__dirname, 'splash.html'));
  splashWindow.once('ready-to-show', () => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.show();
    }
  });
}

function updateSplashStatus(title, detail) {
  if (!isWindows) return;
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.webContents.send('status-update', { title, detail });
  }
}

function closeSplashWindow() {
  if (splashWindow && !splashWindow.isDestroyed()) {
    splashWindow.destroy();
    splashWindow = null;
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: 'RIENTR@ returns — Decision Support System',
    backgroundColor: '#1a2a4a',
    show: !isWindows,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    win.loadURL('http://localhost:5173');
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  return win;
}

// ─── App lifecycle ──────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  Menu.setApplicationMenu(null); // Remove native menu bar

  // 1. Create and show Splash Screen (Windows only)
  if (isWindows) {
    createSplashWindow();
  }

  try {
    // 2. Prepare files in production
    updateSplashStatus('Inizializzazione applicazione...', 'Preparazione dei file di sistema...');
    preparePythonService();

    // 3. Validate prerequisites
    updateSplashStatus('Verifica requisiti di sistema...', 'Controllo della presenza di Python e Java...');
    const hasPython = checkPythonInstalled();
    const hasJava = checkJavaInstalled();

    if (!hasPython || !hasJava) {
      closeSplashWindow();
      let msg = 'I seguenti componenti richiesti non sono stati trovati sul sistema:\n\n';
      if (!hasPython) msg += '❌ Python 3 (versione 3.11 o superiore)\n';
      if (!hasJava) msg += '❌ Java (JRE o JDK versione 17 o superiore, richiesta dal ragionatore Pellet)\n';
      msg += '\nAssicurati che siano installati e aggiunti al PATH di sistema, quindi riavvia l\'applicazione.';
      
      dialog.showErrorBox('Componenti di sistema mancanti', msg);
      app.quit();
      return;
    }

    // 4. Setup virtualenv if in production
    if (!isDev) {
      await ensureVenvAndDeps((title, detail) => {
        updateSplashStatus(title, detail);
      });
    }

    // 5. Start Python service
    updateSplashStatus('Avvio motore semantico...', 'Avvio del server di calcolo e dell\'interfaccia...');
    startPythonService();

    // 6. Create main window
    const mainWindow = createWindow();

    if (isWindows) {
      let shown = false;
      const showApp = () => {
        if (shown) return;
        shown = true;
        mainWindow.show();
        mainWindow.focus();
        setTimeout(() => {
          closeSplashWindow();
        }, 300);
      };

      mainWindow.once('ready-to-show', showApp);
      mainWindow.webContents.once('did-finish-load', () => {
        setTimeout(showApp, 500);
      });
    }

  } catch (err) {
    console.error('[App Startup Error]', err);
    closeSplashWindow();
    dialog.showErrorBox(
      'Errore di Inizializzazione',
      'Si è verificato un errore durante l\'inizializzazione dell\'applicazione:\n\n' + err.message
    );
    app.quit();
  }

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

// ─── IPC — native file-open dialog ──────────────────────────────────────────
// Used by the "Add Worker" button to let the user pick a .sql dataset file.
ipcMain.handle('show-open-dialog', async (_event, options) => {
  const focusedWin = BrowserWindow.getFocusedWindow();
  const result = await dialog.showOpenDialog(
    focusedWin || BrowserWindow.getAllWindows()[0],
    options
  );
  return result; // { canceled, filePaths }
});

// ─── IPC — read file as binary buffer ───────────────────────────────────────
// Lets the renderer read the chosen .sql file and upload it to the Python service.
ipcMain.handle('read-file-buffer', async (_event, filePath) => {
  try {
    const buf = fs.readFileSync(filePath);
    // Transfer as a plain ArrayBuffer (serialisable through contextBridge)
    return { ok: true, data: Array.from(buf) };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ─── IPC — check if ontology file exists ──────────────────────────────────
ipcMain.handle('check-ontology-exists', async () => {
  try {
    const serviceDir = getServiceDir();
    if (!fs.existsSync(serviceDir)) return false;
    const files = fs.readdirSync(serviceDir);
    const extensions = ['.rdf', '.owl', '.ttl', '.n3'];
    return files.some(file => extensions.includes(path.extname(file).toLowerCase()));
  } catch (err) {
    console.error('[IPC Check Ontology] Error:', err);
    return false;
  }
});

// ─── IPC — copy selected ontology file and restart Python service ─────────
ipcMain.handle('upload-ontology-file', async (_event, filePath) => {
  try {
    const serviceDir = getServiceDir();
    if (!fs.existsSync(serviceDir)) {
      fs.mkdirSync(serviceDir, { recursive: true });
    }
    const destPath = path.join(serviceDir, path.basename(filePath));
    fs.copyFileSync(filePath, destPath);
    console.log(`[IPC Upload Ontology] Copied ${filePath} to ${destPath}`);

    // Restart Python service
    stopPythonService();
    startPythonService();
    console.log('[IPC Upload Ontology] Python service restarted successfully');
    return { ok: true };
  } catch (err) {
    console.error('[IPC Upload Ontology] Error:', err);
    return { ok: false, error: err.message };
  }
});

// ─── IPC — export HTML to PDF via native dialog and printToPDF ──────────────
ipcMain.handle('export-pdf', async (_event, { defaultFileName, htmlContent }) => {
  let printWin = null;
  try {
    const focusedWin = BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0];
    const saveResult = await dialog.showSaveDialog(focusedWin, {
      title: 'Save Worker Technical Report (PDF)',
      defaultPath: defaultFileName || 'Worker_Technical_Report.pdf',
      filters: [{ name: 'PDF Documents (*.pdf)', extensions: ['pdf'] }],
    });

    if (saveResult.canceled || !saveResult.filePath) {
      return { canceled: true };
    }

    printWin = new BrowserWindow({
      show: false,
      width: 1024,
      height: 1400,
      webPreferences: {
        nodeIntegration: false,
        contextIsolation: true,
      },
    });

    const dataUrl = `data:text/html;charset=utf-8,${encodeURIComponent(htmlContent)}`;
    await printWin.loadURL(dataUrl);

    // Short delay to ensure styles and fonts render cleanly
    await new Promise((resolve) => setTimeout(resolve, 300));

    const pdfBuffer = await printWin.webContents.printToPDF({
      pageSize: 'A4',
      printBackground: true,
      margins: {
        top: 0.35,
        bottom: 0.35,
        left: 0.35,
        right: 0.35,
      },
    });

    fs.writeFileSync(saveResult.filePath, pdfBuffer);
    return { ok: true, filePath: saveResult.filePath };
  } catch (err) {
    console.error('[IPC Export PDF] Error:', err);
    return { ok: false, error: err.message };
  } finally {
    if (printWin && !printWin.isDestroyed()) {
      printWin.destroy();
    }
  }
});

// ─── IPC — reveal saved file in OS file explorer ────────────────────────────
ipcMain.handle('show-item-in-folder', async (_event, filePath) => {
  try {
    if (filePath && fs.existsSync(filePath)) {
      shell.showItemInFolder(filePath);
      return { ok: true };
    }
    return { ok: false, error: 'File not found' };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});



