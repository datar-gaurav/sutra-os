/**
 * Sutra Job Capture — LinkedIn content script
 *
 * Extracts job details from LinkedIn job pages. LinkedIn is a React SPA so
 * content loads asynchronously after navigation. The scraper retries for up to
 * 3 seconds before giving up, and uses multiple selector strategies plus
 * document.title parsing as a reliable fallback for title and company.
 */

"use strict";

// ── Selector lists (tried in order, first non-empty text wins) ─────────────

const TITLE_SELECTORS = [
  ".job-details-jobs-unified-top-card__job-title h1",
  ".job-details-jobs-unified-top-card__job-title",
  ".jobs-unified-top-card__job-title h1",
  ".jobs-unified-top-card__job-title",
  ".topcard__title",
  ".jobs-details-top-card__job-title",
  "h1.t-24",
  "h1",
];

const COMPANY_SELECTORS = [
  ".job-details-jobs-unified-top-card__company-name a",
  ".job-details-jobs-unified-top-card__company-name",
  ".jobs-unified-top-card__company-name a",
  ".jobs-unified-top-card__company-name",
  ".topcard__org-name-link",
  ".topcard__org-name-link--black-link",
  ".jobs-details-top-card__company-url",
  "[data-tracking-control-name='public_jobs_topcard-org-name']",
];

const LOCATION_SELECTORS = [
  ".job-details-jobs-unified-top-card__primary-description-container .tvm__text",
  ".job-details-jobs-unified-top-card__bullet",
  ".jobs-unified-top-card__bullet",
  ".topcard__flavor--bullet",
  ".jobs-unified-top-card__workplace-type",
  ".job-details-jobs-unified-top-card__workplace-type",
];

const DESCRIPTION_SELECTORS = [
  "#job-details",
  ".jobs-description__content",
  ".jobs-description-content__text",
  ".description__text",
  ".jobs-box__html-content",
  "[data-test-id='job-description']",
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function trySelectors(selectors) {
  for (const sel of selectors) {
    try {
      const el = document.querySelector(sel);
      if (el) {
        const text = el.innerText || el.textContent || "";
        if (text.trim()) return text.trim();
      }
    } catch (_) {}
  }
  return "";
}

/**
 * Parse title and company from the browser tab title as a fallback.
 * LinkedIn sets: "Job Title at Company | LinkedIn" or "Job Title - Company | LinkedIn"
 */
function parseFromDocTitle() {
  const raw = document.title.replace(/\s*\|\s*LinkedIn\s*$/i, "").trim();
  const atMatch = raw.match(/^(.+?)\s+at\s+(.+)$/i);
  if (atMatch) return { title: atMatch[1].trim(), company: atMatch[2].trim() };
  const dashMatch = raw.match(/^(.+?)\s+[-–]\s+(.+)$/);
  if (dashMatch) return { title: dashMatch[1].trim(), company: dashMatch[2].trim() };
  return { title: raw, company: "" };
}

function extractSalary() {
  // Structured salary insight chips
  const chipSelectors = [
    ".job-details-jobs-unified-top-card__job-insight",
    ".jobs-unified-top-card__job-insight",
    ".job-details-preferences-and-skills__pill",
    ".job-details-jobs-unified-top-card__job-insight-view-model-secondary",
    "[aria-label*='salary' i]",
    "[aria-label*='compensation' i]",
  ];
  for (const sel of chipSelectors) {
    for (const el of document.querySelectorAll(sel)) {
      const text = el.innerText || el.textContent || "";
      if (/[$£€¥₹]|per\s+(year|hour|month|annum)|k\/yr|salary|\bK\b/i.test(text)) {
        return text.replace(/\s+/g, " ").trim().slice(0, 150);
      }
    }
  }
  // Walk text nodes for salary patterns
  const salaryRe = /\$[\d,]+(?:\s*[kK])?\s*(?:[-–]\s*\$[\d,]+(?:\s*[kK])?)?(?:\s*\/\s*(?:yr|year|hour|hr))?/;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const t = node.textContent.trim();
    if (salaryRe.test(t) && t.length < 200) return t;
  }
  return "";
}

function extractDescription() {
  for (const sel of DESCRIPTION_SELECTORS) {
    try {
      const el = document.querySelector(sel);
      if (!el) continue;
      const clone = el.cloneNode(true);
      // Preserve structure as readable text
      clone.querySelectorAll("br").forEach((br) => br.replaceWith("\n"));
      clone.querySelectorAll("li").forEach((li) => {
        li.prepend(document.createTextNode("• "));
        li.append(document.createTextNode("\n"));
      });
      clone.querySelectorAll("p, div, h1, h2, h3, h4, h5").forEach((b) =>
        b.append(document.createTextNode("\n"))
      );
      const text = (clone.innerText || clone.textContent || "")
        .replace(/\n{3,}/g, "\n\n")
        .trim();
      if (text.length > 80) return text;
    } catch (_) {}
  }
  return "";
}

function extractLocation() {
  const raw = trySelectors(LOCATION_SELECTORS);
  if (raw) {
    // Strip salary/workplace-type noise that sometimes bleeds into the location chip
    return raw.split(/\n|\|/)[0].trim();
  }
  return "";
}

// ── Main scrape ────────────────────────────────────────────────────────────────

function scrapeJob() {
  let jobTitle = trySelectors(TITLE_SELECTORS);
  let company  = trySelectors(COMPANY_SELECTORS);

  // Reliable fallback: parse from document.title
  if (!jobTitle || !company) {
    const parsed = parseFromDocTitle();
    if (!jobTitle) jobTitle = parsed.title;
    if (!company)  company  = parsed.company;
  }

  return {
    job_title:        jobTitle,
    company:          company,
    location:         extractLocation(),
    salary:           extractSalary(),
    job_description:  extractDescription(),
    job_url:          window.location.href.split("?")[0],
    source:           "linkedin",
    captured_at:      new Date().toISOString(),
  };
}

/** Returns true if we have at least a title or description — worth sending. */
function hasUsefulData(data) {
  return !!(data.job_title || data.job_description);
}

// ── Retry wrapper: LinkedIn SPA loads content asynchronously ──────────────────

async function scrapeWithRetry(maxWaitMs = 3000, intervalMs = 300) {
  const deadline = Date.now() + maxWaitMs;
  let best = scrapeJob();
  if (hasUsefulData(best)) return best;

  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, intervalMs));
    const attempt = scrapeJob();
    // Keep whichever attempt has more data
    if (
      (attempt.job_title && !best.job_title) ||
      (attempt.job_description && !best.job_description) ||
      (attempt.company && !best.company)
    ) {
      best = attempt;
    }
    if (
      best.job_title &&
      best.company &&
      best.job_description
    ) {
      break; // good enough
    }
  }
  return best;
}

// ── Message listener ───────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  if (request.action === "scrapeJob") {
    scrapeWithRetry()
      .then((data) => sendResponse({ success: true, data }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true; // keep channel open for async response
  }
});
