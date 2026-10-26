const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  minimize: () => ipcRenderer.send("window:minimize"),
  close: () => ipcRenderer.send("window:close"),
  setAudioSource: (pid) => ipcRenderer.invoke("audio:set-source", pid),
  onAudioExited: (callback) => {
    const listener = () => callback();
    ipcRenderer.on("audio:exited", listener);
    return () => ipcRenderer.removeListener("audio:exited", listener);
  }
});
