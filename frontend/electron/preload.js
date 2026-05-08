const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('electronAPI', {
  openPdfFile: () => ipcRenderer.invoke('dialog:openPdfFile'),
});
