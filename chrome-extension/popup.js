"use strict";

const DEFAULT_WEBHOOK_URL =
  "http://localhost:8000/api/public/job-applications/capture";

async function getWebhookUrl() {
  const { webhookUrl } = await chrome.storage.sync.get("webhookUrl");
  return webhookUrl || DEFAULT_WEBHOOK_URL;
}

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

function setField(id, text) {
  const el = document.getElementById(id);
  el.value = text && text.trim() ? text.trim() : "";
}

function getField(id) {
  return document.getElementById(id).value.trim();
}

// ── State ─────────────────────────────────────────────────────────────────────

let capturedData = null;

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  const webhookUrl = await getWebhookUrl();

  // Wire settings view — prefill with current or default URL so the user can see/edit
  const inputWebhook = document.getElementById("input-webhook");
  inputWebhook.value = webhookUrl;

  document.getElementById("btn-save-settings").addEventListener("click", saveSettings);
  document.getElementById("btn-back").addEventListener("click", () => showView("view-main"));
  document.getElementById("btn-open-settings").addEventListener("click", () => showView("view-settings"));
  document.getElementById("btn-open-settings-empty").addEventListener("click", () => showView("view-settings"));
  document.getElementById("btn-send").addEventListener("click", sendToSutra);
  document.getElementById("btn-retry").addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) await scrapeCurrentTab(tab.id);
  });

  // Detect active tab
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const isJobPage = tab && tab.url && (
    /linkedin\.com\/jobs\//i.test(tab.url) ||
    /myworkdayjobs\.com\//i.test(tab.url)
  );

  if (!isJobPage) {
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
      showStatus(statusEl, `Captured — edit any field before sending. Missing: ${missing.join(", ")}.`, "info");
    }

    sendBtn.disabled = false;

  } catch (err) {
    showStatus(statusEl, `Scrape failed: ${err.message}`, "error");
  }
}

function renderJobData(data) {
  setField("field-title",    data.job_title);
  setField("field-company",  data.company);
  setField("field-location", data.location);
  setField("field-salary",   data.salary);
  setField("field-desc",     data.job_description);
}

// ── Send ──────────────────────────────────────────────────────────────────────

async function sendToSutra() {
  const statusEl = document.getElementById("status-msg");
  const sendBtn  = document.getElementById("btn-send");

  const webhookUrl = await getWebhookUrl();

  if (!webhookUrl) {
    showStatus(statusEl, "No webhook URL configured. Click Settings to add one.", "error");
    return;
  }

  const payload = {
    ...(capturedData || {}),
    job_title:       getField("field-title"),
    company:         getField("field-company"),
    location:        getField("field-location"),
    salary:          getField("field-salary"),
    job_description: getField("field-desc"),
  };

  if (!payload.job_title && !payload.job_description) {
    showStatus(statusEl, "Add at least a role or description before sending.", "error");
    return;
  }

  sendBtn.disabled = true;
  showStatus(statusEl, "Sending to Sutra…", "info");

  try {
    const res = await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const body = await res.text().catch(() => "");

    if (res.ok) {
      showStatus(
        statusEl,
        `Sent! Resume Builder is tailoring your resume for ${payload.company || "this role"}.`,
        "success"
      );
    } else {
      showStatus(statusEl, `Server error ${res.status}: ${body.slice(0, 120)}`, "error");
      sendBtn.disabled = false;
    }
  } catch (err) {
    // Provide actionable guidance based on the error
    let msg = `Network error: ${err.message}.`;
    if (/fetch|network|failed/i.test(err.message)) {
      msg += " Is the Sutra backend running and the webhook URL correct?";
    }
    showStatus(statusEl, msg, "error");
    sendBtn.disabled = false;
  }
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
