# ClaudeBot desktop

A desktop window onto your own ClaudeBot's web app, for macOS, Windows and Linux. ClaudeBot keeps
running on your server (or your computer); this app only opens it. It stores just the server's
address.

## Use it

1. Make sure the web app is on (it is by default: `WEB_PORT=8765`). For a ClaudeBot on another
   machine, serve it over HTTPS and set `WEB_PUBLIC_URL` (see the main README).
2. In Telegram, send your bot **/web**.
3. Open ClaudeBot desktop and paste the link. That's it.

To switch servers or sign in again: **ClaudeBot → Sign in with a new link…** (Ctrl/Cmd+Shift+L).
**Forget this server** signs the app out and clears its storage.

## Build it

```bash
cd desktop
npm ci
npm test           # link and navigation rules
npm start          # run from source
npm run dist       # installers for this OS into dist/
```

Or run the **Desktop app** workflow on GitHub (Actions tab, or push a `desktop-v*` tag) to build
macOS, Windows and Linux installers at once. They're unsigned: macOS asks you to right-click → Open
the first time, and Windows SmartScreen shows "More info → Run anyway". To sign, add the usual
electron-builder secrets (`CSC_LINK`, `CSC_KEY_PASSWORD`, and for macOS notarization `APPLE_ID`,
`APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`) and remove `CSC_IDENTITY_AUTO_DISCOVERY` from the workflow.

## How it's locked down

- The web app runs with no Node.js access, in Chromium's sandbox, with context isolation.
- The window only shows pages of the ClaudeBot you connected. Other links open in your browser
  (web links only: no `file:` or custom schemes), and pages can't open new windows.
- No camera, microphone, location or notification permissions, ever.
- Plain `http://` is only accepted for this computer (`localhost`); anything else must be `https://`.
- Packaged builds turn off `ELECTRON_RUN_AS_NODE`, `NODE_OPTIONS` and `--inspect`, encrypt cookies,
  and only load the app from its checked bundle (Electron fuses).
