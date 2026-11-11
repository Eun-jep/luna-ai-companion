const {contextBridge, ipcRenderer} = require('electron');

contextBridge.exposeInMainWorld('desktop', {
  setInteractive: on => ipcRenderer.send('interactive', !!on),
  capture: big => ipcRenderer.invoke('capture', !!big),
  peek: () => ipcRenderer.invoke('peek'),
  title: () => ipcRenderer.invoke('title'),
  quit: () => ipcRenderer.send('quit'),
  wake: () => ipcRenderer.send('wake'),
  onStopAgent: callback => ipcRenderer.on('stop-agent', () => callback()),
  onToggleEye: callback => ipcRenderer.on('toggle-eye', () => callback()),
});
