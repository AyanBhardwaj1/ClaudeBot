// ClaudeBot desktop: a window onto the web app of your own ClaudeBot. It runs no ClaudeBot code and
// stores no data except the server address; signing in uses the same one-time link as the browser.
//
// Locked down: the remote page gets no Node.js, a sandbox and context isolation; it can only show
// pages of your ClaudeBot (anything else opens in your browser, web links only); it can't open new
// windows or ask for the camera, microphone, location or notifications.

const { app, BrowserWindow, Menu, dialog, ipcMain, session, shell } = require("electron");
const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const { parseServerLink, isSameOrigin, isSafeExternal } = require("./links");

const SETUP_PAGE = pathToFileURL(path.join(__dirname, "setup.html")).href;
const isSetupPage = url => url === SETUP_PAGE || url.startsWith(`${SETUP_PAGE}?`);

const CONFIG = () => path.join(app.getPath("userData"), "config.json");
let win = null;
let origin = null;

function loadConfig() {
  try {
    const saved = JSON.parse(fs.readFileSync(CONFIG(), "utf8"));
    return parseServerLink(saved.origin).origin;  // re-checked: a hand-edited file can't point at file:// or plain http
  } catch {
    return null;
  }
}

function saveConfig(value) {
  fs.mkdirSync(path.dirname(CONFIG()), { recursive: true });
  fs.writeFileSync(CONFIG(), JSON.stringify({ origin: value }, null, 2), { mode: 0o600 });
}

function showSetup(message) {
  win.loadFile(path.join(__dirname, "setup.html"), { query: message ? { message } : {} });
}

function showApp(url) {
  win.loadURL(url || `${origin}/#/chat`);
}

function createWindow() {
  win = new BrowserWindow({
    width: 1180, height: 820, minWidth: 380, minHeight: 520, title: "ClaudeBot", show: false,
    backgroundColor: "#f7f6f3", autoHideMenuBar: process.platform !== "darwin",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),  // exposes one function, and only to the local setup page
      contextIsolation: true, sandbox: true, nodeIntegration: false, webSecurity: true,
      spellcheck: true, devTools: !app.isPackaged,
    },
  });
  win.once("ready-to-show", () => win.show());

  const allowed = url => (origin && isSameOrigin(url, origin)) || isSetupPage(url);
  win.webContents.on("will-navigate", (event, url) => {
    if (allowed(url)) return;
    event.preventDefault();
    if (isSafeExternal(url)) shell.openExternal(url);
  });
  win.webContents.on("will-redirect", (event, url) => {
    if (!allowed(url)) event.preventDefault();
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (isSafeExternal(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("did-fail-load", (_e, code, description, url, isMainFrame) => {
    if (isMainFrame && code !== -3 && origin && isSameOrigin(url, origin)) {
      showSetup(`Couldn't reach ${origin} (${description}). Is ClaudeBot running?`);
    }
  });

  if (origin) showApp(); else showSetup();
}

function buildMenu() {
  const template = [
    ...(process.platform === "darwin" ? [{ role: "appMenu" }] : []),
    {
      label: "ClaudeBot",
      submenu: [
        { label: "Sign in with a new link…", accelerator: "CmdOrCtrl+Shift+L", click: () => showSetup() },
        { label: "Reload", accelerator: "CmdOrCtrl+R", click: () => (origin ? showApp(win.webContents.getURL()) : showSetup()) },
        { type: "separator" },
        { label: "Forget this server", click: forgetServer },
        ...(process.platform === "darwin" ? [] : [{ type: "separator" }, { role: "quit" }]),
      ],
    },
    { role: "editMenu" },
    {
      label: "View",
      submenu: [
        { label: "Chat", accelerator: "CmdOrCtrl+1", click: () => origin && showApp(`${origin}/#/chat`) },
        { label: "Today", accelerator: "CmdOrCtrl+2", click: () => origin && showApp(`${origin}/#/today`) },
        { label: "Week", accelerator: "CmdOrCtrl+3", click: () => origin && showApp(`${origin}/#/week`) },
        { type: "separator" }, { role: "resetZoom" }, { role: "zoomIn" }, { role: "zoomOut" }, { role: "togglefullscreen" },
        ...(app.isPackaged ? [] : [{ role: "toggleDevTools" }]),
      ],
    },
    { role: "windowMenu" },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

async function forgetServer() {
  const { response } = await dialog.showMessageBox(win, {
    type: "question", buttons: ["Forget", "Cancel"], defaultId: 1, cancelId: 1,
    message: "Forget this ClaudeBot?", detail: "This signs the desktop app out. Your ClaudeBot and its data aren't touched.",
  });
  if (response !== 0) return;
  await session.defaultSession.clearStorageData();
  origin = null;
  try { fs.unlinkSync(CONFIG()); } catch { /* already gone */ }
  showSetup();
}

// Only the local setup page may call this (checked by the sender's URL, not just trusted).
ipcMain.handle("claudebot:connect", async (event, link) => {
  if (!event.senderFrame || !isSetupPage(event.senderFrame.url)) throw new Error("Not allowed.");
  const parsed = parseServerLink(link);  // throws a friendly message for bad links
  if (origin && origin !== parsed.origin) await session.defaultSession.clearStorageData();  // a different server: start clean
  origin = parsed.origin;
  saveConfig(origin);
  showApp(parsed.loginUrl || `${origin}/#/chat`);
  return { origin };
});

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (win) { if (win.isMinimized()) win.restore(); win.focus(); }
  });
  app.whenReady().then(() => {
    // No camera, microphone, location, notifications or anything else, ever.
    session.defaultSession.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
    session.defaultSession.setPermissionCheckHandler(() => false);
    app.on("web-contents-created", (_e, contents) => {
      contents.on("will-attach-webview", event => event.preventDefault());
    });
    origin = loadConfig();
    buildMenu();
    createWindow();
    app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
  });
  app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
}
