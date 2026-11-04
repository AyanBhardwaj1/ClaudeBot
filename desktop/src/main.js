// ClaudeBot desktop: a window onto the web app of your own ClaudeBot. It runs no ClaudeBot code and
// stores no data except the server address; signing in uses the same one-time link as the browser.
//
// Locked down: the remote page gets no Node.js, a sandbox and context isolation; it can only show
// pages of your ClaudeBot (anything else opens in your browser, web links only); it can't open new
// windows or ask for the camera, microphone, location or notifications.

const { app, BrowserWindow, Menu, Tray, dialog, globalShortcut, ipcMain, nativeImage, net, session, shell } = require("electron");
const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const { parseServerLink, isSameOrigin, isSafeExternal } = require("./links");

const SETUP_PAGE = pathToFileURL(path.join(__dirname, "setup.html")).href;
const isSetupPage = url => url === SETUP_PAGE || url.startsWith(`${SETUP_PAGE}?`);

const CONFIG = () => path.join(app.getPath("userData"), "config.json");
let win = null;
let origin = null;
let tray = null;
let quitting = false;
const SHORTCUT = "CommandOrControl+Shift+Space";

/** Bring the window up (from the tray, the shortcut or a second launch), optionally on a page. */
function show(view) {
  if (!win) createWindow();
  if (view && origin) showApp(`${origin}/#/${view}`);
  if (win.isMinimized()) win.restore();
  win.show();
  win.focus();
}

function buildTray() {
  try {
    tray = new Tray(nativeImage.createFromPath(path.join(__dirname, "tray.png")));
  } catch {
    tray = null;  // some Linux desktops have no tray: the app still works, closing just quits
    return;
  }
  tray.setToolTip("ClaudeBot");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open ClaudeBot", click: () => show() },
    { type: "separator" },
    { label: "Chat", click: () => show("chat") },
    { label: "Today", click: () => show("today") },
    { label: "Week", click: () => show("week") },
    { type: "separator" },
    { label: "Quit ClaudeBot", click: () => { quitting = true; app.quit(); } },
  ]));
  tray.on("click", () => show());
}

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
  // With a tray icon, closing the window keeps ClaudeBot one click (or the shortcut) away; Quit quits.
  win.on("close", event => {
    if (tray && !quitting && process.platform !== "darwin") {
      event.preventDefault();
      win.hide();
    }
  });
  win.on("closed", () => { win = null; });

  const allowed = url => (origin && isSameOrigin(url, origin)) || isSetupPage(url);
  // Leaving your ClaudeBot is simply blocked: a page can't push you to another site, nor make the app open
  // your browser on its own (that only happens from a link you click, after you say yes).
  win.webContents.on("will-navigate", (event, url) => {
    if (!allowed(url)) event.preventDefault();
  });
  win.webContents.on("will-redirect", (event, url) => {
    if (!allowed(url)) event.preventDefault();
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (isSafeExternal(url)) confirmExternal(url);
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
        ...(process.platform === "linux" ? [] : [{
          label: "Open at login", type: "checkbox", checked: app.getLoginItemSettings().openAtLogin,
          click: item => app.setLoginItemSettings({ openAtLogin: item.checked }),
        }]),
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

let asking = false;
async function confirmExternal(url) {
  if (asking) return;  // one question at a time: a page can't stack up dialogs
  asking = true;
  try {
    const { response } = await dialog.showMessageBox(win, {
      type: "question", buttons: ["Open in browser", "Cancel"], defaultId: 1, cancelId: 1,
      message: "Open this link in your browser?", detail: url.slice(0, 300),
    });
    if (response === 0) await shell.openExternal(url);
  } finally {
    asking = false;
  }
}

/** Best effort: end the session on the server too, not just forget the cookie here. */
async function signOutOnServer() {
  if (!origin) return;
  try {
    const me = await net.fetch(`${origin}/api/me`, { useSessionCookies: true });
    if (!me.ok) return;
    const { csrf } = await me.json();
    await net.fetch(`${origin}/api/logout`, { method: "POST", useSessionCookies: true,
                                              headers: { "X-CSRF-Token": csrf, "Content-Type": "application/json", Origin: origin } });
  } catch { /* offline: the cookie is still cleared below */ }
}

async function forgetServer() {
  const { response } = await dialog.showMessageBox(win, {
    type: "question", buttons: ["Forget", "Cancel"], defaultId: 1, cancelId: 1,
    message: "Forget this ClaudeBot?", detail: "This signs the desktop app out. Your ClaudeBot and its data aren't touched.",
  });
  if (response !== 0) return;
  await signOutOnServer();
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
  app.on("second-instance", () => show());
  app.on("before-quit", () => { quitting = true; });
  app.on("will-quit", () => globalShortcut.unregisterAll());
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
    buildTray();
    // Ctrl/Cmd+Shift+Space from anywhere brings up the chat (skipped quietly if another app has it).
    globalShortcut.register(SHORTCUT, () => show("chat"));
    app.on("activate", () => show());
  });
  app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
}
