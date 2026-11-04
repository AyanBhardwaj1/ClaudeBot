// ClaudeBot web app. No framework and no build step. Every string from the server is put on the
// page as text (textContent), never as HTML: email subjects, contact names and replies can't inject markup.

const state = { me: null, csrf: null, chatBusy: false, timer: null };
const app = document.getElementById("app");

// --- tiny DOM helper -------------------------------------------------------------------------

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "class") el.className = value;
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

function toast(text) {
  const el = h("div", { class: "toast", role: "status" }, text);
  document.body.append(el);
  setTimeout(() => el.remove(), 3200);
}

// --- API --------------------------------------------------------------------------------------

class SignedOut extends Error {}

async function api(method, path, body) {
  const headers = { "Accept": "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET" && state.csrf) headers["X-CSRF-Token"] = state.csrf;
  const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body),
                                  credentials: "same-origin", cache: "no-store" });
  if (res.status === 401) throw new SignedOut();
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Something went wrong (${res.status}).`);
  return data;
}

async function act(promise, done) {
  try {
    const result = await promise;
    if (done) toast(typeof done === "function" ? done(result) : done);
    return result;
  } catch (err) {
    if (err instanceof SignedOut) return showSignedOut();
    toast(err.message);
    return null;
  }
}

// --- sign in ----------------------------------------------------------------------------------

async function signInFromLink() {
  const token = new URLSearchParams(location.hash.slice(1)).get("t");
  history.replaceState(null, "", "/");  // the token leaves the address bar (and history) right away
  if (!token) return false;
  app.replaceChildren(h("div", { class: "boot" }, h("div", { class: "spinner" }), "Signing you in…"));
  const res = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" },
                                          body: JSON.stringify({ token }), credentials: "same-origin" });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    showSignedOut(data.error);
    return null;
  }
  return true;
}

function showSignedOut(message) {
  state.me = null;
  app.replaceChildren(h("div", { class: "center" }, h("div", { class: "login" }, h("div", { class: "card" },
    h("h1", {}, "Sign in to ClaudeBot"),
    message ? h("p", { class: "msg error" }, message) : null,
    h("ol", {},
      h("li", {}, "Open your ClaudeBot chat in Telegram."),
      h("li", {}, "Send ", h("b", {}, "/web"), "."),
      h("li", {}, "Open the link it sends (it works once, for 10 minutes).")),
    h("p", { class: "sub" }, "Only you can sign in: the link comes from your own bot.")))));
}

// --- layout -----------------------------------------------------------------------------------

const PAGES = [
  ["chat", "💬", "Chat"], ["today", "📆", "Today"], ["week", "🗓", "Week"], ["lists", "🗒", "Lists"],
  ["reminders", "⏰", "Reminders"], ["bills", "🧾", "Bills"], ["birthdays", "🎂", "Birthdays"],
  ["dms", "✉️", "Telegram DMs"], ["memory", "🧠", "Memory"], ["activity", "📜", "Activity"], ["settings", "⚙️", "Settings"],
];
const TABS = ["chat", "today", "week", "lists", "more"];

function route() {
  const name = location.hash.replace(/^#\/?/, "") || "chat";
  return [...PAGES.map(p => p[0]), "more", "search"].includes(name) ? name : "chat";
}

function navLink(name, icon, label, current) {
  return h("a", { href: `#/${name}`, "aria-current": name === current ? "page" : null },
           h("span", { class: "ico", "aria-hidden": "true" }, icon), h("span", {}, label));
}

function layout(current, content) {
  clearInterval(state.timer);  // a page's polling stops when you leave it
  state.timer = null;
  const side = h("nav", { class: "side", "aria-label": "Main" },
    h("div", { class: "brand" }, h("img", { src: "/static/icon.svg", alt: "" }), "ClaudeBot"),
    h("form", { class: "search", role: "search", onsubmit: e => { e.preventDefault(); openSearch(e.target.q.value); } },
      h("input", { class: "field", name: "q", id: "search", type: "search", placeholder: "Search  (Ctrl K)", "aria-label": "Search",
                   value: state.query || "" })),
    h("div", { class: "nav" }, PAGES.map(([n, i, l]) => navLink(n, i, l, current))),
    h("div", { class: "foot" }, `Signed in as ${state.me.name}. `,
      h("button", { type: "button", onclick: signOut }, "Sign out")));
  const more = ["more", "⋯", "More"];
  const tabs = h("nav", { class: "tabs", "aria-label": "Main" },
    TABS.map(n => n === "more" ? navLink(...more, PAGES.slice(4).some(p => p[0] === current) || current === "more" ? "more" : current)
                               : navLink(n, ...PAGES.find(p => p[0] === n).slice(1), current)));
  app.replaceChildren(side, h("main", { class: "main", id: "main" }, content), tabs);
}

async function signOut() {
  await act(api("POST", "/api/logout"));
  showSignedOut("Signed out.");
}

function page(title, subtitle, ...body) {
  return h("div", { class: "page" }, h("h1", {}, title), subtitle ? h("p", { class: "sub" }, subtitle) : null, ...body);
}

function card(title, ...body) {
  return h("section", { class: "card" }, title ? h("h2", {}, title) : null, ...body);
}

function rows(items, render, emptyText) {
  return items.length ? h("ul", { class: "rows" }, items.map(render)) : h("p", { class: "empty" }, emptyText);
}

// Times are shown in your ClaudeBot's time zone (the one reminders and your calendar use), whatever
// time zone this browser or computer is in.
const tz = () => state.me?.timezone;

function fmtDate(iso, opts = { weekday: "short", month: "short", day: "numeric" }) {
  if (iso.length === 10) return new Date(iso + "T12:00:00Z").toLocaleDateString(undefined, { ...opts, timeZone: "UTC" });
  return new Date(iso).toLocaleDateString(undefined, { ...opts, timeZone: tz() });
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", timeZone: tz() });
}

function botLocalInput(date) {  // "YYYY-MM-DDTHH:MM" in the bot's time zone, for datetime-local inputs
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: tz(), hourCycle: "h23", year: "numeric",
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).formatToParts(date).map(x => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

function money(amount, currency) {
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amount); }
  catch { return `${amount.toFixed(2)} ${currency}`; }
}

// --- chat -------------------------------------------------------------------------------------

const STARTERS = ["What's on my calendar today?", "Anything important in my inbox?", "Remind me to call Mom at 6pm",
                  "Plan my afternoon"];

async function chatPage() {
  const log = h("div", { class: "log-inner" });
  const scroller = h("div", { class: "log" }, log);
  const input = h("textarea", { rows: 1, placeholder: "Message ClaudeBot", "aria-label": "Message", maxlength: 8000 });
  const send = h("button", { class: "btn primary", type: "submit" }, "Send");
  let file = null;
  const chip = h("div", { class: "chip", hidden: true });
  const picker = h("input", { type: "file", hidden: true, "aria-hidden": "true",
    accept: "image/*,.pdf,.txt,.md,.csv,.json,.docx,.xlsx,.pptx", onchange: () => pick(picker.files[0]) });
  const clip = h("button", { class: "btn clip", type: "button", "aria-label": "Attach a file", title: "Attach a file (10 MB max)",
                             onclick: () => picker.click() }, "📎");
  const pick = f => {
    file = f && f.size <= 10 * 1024 * 1024 ? f : null;
    if (f && !file) toast(`${f.name} is too big (10 MB max).`);
    chip.hidden = !file;
    chip.replaceChildren(...(file ? [h("span", {}, `📎 ${file.name}`),
      h("button", { type: "button", class: "chip-x", "aria-label": "Remove file", onclick: () => pick(null) }, "✕")] : []));
    picker.value = "";
  };
  const form = h("form", { onsubmit: e => { e.preventDefault(); submit(input.value); } }, clip, input, picker, send);
  const fresh = h("button", { class: "btn small", type: "button", onclick: newChat }, "New chat");
  const outbox = h("div", { class: "outbox", "aria-live": "polite" });
  const view = h("div", { class: "chat" },
    h("header", { class: "chat-head" }, h("h1", {}, "Chat"), fresh),
    scroller,
    h("div", { class: "composer" }, outbox, chip, form,
      h("p", { class: "note" }, "Same conversation as Telegram. Emails wait here (and in Telegram) with Undo or Send.")));
  layout("chat", view);
  refreshOutbox(outbox);
  state.timer = setInterval(() => refreshOutbox(outbox), 3000);

  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
  });
  view.addEventListener("dragover", e => { e.preventDefault(); });
  view.addEventListener("drop", e => { e.preventDefault(); if (e.dataTransfer.files[0]) pick(e.dataTransfer.files[0]); });
  input.addEventListener("paste", e => {
    const pasted = [...(e.clipboardData?.files || [])][0];
    if (pasted) { e.preventDefault(); pick(pasted); }
  });
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = `${input.scrollHeight}px`; });

  const bubble = (role, text, extra = "") => {
    const el = h("div", { class: `msg ${role} ${extra}` }, text);
    log.append(el);
    scroller.scrollTop = scroller.scrollHeight;
    return el;
  };
  const hello = () => log.replaceChildren(h("div", { class: "hello" },
    h("h2", {}, `Hi ${state.me.name}, what can I do?`), h("p", {}, "Email, calendar, reminders, research and files."),
    h("div", { class: "starters" }, STARTERS.map(s => h("button", { class: "btn", type: "button", onclick: () => submit(s) }, s)))));

  const history = await act(api("GET", "/api/history"));
  if (!history) return;
  if (history.messages.length) history.messages.forEach(m => bubble(m.role, m.text)); else hello();
  input.focus();

  async function newChat() {
    if (state.chatBusy) return;
    if (await act(api("POST", "/api/new"), "Fresh start. I still remember the important things.")) hello();
  }

  async function submit(text) {
    text = text.trim();
    if ((!text && !file) || state.chatBusy) return;
    state.chatBusy = true;
    send.disabled = fresh.disabled = clip.disabled = true;
    log.querySelector(".hello")?.remove();
    const attached = file;
    bubble("you", attached ? `📎 ${attached.name}${text ? `\n${text}` : ""}` : text);
    input.value = "";
    input.style.height = "auto";
    pick(null);
    const reply = bubble("claudebot", "", "pending");
    try {
      let body, headers = { "X-CSRF-Token": state.csrf };
      if (attached) {
        body = new FormData();
        body.append("text", text);
        body.append("file", attached, attached.name);  // the browser sets the multipart Content-Type
      } else {
        body = JSON.stringify({ text });
        headers["Content-Type"] = "application/json";
      }
      const res = await fetch("/api/chat", { method: "POST", credentials: "same-origin", headers, body });
      if (res.status === 401) throw new SignedOut();
      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Couldn't send that.");
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "", finished = false;
      while (!finished) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let cut;
        while ((cut = buffer.indexOf("\n\n")) >= 0) {
          const chunk = buffer.slice(0, cut);
          buffer = buffer.slice(cut + 2);
          const event = /^event: (.*)$/m.exec(chunk)?.[1];
          const data = JSON.parse(/^data: (.*)$/m.exec(chunk)?.[1] || "{}");
          if (event === "delta") { reply.textContent = data.text; scroller.scrollTop = scroller.scrollHeight; }
          if (event === "done") {
            reply.textContent = data.text;
            reply.classList.remove("pending");
            if (!data.ok) reply.classList.add("error");
            finished = true;
          }
        }
      }
      if (!finished) throw new Error("The connection dropped. Your message still went through; refresh to see the reply.");
    } catch (err) {
      if (err instanceof SignedOut) return showSignedOut();
      reply.classList.remove("pending");
      reply.classList.add("error");
      reply.textContent = err.message;
    } finally {
      refreshOutbox(outbox);
      state.chatBusy = false;
      send.disabled = fresh.disabled = clip.disabled = false;
      scroller.scrollTop = scroller.scrollHeight;
      input.focus();
    }
  }
}

// --- emails waiting for you ---------------------------------------------------------------------

async function refreshOutbox(box) {
  let data;
  try { data = await api("GET", "/api/outbox"); } catch { return; }
  box.replaceChildren(...data.emails.map(e => {
    const copies = [e.cc && `cc: ${e.cc}`, e.bcc && `bcc: ${e.bcc}`].filter(Boolean).join(" · ");
    const seconds = Math.max(0, Math.round((new Date(e.send_at) - Date.now()) / 1000));
    const run = async (path, done) => { if (await act(api("POST", `/api/outbox/${e.id}/${path}`), done)) refreshOutbox(box); };
    return h("div", { class: `mail ${e.status}` },
      h("div", { class: "grow" },
        h("b", {}, e.status === "held" ? "✉️ Ready to send" : `📤 Sending in ${seconds < 90 ? `${seconds}s` : `${Math.round(seconds / 60)} min`}`, " to ", e.to),
        copies ? h("div", { class: "copies" }, copies) : null,
        h("details", {}, h("summary", {}, e.subject), h("div", { class: "body" }, e.body))),
      h("div", { class: "row" }, e.status === "held"
        ? [h("button", { class: "btn small primary", onclick: () => run("send", "Sending") }, "✅ Send"),
           h("button", { class: "btn small", onclick: () => run("cancel", "Cancelled") }, "✖️ Cancel")]
        : h("button", { class: "btn small", onclick: () => run("cancel", "Cancelled: not sent") }, "↩️ Undo")));
  }));
}

// --- glance pages -----------------------------------------------------------------------------

async function todayPage() {
  const d = await act(api("GET", "/api/today"));
  if (!d) return;
  const cal = d.calendar.status === "ok"
    ? rows(d.calendar.events, e => h("li", {},
        h("span", { class: "time" }, e.all_day ? "all day" : `${e.start}–${e.end}`),
        h("span", { class: `grow ${e.declined ? "done" : ""}` }, e.title)), "Nothing scheduled.")
    : h("p", { class: "empty" }, d.calendar.status === "error" ? "Couldn't read your calendar just now."
                                                               : "Calendar not connected. Send /connect in Telegram.");
  layout("today", page(d.title, d.quiet_until ? `🔕 Quiet until ${d.quiet_until}` : "Today at a glance.",
    h("div", { class: "grid" },
      card("Calendar", cal),
      card("Reminders", rows(d.reminders, r => h("li", {}, h("span", { class: "time" }, r.time), h("span", { class: "grow" }, r.text)),
                             "Nothing due today.")),
      card("Bills due", rows(d.bills, b => h("li", {}, h("span", { class: "grow" }, b.name),
                                             h("span", {}, money(b.amount, b.currency)), h("span", { class: "pill warn" }, b.when)),
                             "No bills due today or tomorrow.")),
      card("Birthdays", rows(d.birthdays, b => h("li", {}, h("span", { class: "grow" }, `🎂 ${b.name}`), h("span", { class: "pill" }, b.when)),
                             "None this week.")),
      card("Waiting on you", h("p", {}, d.dms_waiting ? `${d.dms_waiting} Telegram chat${d.dms_waiting === 1 ? "" : "s"} waiting on a reply.`
                                                     : "Nobody is waiting on a Telegram reply."),
           d.dms_waiting ? h("a", { href: "#/dms" }, "See them") : null),
      card("Lists", rows(d.lists, l => h("li", {}, h("span", { class: "grow" }, l.name), h("span", { class: "pill" }, `${l.open} open`)),
                         "No open list items.")))));
}

async function weekPage() {
  const d = await act(api("GET", "/api/week"));
  if (!d) return;
  const icon = { event: "📅", reminder: "⏰", bill: "🧾", birthday: "🎂" };
  const note = { error: "Couldn't read your calendar just now.", disconnected: "Calendar not connected (send /connect in Telegram)." }[d.calendar];
  layout("week", page("Your week", note || "The next 7 days.",
    card(null, d.days.map(day => h("div", { class: "week-day" },
      h("h3", {}, day.label, " ", h("span", { class: "pill" }, day.items.length ? `${day.items.length}` : "free")),
      day.items.length ? h("ul", { class: "rows" }, day.items.map(i => h("li", {},
        h("span", { "aria-hidden": "true" }, icon[i.kind]), h("span", { class: "time" }, i.time || ""), h("span", { class: "grow" }, i.text))))
        : null)))));
}

// --- lists ------------------------------------------------------------------------------------

async function listsPage() {
  const d = await act(api("GET", "/api/lists"));
  if (!d) return;
  const listName = h("input", { class: "field", placeholder: "List (e.g. Shopping)", "aria-label": "List", value: d.lists[0]?.name || "Shopping" });
  const item = h("input", { class: "field flex1", placeholder: "Add an item", "aria-label": "Item" });
  const add = h("form", { class: "row", onsubmit: async e => {
    e.preventDefault();
    if (!item.value.trim()) return;
    if (await act(api("POST", "/api/lists/items", { list: listName.value, items: [item.value] }))) listsPage();
  } }, listName, item, h("button", { class: "btn primary" }, "Add"));
  layout("lists", page("Lists", "Tap to check things off. Same lists as /lists in Telegram.",
    card(null, add), h("div", { class: "spacer" }),
    h("div", { class: "grid" }, d.lists.map(l => card(l.name,
      rows(l.items, i => h("li", {},
        h("input", { type: "checkbox", class: "check", checked: i.done, "aria-label": i.text,
                     onchange: async () => { if (await act(api("POST", `/api/lists/${l.id}/items/${i.id}/toggle`))) listsPage(); } }),
        h("span", { class: `grow ${i.done ? "done" : ""}` }, i.text)), "Empty."),
      l.items.some(i => i.done) ? h("div", { class: "row mt" },
        h("button", { class: "btn small", onclick: async () => { if (await act(api("POST", `/api/lists/${l.id}/clear`), "Cleared checked items")) listsPage(); } },
          "Clear checked")) : null))),
    d.lists.length ? null : h("p", { class: "empty" }, "No lists yet. Add an item above, or tell ClaudeBot \"add milk to my shopping list\".")));
}

// --- reminders, bills, birthdays ---------------------------------------------------------------

async function remindersPage() {
  const d = await act(api("GET", "/api/reminders"));
  if (!d) return;
  const what = h("input", { class: "field flex1", placeholder: "Remind me to…", "aria-label": "Reminder", required: true, maxlength: 300 });
  const local = botLocalInput(new Date(Date.now() + 3600e3)).slice(0, 14) + "00";  // the next whole hour
  const when = h("input", { class: "field", type: "datetime-local", "aria-label": "When", required: true, value: local });
  const repeat = h("select", { class: "field", "aria-label": "Repeat" },
    ["none", "daily", "weekdays", "weekly", "biweekly", "monthly", "yearly"].map(r => h("option", { value: r }, r === "none" ? "once" : r)));
  const form = h("form", { class: "row", onsubmit: async e => {
    e.preventDefault();
    if (await act(api("POST", "/api/reminders", { text: what.value, when: when.value, repeat: repeat.value }), "Reminder set")) remindersPage();
  } }, what, when, repeat, h("button", { class: "btn primary" }, "Add"));
  layout("reminders", page("Reminders", "Add one here, or just ask: \"remind me Friday at 9 to renew my passport\". Times are in your ClaudeBot's time zone.",
    card(null, form), h("div", { class: "spacer" }),
    card(null, rows(d.reminders, r => h("li", {},
      h("span", { class: "time" }, fmtDate(r.next), h("br"), fmtTime(r.next)),
      h("span", { class: "grow" }, r.text),
      r.repeat !== "none" ? h("span", { class: "pill" }, r.repeat) : null,
      r.briefing ? h("span", { class: "pill" }, "briefing") : r.task ? h("span", { class: "pill" }, "task") : null,
      r.owned ? h("span", { class: "pill", title: "Change it on the Bills or Birthdays page" }, "auto")
        : h("button", { class: "btn small danger", onclick: async () => {
            if (await act(api("POST", `/api/reminders/${r.id}/cancel`), "Cancelled")) remindersPage();
          } }, "Cancel")), "No reminders."))));
}

async function billsPage() {
  const d = await act(api("GET", "/api/bills"));
  if (!d) return;
  const totals = {};
  d.bills.forEach(b => { totals[b.currency] = (totals[b.currency] || 0) + b.amount; });
  layout("bills", page("Bills", Object.keys(totals).length ? `Each month: ${Object.entries(totals).map(([c, v]) => money(v, c)).join(", ")}`
                                                          : "Tell ClaudeBot \"rent is $1200 on the 1st\" to add one.",
    card(null, rows(d.bills, b => h("li", {},
      h("span", { class: "grow" }, h("b", {}, b.name), h("br"), h("span", { class: "time" }, `due ${fmtDate(b.next_due)}`)),
      h("span", {}, money(b.amount, b.currency)),
      b.paid ? h("span", { class: "pill good" }, "✅ paid")
             : h("button", { class: "btn small", onclick: async () => {
                 if (await act(api("POST", `/api/bills/${b.id}/paid`), r => `Logged as paid for ${fmtDate(r.settled)}`)) billsPage();
               } }, "✅ Paid"),
      h("button", { class: "btn small danger", "aria-label": `Remove ${b.name}`, onclick: async () => {
        if (confirm(`Remove ${b.name} and its reminder?`) && await act(api("DELETE", `/api/bills/${b.id}`), "Removed")) billsPage();
      } }, "🗑")), "No bills yet."))));
}

async function birthdaysPage() {
  const d = await act(api("GET", "/api/birthdays"));
  if (!d) return;
  const name = h("input", { class: "field flex1", placeholder: "Name", "aria-label": "Name", required: true, maxlength: 40 });
  const date = h("input", { class: "field", type: "date", "aria-label": "Birthday", required: true });
  const form = h("form", { class: "row", onsubmit: async e => {
    e.preventDefault();
    const [, month, day] = date.value.split("-").map(Number);
    if (await act(api("POST", "/api/birthdays", { name: name.value, month, day }), `Saved ${name.value}`)) birthdaysPage();
  } }, name, date, h("button", { class: "btn primary" }, "Add"));
  layout("birthdays", page("Birthdays", "You get a heads-up the day before, and they show in Today and Week.",
    card(null, form), h("div", { class: "spacer" }),
    card(null, rows(d.birthdays, b => h("li", {},
      h("span", { class: "grow" }, `🎂 ${b.name}`), h("span", { class: "pill" }, fmtDate(b.next)),
      h("button", { class: "btn small danger", "aria-label": `Remove ${b.name}`, onclick: async () => {
        if (await act(api("DELETE", `/api/birthdays/${b.id}`), "Removed")) birthdaysPage();
      } }, "🗑")), "No birthdays yet."))));
}

// --- DMs, memory, activity --------------------------------------------------------------------

async function dmsPage() {
  const d = await act(api("GET", "/api/dms"));
  if (!d) return;
  layout("dms", page("Telegram DMs", d.connected ? "Who's waiting on a reply. Draft and send replies from Telegram (/dms)."
                                                 : "Not connected. In Telegram: Settings → Business → Chatbots → add your ClaudeBot.",
    card(null, rows(d.waiting, c => h("li", {},
      h("span", { class: "grow" }, h("b", {}, c.name), h("br"), c.messages.join(" / ")),
      h("span", { class: "pill" }, fmtTime(c.since))), "Nobody is waiting on you."))));
}

async function memoryPage() {
  const d = await act(api("GET", "/api/memories"));
  if (!d) return;
  const fact = h("input", { class: "field flex1", placeholder: "Something to remember (e.g. my passport expires in May 2028)", "aria-label": "Memory", required: true, maxlength: 500 });
  const form = h("form", { class: "row", onsubmit: async e => {
    e.preventDefault();
    if (await act(api("POST", "/api/memories", { text: fact.value }), "Remembered")) memoryPage();
  } }, fact, h("button", { class: "btn primary" }, "Add"));
  layout("memory", page("Memory", "What ClaudeBot remembers about you. Add something here, or tell it \"remember that…\".",
    card(null, form), h("div", { class: "spacer" }),
    card(null, rows(d.memories, m => h("li", {}, h("span", { class: "grow" }, m.text),
      h("button", { class: "btn small danger", onclick: async () => {
        if (await act(api("DELETE", `/api/memories/${m.id}`), "Forgotten")) memoryPage();
      } }, "Forget")), "Nothing yet."))));
}

async function activityPage() {
  const [log, usage] = await Promise.all([act(api("GET", "/api/log?days=7")), act(api("GET", "/api/usage"))]);
  if (!log || !usage) return;
  layout("activity", page("Activity", "What ClaudeBot actually did, recorded when it happened.",
    h("div", { class: "grid" },
      card("This month", h("p", { class: "big" }, money(usage.month_cost, "USD")),
        h("p", { class: "empty" }, usage.budget ? `of your ${money(usage.budget, "USD")} budget` : "No monthly budget set."),
        rows(usage.by_source, s => h("li", {}, h("span", { class: "grow" }, s.source), h("span", { class: "time" }, money(s.cost, "USD"))), ""))),
    h("div", { class: "spacer" }),
    card("Last 7 days", rows(log.actions, a => h("li", {},
      h("span", { class: "time" }, fmtDate(a.at, { month: "short", day: "numeric" }), h("br"), fmtTime(a.at)),
      h("span", { class: "pill" }, a.kind), h("span", { class: "grow" }, a.summary)), "Nothing yet."))));
}

// --- settings ---------------------------------------------------------------------------------

async function settingsPage() {
  const s = await act(api("GET", "/api/settings"));
  if (!s) return;
  const change = async (body, message) => { if (await act(api("POST", "/api/settings", body), message)) settingsPage(); };
  const toggle = (checked, onchange, label) => h("label", { class: "switch" },
    h("input", { type: "checkbox", role: "switch", checked, "aria-label": label, onchange: e => onchange(e.target.checked) }));
  layout("settings", page("Settings", "Everything else is in /settings in Telegram.",
    card("Pause", h("div", { class: "setting" },
      h("div", {}, h("b", {}, s.quiet_until ? `Quiet until ${fmtTime(s.quiet_until)}` : "Alerts and check-ins are on"),
        h("p", {}, "Reminders you set still come through.")),
      h("div", { class: "row" }, s.quiet_until
        ? h("button", { class: "btn", onclick: () => change({ quiet: "off" }, "Back on") }, "Resume")
        : [h("button", { class: "btn", onclick: () => change({ quiet: "1h" }, "Quiet for an hour") }, "1 hour"),
           h("button", { class: "btn", onclick: () => change({ quiet: "morning" }, "Quiet until morning") }, "Until morning")]))),
    h("div", { class: "spacer" }),
    card("Inbox alerts",
      h("div", { class: "setting" }, h("div", {}, h("b", {}, "Hourly digest"), h("p", {}, "One message an hour instead of a ping per email. Urgent email still comes right away.")),
        toggle(s.alert_mode === "hourly", on => change({ alert_mode: on ? "hourly" : "instant" }, on ? "Hourly digest on" : "Alerts come right away"), "Hourly digest")),
      h("div", { class: "setting" }, h("div", {}, h("b", {}, "Urgent email can wake me"), h("p", {}, `During quiet hours (${s.quiet_hours || "none"}) and pauses, at most 3 times in 12 hours.`)),
        toggle(s.urgent_wakes, on => change({ urgent_wakes: on }, on ? "Urgent email can wake you" : "Quiet time is fully quiet"), "Urgent email can wake me"))),
    h("div", { class: "spacer" }),
    card("Security", h("div", { class: "setting" },
      h("div", {}, h("b", {}, "Sign out everywhere"), h("p", {}, "Ends every web and desktop session. Get a new link with /web in Telegram.")),
      h("button", { class: "btn danger", onclick: async () => {
        if (confirm("Sign out of every browser and the desktop app?") && await act(api("POST", "/api/logout-all"))) showSignedOut("Signed out everywhere.");
      } }, "Sign out all")))));
}

function openSearch(query) {
  state.query = query;
  if (location.hash === "#/search") searchPage(); else location.hash = "#/search";
}

async function searchPage() {
  const input = h("input", { class: "field flex1", type: "search", placeholder: "Search memories, lists, reminders, bills, birthdays",
                             "aria-label": "Search", value: state.query || "" });
  const results = h("div", {});
  const run = async () => {
    state.query = input.value;
    const d = input.value.trim().length < 2 ? { results: [] } : await act(api("GET", `/api/search?q=${encodeURIComponent(input.value)}`));
    if (!d) return;
    const icon = { memory: "🧠", list: "🗒", reminder: "⏰", bill: "🧾", birthday: "🎂" };
    results.replaceChildren(card(null, rows(d.results, r => h("li", {},
      h("span", { "aria-hidden": "true" }, icon[r.kind]), h("a", { class: "grow", href: `#/${r.page}` }, r.text)),
      input.value.trim().length < 2 ? "Type at least two letters." : "Nothing found. Ask ClaudeBot in Chat: it can also search your email and calendar.")));
  };
  let timer;
  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 200); });
  layout("search", page("Search", "Everything stored in your ClaudeBot. Email and calendar search happen in Chat.",
    h("div", { class: "row" }, input), h("div", { class: "spacer" }), results));
  input.focus();
  run();
}

function morePage() {
  layout("more", page("More", null, card(null, h("div", { class: "nav" }, [["search", "🔎", "Search"], ...PAGES.slice(4)].map(([n, i, l]) => navLink(n, i, l, null))),
    h("div", { class: "spacer" }), h("button", { class: "btn", onclick: signOut }, "Sign out"))));
}

// --- boot -------------------------------------------------------------------------------------

const VIEWS = { chat: chatPage, today: todayPage, week: weekPage, lists: listsPage, reminders: remindersPage,
                bills: billsPage, birthdays: birthdaysPage, dms: dmsPage, memory: memoryPage, activity: activityPage,
                settings: settingsPage, more: morePage, search: searchPage };

async function render() {
  if (!state.me) return;
  await VIEWS[route()]();
  document.title = `${PAGES.find(p => p[0] === route())?.[2] || (route() === "search" ? "Search" : "More")} · ClaudeBot`;
}

async function boot() {
  if (location.pathname === "/login") {
    const signedIn = await signInFromLink();
    if (signedIn === null) return;
  }
  try {
    state.me = await api("GET", "/api/me");
    state.csrf = state.me.csrf;
  } catch (err) {
    return err instanceof SignedOut ? showSignedOut() : app.replaceChildren(h("div", { class: "center" }, err.message));
  }
  window.addEventListener("hashchange", render);
  window.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      const box = document.getElementById("search");
      if (box && box.offsetParent) box.focus(); else location.hash = "#/search";
    }
  });
  await render();
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
boot();
