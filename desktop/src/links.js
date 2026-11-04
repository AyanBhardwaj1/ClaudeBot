// Pure helpers (no Electron), so they can be unit-tested with plain Node.

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

/**
 * Read a ClaudeBot sign-in link ("https://bot.example.com/login#t=..."), or a bare server address.
 * Returns { origin, loginUrl } or throws an Error with a message fit to show the person.
 * Plain http is only accepted for this computer: elsewhere the session cookie would cross the network unencrypted.
 */
function parseServerLink(text) {
  let url;
  try {
    url = new URL(String(text || "").trim());
  } catch {
    throw new Error("That doesn't look like a link. Paste the whole link from /web in Telegram.");
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") throw new Error("The link must start with https://");
  if (url.protocol === "http:" && !LOCAL_HOSTS.has(url.hostname)) {
    throw new Error("Use an https:// address for a ClaudeBot on another computer (set WEB_PUBLIC_URL on the server).");
  }
  if (url.username || url.password) throw new Error("That link has a username or password in it; use the one from /web.");
  const token = new URLSearchParams(url.hash.slice(1)).get("t");
  const loginUrl = url.pathname === "/login" && token ? `${url.origin}/login#t=${encodeURIComponent(token)}` : null;
  return { origin: url.origin, loginUrl };
}

/** True if `target` is a page of the ClaudeBot at `origin` (exactly that scheme, host and port). */
function isSameOrigin(target, origin) {
  try {
    return new URL(target).origin === origin;
  } catch {
    return false;
  }
}

/** Links that may open in the person's browser: plain web pages only (no file:, javascript:, custom schemes). */
function isSafeExternal(target) {
  try {
    const url = new URL(target);
    return url.protocol === "https:" || url.protocol === "http:" || url.protocol === "mailto:";
  } catch {
    return false;
  }
}

module.exports = { parseServerLink, isSameOrigin, isSafeExternal };
