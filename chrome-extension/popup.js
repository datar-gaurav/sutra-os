"use strict";

// ── Helpers ───────────────────────────────────────────────────────────────────

function showView(id) {
  ["view-not-linkedin", "view-main", "view-settings"].forEach((v) => {
    document.getElementById(v).classList.remove("active");
  });
  document.getElementById(id).classList.add("active");
}

function showStatus(el, message, type) {
  el.textContent = message;
  el.className = `status ${type}`;
}

function setText(id, text, placeholder = false) {
  const el = document.getElementById(id);
  if (!text || !text.trim()) {
    el.textContent = "—";
    el.classList.add("placeholder");
  } else {
    el.textContent = text.trim();
    el.classList.remove("placeholder");
  }
}

// ── State ─────────────────────────────────────────────────────────────────────

let capturedData = null;

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  const { webhookUrl } = await chrome.storage.sync.get("webhookUrl");

  // Wire settings view
  const inputWebhook = document.getElementById("input-webhook");
  if (webhookUrl) inputWebhook.value = webhookUrl;

  document.getElementById("btn-save-settings").addEventListener("click", saveSettings);
  document.getElementById("btn-back").addEventListener("click", () => showView("view-main"));
  document.getElementById("btn-open-settings").addEventListener("click", () => showView("view-settings"));
  document.getElementById("btn-open-settings-empty").addEventListener("click", () => showView("view-settings"));
  document.getElementById("btn-send").addEventListener("click", sendToSutra);

  // Detect active tab
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const isLinkedInJob = tab && tab.url && /linkedin\.com\/jobs\//i.test(tab.url);

  if (!isLinkedInJob) {
    showView("view-not-linkedin");
    return;
  }

  showView("view-main");
  await scrapeCurrentTab(tab.id);
});

// ── Scrape ────────────────────────────────────────────────────────────────────

async function scrapeCurrentTab(tabId) {
  const statusEl = document.getElementById("status-msg");
  const sendBtn  = document.getElementById("btn-send");

  showStatus(statusEl, "Reading job details…", "info");

  try {
    // Re-inject content script in case the page loaded before the extension was installed
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"],
    }).catch(() => {});

    const response = await chrome.tabs.sendMessage(tabId, { action: "scrapeJob" });

    if (!response || !response.success) {
      showStatus(statusEl, `Could not read page: ${response?.error || "unknown error"}`, "error");
      return;
    }

    capturedData = response.data;
    renderJobData(capturedData);

    const missing = ["job_title", "company", "location", "job_description"]
      .filter((k) => !capturedData[k]);

    if (missing.length === 0) {
      statusEl.className = "status"; // hide
    } else {
      showStatus(statusEl, `Captured — ${missing.join(", ")} not found on page.`, "info");
    }

    sendBtn.disabled = !(capturedData.job_title || capturedData.job_description);

  } catch (err) {
    showStatus(statusEl, `Scrape failed: ${err.message}`, "error");
  }
}

function renderJobData(data) {
  setText("field-title",   data.job_title);
  setText("field-company", data.company);
  setText("field-location", data.location);
  setText("field-salary",  data.salary);

  const desc = data.job_description || "";
  setText("field-desc", desc.length > 400 ? desc.slice(0, 400) + "…" : desc);
}

// ── Send ──────────────────────────────────────────────────────────────────────

async function sendToSutra() {
  const statusEl = document.getElementById("status-msg");
  const sendBtn  = document.getElementById("btn-send");

  const { webhookUrl } = await chrome.storage.sync.get("webhookUrl");

  if (!webhookUrl) {
    showStatus(statusEl, "No webhook URL configured. Click Settings to add one.", "error");
    return;
  }

  if (!capturedData) {
    showStatus(statusEl, "No job data captured yet.", "error");
    return;
  }

  sendBtn.disabled = true;
  showStatus(statusEl, "Sending to Sutra…", "info");

  // Delegate the fetch to the background service worker (avoids CORS issues)
  chrome.runtime.sendMessage(
    { action: "sendWebhook", webhookUrl, payload: capturedData },
    (response) => {
      if (chrome.runtime.lastError) {
        showStatus(statusEl, `Extension error: ${chrome.runtime.lastError.message}`, "error");
        sendBtn.disabled = false;
        return;
      }

      if (response && response.ok) {
        showStatus(
          statusEl,
          `Sent! Resume Builder is tailoring your resume for ${capturedData.company || "this role"}.`,
          "success"
        );
        // Keep button disabled to prevent double-send
      } else {
        const detail = response ? `HTTP ${response.status}: ${response.body}` : "No response";
        showStatus(statusEl, `Failed to send: ${detail}`, "error");
        sendBtn.disabled = false;
      }
    }
  );
}

// ── Settings ──────────────────────────────────────────────────────────────────

async function saveSettings() {
  const inputWebhook  = document.getElementById("input-webhook");
  const settingsStatus = document.getElementById("settings-status");
  const url = inputWebhook.value.trim();

  if (!url) {
    showStatus(settingsStatus, "Please enter a webhook URL.", "error");
    return;
  }

  try {
    new URL(url); // validate format
  } catch {
    showStatus(settingsStatus, "Invalid URL format.", "error");
    return;
  }

  await chrome.storage.sync.set({ webhookUrl: url });
  showStatus(settingsStatus, "Saved!", "success");

  setTimeout(() => showView("view-main"), 800);
}
