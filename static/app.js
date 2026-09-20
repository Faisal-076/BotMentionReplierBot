/**
 * Telegram Bot Mention Replier - Control Center Frontend Logic
 */

let currentConfig = {
  bot_tokens: [],
  reply_mode: "both",
  parse_mode: "HTML",
  disable_web_page_preview: false,
  reply_delay: 0.0,
  reply_templates: [],
  poll_timeout: 25,
};

let verifiedTokensData = [];
let lastFocusedTextarea = null;
let uptimeInterval = null;

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  fetchConfig();
  fetchStatus();
  startLogPolling();
  setInterval(fetchStatus, 3000);
});

// Switch Tab
function switchTab(tabId) {
  document.querySelectorAll(".tab-content").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach((el) => el.classList.remove("active"));

  const targetTab = document.getElementById(`tab-${tabId}`);
  const targetBtn = document.getElementById(`tab-btn-${tabId}`);
  if (targetTab) targetTab.classList.add("active");
  if (targetBtn) targetBtn.classList.add("active");

  if (tabId === "tokens" && verifiedTokensData.length === 0) {
    verifyTokens();
  }
}

// Toast Notifications
function showToast(message, type = "success") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// Fetch Cluster Status
async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();

    const statusDot = document.getElementById("status-dot");
    const statusText = document.getElementById("cluster-status-text");
    const uptimeEl = document.getElementById("cluster-uptime");

    if (data.is_running) {
      statusDot.className = "pulse-dot running";
      statusText.textContent = "Cluster Running";
    } else {
      statusDot.className = "pulse-dot stopped";
      statusText.textContent = "Cluster Stopped";
    }

    // Format Uptime
    const secs = data.uptime_seconds || 0;
    const mins = Math.floor(secs / 60);
    const hrs = Math.floor(mins / 60);
    uptimeEl.textContent = `${hrs}h ${mins % 60}m ${secs % 60}s`;

    // Overview Stats
    document.getElementById("stat-active-bots").textContent = data.active_bots_count;
    document.getElementById("stat-configured-tokens").textContent = `${data.configured_tokens_count} tokens configured`;
    document.getElementById("stat-reply-mode").textContent = data.reply_mode;
    document.getElementById("stat-templates-count").textContent = data.templates_count;

    // Connected Bots List
    renderConnectedBots(data.bots || []);
  } catch (err) {
    console.error("Failed to fetch status:", err);
  }
}

// Render Connected Bots
function renderConnectedBots(bots) {
  const container = document.getElementById("bots-list-container");
  if (!bots.length) {
    container.innerHTML = `<p class="text-muted">No bots currently active. Click 'Start' above or add tokens in 'Bot Tokens'.</p>`;
    return;
  }

  container.innerHTML = bots
    .map(
      (b) => `
    <div class="bot-card">
      <div class="bot-card-top">
        <span class="bot-name">🤖 @${b.username}</span>
        <span class="badge ${b.is_running ? "badge-success" : "badge-danger"}">${b.is_running ? "POLLING" : "IDLE"}</span>
      </div>
      <div>
        <span class="badge ${b.guest_supported ? "badge-info" : "badge-danger"}">
          ${b.guest_supported ? "🌟 Guest Mode: ENABLED" : "⚠️ Guest Mode: OFF"}
        </span>
      </div>
    </div>
  `
    )
    .join("");
}

// Fetch Settings & Config
async function fetchConfig() {
  try {
    const res = await fetch("/api/config");
    if (!res.ok) return;
    currentConfig = await res.json();

    // Populate Settings tab
    document.getElementById("setting-reply-mode").value = currentConfig.reply_mode;
    document.getElementById("setting-parse-mode").value = currentConfig.parse_mode;
    document.getElementById("setting-reply-delay").value = currentConfig.reply_delay;
    updateDelayLabel(currentConfig.reply_delay);
    document.getElementById("setting-disable-preview").checked = currentConfig.disable_web_page_preview;

    // Render Tokens Table
    renderTokensTable();

    // Render Templates
    renderTemplatesList();
  } catch (err) {
    console.error("Failed to fetch config:", err);
  }
}

// Delay Slider Label
function updateDelayLabel(val) {
  const label = document.getElementById("delay-label");
  const num = parseFloat(val);
  label.textContent = num === 0 ? "0.0s (Instant)" : `${num.toFixed(1)}s`;
}

// Render Tokens Table
function renderTokensTable() {
  const tbody = document.getElementById("tokens-table-body");
  if (!currentConfig.bot_tokens || !currentConfig.bot_tokens.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No bot tokens added yet. Click '+ Add New Bot Token'.</td></tr>`;
    return;
  }

  tbody.innerHTML = currentConfig.bot_tokens
    .map((token, index) => {
      const preview = `...${token.slice(-8)}`;
      const verified = verifiedTokensData.find((v) => v.token_preview === preview);
      const username = verified ? `@${verified.username}` : "Click Verify";
      const guestBadge = verified
        ? verified.guest_mode
          ? `<span class="badge badge-success">Enabled</span>`
          : `<span class="badge badge-danger">Disabled</span>`
        : `<span class="badge badge-info">Unknown</span>`;

      return `
      <tr>
        <td>${index + 1}</td>
        <td><code>${preview}</code></td>
        <td><strong>${username}</strong></td>
        <td>${guestBadge}</td>
        <td><span class="badge badge-success">Configured</span></td>
        <td>
          <button class="btn btn-danger btn-xs" onclick="deleteToken(${index})">Remove</button>
        </td>
      </tr>
    `;
    })
    .join("");
}

// Verify Tokens with Telegram
async function verifyTokens() {
  showToast("Verifying bot tokens with Telegram...", "info");
  try {
    const res = await fetch("/api/tokens/verify");
    const data = await res.json();
    verifiedTokensData = data.results || [];
    renderTokensTable();
    showToast("Token verification complete!", "success");
  } catch (err) {
    showToast("Failed to verify tokens: " + err, "error");
  }
}

// Token Modal
function showAddTokenModal() {
  document.getElementById("modal-add-token").classList.remove("hidden");
  document.getElementById("input-new-token").focus();
}

function hideAddTokenModal() {
  document.getElementById("modal-add-token").classList.add("hidden");
  document.getElementById("input-new-token").value = "";
}

async function submitNewToken() {
  const input = document.getElementById("input-new-token");
  const token = input.value.trim();
  if (!token) {
    alert("Please enter a valid Bot Token.");
    return;
  }

  if (currentConfig.bot_tokens.includes(token)) {
    alert("This bot token is already added.");
    return;
  }

  currentConfig.bot_tokens.push(token);
  hideAddTokenModal();
  renderTokensTable();
  await saveConfiguration();
  verifyTokens();
}

async function deleteToken(index) {
  if (!confirm("Are you sure you want to remove this bot token?")) return;
  currentConfig.bot_tokens.splice(index, 1);
  renderTokensTable();
  await saveConfiguration();
}

// Templates Handling
function renderTemplatesList() {
  const container = document.getElementById("templates-list-container");
  if (!currentConfig.reply_templates || !currentConfig.reply_templates.length) {
    currentConfig.reply_templates = ["🔥 Hello <b>{first_name}</b>, thanks for mentioning me!"];
  }

  container.innerHTML = currentConfig.reply_templates
    .map(
      (tmpl, index) => `
    <div class="template-item">
      <textarea class="template-textarea" id="tmpl-${index}" onfocus="lastFocusedTextarea = this" oninput="currentConfig.reply_templates[${index}] = this.value">${tmpl}</textarea>
      <button class="btn btn-danger btn-xs" onclick="deleteTemplate(${index})">✕</button>
    </div>
  `
    )
    .join("");
}

function loadClonePreset() {
  const cloneText = `<b>😀😀😀😀😀😀牛逼项目看这里......\n\n😀风口项目绿色, 安全, 无风险🔥..\n\n🔥 手 机 拍 照 项 目 💥\n\n有无经验都可做, 小白可教\n\n💸拍 收 款 码 80 元/ 单💸\n\n💸拍私家车100-1000元/单📣\n\n工资日结 日赚3200 +\n\n了解 : @lnmei3nakz</b>`;
  currentConfig.reply_templates = [cloneText];
  renderTemplatesList();
  showToast("🌟 GXH19 Clone template loaded! Click Save Templates to activate.", "success");
}

function addNewTemplate() {
  currentConfig.reply_templates.push("✨ <b>Special Update for {first_name}</b>: Check this out!");
  renderTemplatesList();
}

function deleteTemplate(index) {
  if (currentConfig.reply_templates.length <= 1) {
    alert("You must keep at least one reply template.");
    return;
  }
  currentConfig.reply_templates.splice(index, 1);
  renderTemplatesList();
}

function insertVariable(varName) {
  if (!lastFocusedTextarea) {
    lastFocusedTextarea = document.querySelector(".template-textarea");
  }
  if (!lastFocusedTextarea) return;

  const start = lastFocusedTextarea.selectionStart;
  const end = lastFocusedTextarea.selectionEnd;
  const text = lastFocusedTextarea.value;
  lastFocusedTextarea.value = text.substring(0, start) + varName + text.substring(end);
  lastFocusedTextarea.focus();
  lastFocusedTextarea.selectionStart = lastFocusedTextarea.selectionEnd = start + varName.length;

  // Trigger input event to update model
  lastFocusedTextarea.dispatchEvent(new Event("input"));
}

// Save Configuration
async function saveConfiguration() {
  // Sync form inputs
  currentConfig.reply_mode = document.getElementById("setting-reply-mode").value;
  currentConfig.parse_mode = document.getElementById("setting-parse-mode").value;
  currentConfig.reply_delay = parseFloat(document.getElementById("setting-reply-delay").value);
  currentConfig.disable_web_page_preview = document.getElementById("setting-disable-preview").checked;

  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentConfig),
    });
    const data = await res.json();
    if (res.ok) {
      showToast("Configuration saved successfully!", "success");
      fetchStatus();
    } else {
      showToast("Error saving: " + data.detail, "error");
    }
  } catch (err) {
    showToast("Network error saving configuration: " + err, "error");
  }
}

// Cluster Controls
async function startCluster() {
  try {
    const res = await fetch("/api/cluster/start", { method: "POST" });
    const data = await res.json();
    showToast(data.message, "success");
    setTimeout(fetchStatus, 1000);
  } catch (err) {
    showToast("Failed to start cluster: " + err, "error");
  }
}

async function stopCluster() {
  try {
    const res = await fetch("/api/cluster/stop", { method: "POST" });
    const data = await res.json();
    showToast(data.message, "info");
    setTimeout(fetchStatus, 1000);
  } catch (err) {
    showToast("Failed to stop cluster: " + err, "error");
  }
}

async function restartCluster() {
  try {
    showToast("Restarting Bot Cluster...", "info");
    const res = await fetch("/api/cluster/restart", { method: "POST" });
    const data = await res.json();
    showToast(data.message, "success");
    setTimeout(fetchStatus, 1500);
  } catch (err) {
    showToast("Failed to restart cluster: " + err, "error");
  }
}

// Live Logs
async function fetchLogs() {
  try {
    const res = await fetch("/api/logs");
    if (!res.ok) return;
    const data = await res.json();
    const consoleEl = document.getElementById("live-log-console");
    const autoScroll = document.getElementById("auto-scroll-check").checked;

    if (data.logs && data.logs.length) {
      consoleEl.innerHTML = data.logs
        .map((log) => {
          let cssClass = "log-info";
          if (log.level === "ERROR") cssClass = "log-error";
          else if (log.level === "WARNING") cssClass = "log-warning";
          else if (log.message.includes("Mention") || log.message.includes("🎯")) cssClass = "log-mention";
          else if (log.message.includes("Successfully") || log.message.includes("✅")) cssClass = "log-success";

          return `<div class="log-entry ${cssClass}">[${log.time}] [${log.level}] ${escapeHtml(log.message)}</div>`;
        })
        .join("");

      if (autoScroll) {
        consoleEl.scrollTop = consoleEl.scrollHeight;
      }
    }
  } catch (err) {
    console.error("Log fetch error:", err);
  }
}

function startLogPolling() {
  fetchLogs();
  setInterval(fetchLogs, 1500);
}

function clearLogs() {
  document.getElementById("live-log-console").innerHTML = `<div class="log-entry log-info">[SYSTEM] Logs cleared.</div>`;
}

function escapeHtml(text) {
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
  return text.replace(/[&<>"']/g, (m) => map[m]);
}
