const { app, BrowserWindow, dialog, ipcMain, session, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const { createServiceManager } = require('./services');

const DOWNLOAD_PAGES = {
  docker: 'https://www.docker.com/products/docker-desktop/',
  ollama: 'https://ollama.com/download',
};

let mainWindow;
let quitting = false;

const services = createServiceManager((state) => {
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('services:update', state);
});

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  // Content Security Policy
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [
          "default-src 'self' http://localhost:8000 http://localhost:5173; " +
          "script-src 'self' 'unsafe-inline' 'unsafe-eval' http://localhost:5173; " +
          "style-src 'self' 'unsafe-inline'; " +
          "font-src 'self'; " +
          "connect-src 'self' http://localhost:8000 http://localhost:5173 ws://localhost:5173; " +
          "img-src 'self' data:;"
        ],
      },
    });
  });

  // In dev, load from Vite dev server; in prod, load built index.html
  const isDev = !app.isPackaged;
  if (isDev) {
    mainWindow.loadURL(`http://localhost:5173${process.env.JAS_SKIP_ONBOARDING === '1' ? '?skipOnboarding=1' : ''}`);
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }
}

// IPC handler for file picker
ipcMain.handle('dialog:openPdfFile', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: [{ name: 'Documents and Images', extensions: ['pdf', 'txt', 'png', 'jpg', 'jpeg'] }],
  });
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  return result.filePaths[0];
});

ipcMain.handle('dialog:openFolder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory', 'createDirectory'],
    defaultPath: app.getPath('home'),
  });
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  return result.filePaths[0];
});

// Chrome's history is a SQLite file with no extension, so the renderer can't pick
// it by type. Look in the default profile for the current OS instead.
function chromeHistoryPath() {
  const home = app.getPath('home');
  const candidates = {
    darwin: [path.join(home, 'Library', 'Application Support', 'Google', 'Chrome', 'Default', 'History')],
    win32: [path.join(process.env.LOCALAPPDATA || '', 'Google', 'Chrome', 'User Data', 'Default', 'History')],
    linux: [path.join(home, '.config', 'google-chrome', 'Default', 'History')],
  }[process.platform] || [];
  return candidates.find((p) => fs.existsSync(p)) || null;
}

ipcMain.handle('history:findChrome', () => chromeHistoryPath());

ipcMain.handle('services:get', () => services.get());
ipcMain.handle('services:start', () => services.start());
ipcMain.handle('services:pullModel', () => services.pullModel());
ipcMain.handle('shell:openDownload', (_event, name) => {
  if (DOWNLOAD_PAGES[name]) shell.openExternal(DOWNLOAD_PAGES[name]);
});

app.whenReady().then(() => {
  createWindow();
  services.start();
});

app.on('before-quit', (event) => {
  if (quitting) return;
  event.preventDefault();
  quitting = true;
  services.stop().finally(() => app.exit());
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
