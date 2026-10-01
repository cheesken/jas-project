const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('electronAPI', {
  openPdfFile: () => ipcRenderer.invoke('dialog:openPdfFile'),
  findChromeHistory: () => ipcRenderer.invoke('history:findChrome'),
});
