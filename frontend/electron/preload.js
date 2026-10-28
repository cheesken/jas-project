const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('electronAPI', {
  openPdfFile: () => ipcRenderer.invoke('dialog:openPdfFile'),
  findChromeHistory: () => ipcRenderer.invoke('history:findChrome'),
  findSafariHistory: () => ipcRenderer.invoke('history:findSafari'),
  platform: process.platform,
  openFolder: () => ipcRenderer.invoke('dialog:openFolder'),
  getServices: () => ipcRenderer.invoke('services:get'),
  startServices: () => ipcRenderer.invoke('services:start'),
  pullModel: () => ipcRenderer.invoke('services:pullModel'),
  openDownload: (name) => ipcRenderer.invoke('shell:openDownload', name),
  onServicesUpdate: (callback) => {
    const listener = (_event, state) => callback(state);
    ipcRenderer.on('services:update', listener);
    return () => ipcRenderer.removeListener('services:update', listener);
  },
});
