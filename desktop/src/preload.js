// Runs before every page, but only hands the local setup page a way to connect: the remote web app
// gets nothing (it can't reach Node.js, IPC or the file system).
const { contextBridge, ipcRenderer } = require("electron");

if (location.protocol === "file:") {
  contextBridge.exposeInMainWorld("claudebot", {
    connect: link => ipcRenderer.invoke("claudebot:connect", String(link || "")),
  });
}
