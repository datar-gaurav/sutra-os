/**
 * Sutra Job Capture — service worker (Manifest V3 background)
 *
 * Handles cross-origin fetch requests from the popup since content scripts
 * and popups cannot always reach non-LinkedIn origins directly.
 */

"use strict";

chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  if (request.action === "sendWebhook") {
    const { webhookUrl, payload } = request;

    fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(async (res) => {
        const text = await res.text().catch(() => "");
        sendResponse({ ok: res.ok, status: res.status, body: text });
      })
      .catch((err) => {
        sendResponse({ ok: false, status: 0, body: err.message });
      });

    return true; // keep the message channel open for async response
  }
});
