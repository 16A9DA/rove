const { contextBridge, ipcRenderer } = require("electron");

// The renderer gets the backend token only through this one call; it never touches the filesystem.
contextBridge.exposeInMainWorld("rove", {
  getToken: () => ipcRenderer.invoke("rove:get-token"),
});
