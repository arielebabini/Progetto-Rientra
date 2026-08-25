const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const https = require('https');

const PYTHON_URL = 'https://www.nuget.org/api/v2/package/python/3.11.9';
const JRE_URL = 'https://github.com/adoptium/temurin11-binaries/releases/download/jdk-11.0.22%2B7/OpenJDK11U-jre_x64_windows_hotspot_11.0.22_7.zip';

const PYTHON_WIN_DIR = path.join(__dirname, '..', 'python-service', 'python-win');
const JRE_WIN_DIR = path.join(__dirname, '..', 'python-service', 'jre-win');
const TEMP_DIR = path.join(__dirname, '..', 'temp-runtimes');

// Helper to download a file with redirect support
function downloadFile(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    
    function get(requestUrl) {
      https.get(requestUrl, (response) => {
        if (response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
          // Follow redirect
          get(response.headers.location);
          return;
        }
        
        if (response.statusCode !== 200) {
          reject(new Error(`Failed to download: Status Code ${response.statusCode}`));
          return;
        }
        
        response.pipe(file);
        
        file.on('finish', () => {
          file.close();
          resolve();
        });
      }).on('error', (err) => {
        fs.unlink(dest, () => {});
        reject(err);
      });
    }
    
    get(url);
  });
}

// Helper to extract zip using system tar
function extractZip(zipPath, targetDir) {
  if (!fs.existsSync(targetDir)) {
    fs.mkdirSync(targetDir, { recursive: true });
  }
  console.log(`Extracting ${path.basename(zipPath)} to ${targetDir}...`);
  execSync(`tar -xf "${zipPath}" -C "${targetDir}"`, { stdio: 'inherit' });
}

async function main() {
  try {
    const needsPython = !fs.existsSync(PYTHON_WIN_DIR);
    const needsJre = !fs.existsSync(JRE_WIN_DIR);
    
    if (!needsPython && !needsJre) {
      console.log('[Runtimes Setup] Windows Python and JRE are already prepared.');
      return;
    }
    
    if (!fs.existsSync(TEMP_DIR)) {
      fs.mkdirSync(TEMP_DIR, { recursive: true });
    }
    
    if (needsPython) {
      const pythonZip = path.join(TEMP_DIR, 'python-win.zip');
      const tempExtract = path.join(TEMP_DIR, 'python-extract');
      
      console.log(`[Runtimes Setup] Downloading Windows Python 3.11.9 from NuGet...`);
      await downloadFile(PYTHON_URL, pythonZip);
      
      // Extract NuGet package
      extractZip(pythonZip, tempExtract);
      
      // NuGet places Python under the 'tools' folder
      const toolsDir = path.join(tempExtract, 'tools');
      if (fs.existsSync(toolsDir)) {
        console.log(`Moving Python tools to ${PYTHON_WIN_DIR}`);
        fs.renameSync(toolsDir, PYTHON_WIN_DIR);
      } else {
        throw new Error('NuGet package did not contain a "tools" folder.');
      }
    }
    
    if (needsJre) {
      const jreZip = path.join(TEMP_DIR, 'jre-win.zip');
      const tempExtract = path.join(TEMP_DIR, 'jre-extract');
      
      console.log(`[Runtimes Setup] Downloading Windows JRE 11 from Adoptium...`);
      await downloadFile(JRE_URL, jreZip);
      
      // Extract JRE
      extractZip(jreZip, tempExtract);
      
      // Adoptium JRE is wrapped inside a single folder, locate it
      const folders = fs.readdirSync(tempExtract).filter(f => fs.statSync(path.join(tempExtract, f)).isDirectory());
      if (folders.length > 0) {
        const jreFolder = path.join(tempExtract, folders[0]);
        console.log(`Moving JRE content to ${JRE_WIN_DIR}`);
        fs.renameSync(jreFolder, JRE_WIN_DIR);
      } else {
        throw new Error('JRE zip did not contain a root directory.');
      }
    }
    
    console.log('[Runtimes Setup] Cleanup temporary files...');
    fs.rmSync(TEMP_DIR, { recursive: true, force: true });
    console.log('[Runtimes Setup] Completed successfully.');
    
  } catch (error) {
    console.error('[Runtimes Setup] Error preparing runtimes:', error);
    process.exit(1);
  }
}

main();
