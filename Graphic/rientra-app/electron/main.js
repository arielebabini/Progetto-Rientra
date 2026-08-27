const { app, BrowserWindow, ipcMain, dialog, Menu } = require('electron');
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

function ensureVenvAndDeps() {
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
      
      dialog.showMessageBoxSync({
        type: 'info',
        title: 'Inizializzazione Applicazione',
        message: 'Configurazione dell\'ambiente Python locale in corso.',
        detail: 'Sto creando l\'ambiente virtuale locale e installando le librerie necessarie (FastAPI, Owlready2, morph-kgc, ecc.).\n\nQuesta operazione viene eseguita solo al primo avvio e potrebbe richiedere da 1 a 3 minuti. Fai clic su OK per iniziare.',
        buttons: ['OK']
      });

      try {
        execSync(`"${getFallbackPython()}" -m venv .venv`, { cwd: serviceDir });
        console.log('[Python Setup] .venv created successfully.');
      } catch (err) {
        console.error('[Python Setup] Error during environment setup:', err);
        dialog.showErrorBox(
          'Errore di Inizializzazione',
          'Si è verificato un errore durante la configurazione dell\'ambiente virtuale Python:\n\n' + err.message
        );
        return;
      }
    }

    try {
      console.log('[Python Setup] Installing/updating dependencies...');
      execSync(`"${pipExe}" install -r requirements.txt`, { cwd: serviceDir });
      if (currentHash) {
        fs.writeFileSync(hashFile, currentHash, 'utf8');
      }
      console.log('[Python Setup] Dependencies installed successfully.');
    } catch (err) {
      console.error('[Python Setup] Error during dependencies installation:', err);
      dialog.showErrorBox(
        'Errore di Inizializzazione',
        'Si è verificato un errore durante l\'installazione delle dipendenze Python:\n\n' + err.message
      );
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
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

// ─── App lifecycle ──────────────────────────────────────────────────────────
app.whenReady().then(() => {
  Menu.setApplicationMenu(null); // Remove native menu bar

  // 1. Prepare files in production
  preparePythonService();

  // 2. Validate prerequisites
  const hasPython = checkPythonInstalled();
  const hasJava = checkJavaInstalled();

  if (!hasPython || !hasJava) {
    let msg = 'I seguenti componenti richiesti non sono stati trovati sul sistema:\n\n';
    if (!hasPython) msg += '❌ Python 3 (versione 3.11 o superiore)\n';
    if (!hasJava) msg += '❌ Java (JRE o JDK versione 17 o superiore, richiesta dal ragionatore Pellet)\n';
    msg += '\nAssicurati che siano installati e aggiunti al PATH di sistema, quindi riavvia l\'applicazione.';
    
    dialog.showErrorBox('Componenti di sistema mancanti', msg);
    app.quit();
    return;
  }

  // 3. Setup virtualenv if in production
  if (!isDev) {
    ensureVenvAndDeps();
  }

  startPythonService();
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


