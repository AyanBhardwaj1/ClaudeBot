const test = require("node:test");
const assert = require("node:assert");
const { parseServerLink, isSameOrigin, isSafeExternal } = require("../src/links");

test("a sign-in link gives the server and the login page", () => {
  const r = parseServerLink("  https://bot.example.com/login#t=abc_DEF-123 ");
  assert.deepStrictEqual(r, { origin: "https://bot.example.com", loginUrl: "https://bot.example.com/login#t=abc_DEF-123" });
});

test("a bare address is fine too", () => {
  assert.deepStrictEqual(parseServerLink("http://localhost:8765"), { origin: "http://localhost:8765", loginUrl: null });
});

test("plain http only for this computer", () => {
  assert.throws(() => parseServerLink("http://bot.example.com/login#t=x"), /https/);
  assert.ok(parseServerLink("http://127.0.0.1:8765/login#t=x").loginUrl);
});

test("junk and odd schemes are refused", () => {
  for (const bad of ["", "hello", "file:///etc/passwd", "javascript:alert(1)", "https://u:p@bot.example.com"]) {
    assert.throws(() => parseServerLink(bad));
  }
});

test("same origin means same scheme, host and port", () => {
  const o = "https://bot.example.com";
  assert.ok(isSameOrigin("https://bot.example.com/#/today", o));
  assert.ok(!isSameOrigin("https://bot.example.com.evil.net/", o));
  assert.ok(!isSameOrigin("http://bot.example.com/", o));
  assert.ok(!isSameOrigin("https://bot.example.com:8443/", o));
  assert.ok(!isSameOrigin("not a url", o));
});

test("only web links open outside", () => {
  assert.ok(isSafeExternal("https://example.com"));
  assert.ok(!isSafeExternal("file:///C:/Windows/system32/calc.exe"));
  assert.ok(!isSafeExternal("smb://evil/share"));
  assert.ok(!isSafeExternal("javascript:alert(1)"));
});
