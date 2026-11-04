const form = document.getElementById("form");
const input = document.getElementById("link");
const error = document.getElementById("error");
const button = form.querySelector("button");

const message = new URLSearchParams(location.search).get("message");
if (message) { error.textContent = message; error.hidden = false; }

form.addEventListener("submit", async event => {
  event.preventDefault();
  error.hidden = true;
  button.disabled = true;
  try {
    await window.claudebot.connect(input.value);
  } catch (err) {
    // Electron prefixes IPC errors with "Error invoking remote method ...: Error: "; show just the reason.
    error.textContent = String(err.message || err).replace(/^.*Error: /, "");
    error.hidden = false;
    button.disabled = false;
  }
});
input.focus();
