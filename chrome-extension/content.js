/**
 * Sutra Job Capture — LinkedIn content script
 *
 * LinkedIn is a React SPA with frequent DOM changes. This script uses a
 * layered approach: specific selectors → document.title parsing → structural
 * heuristics. Retries for up to 4s to handle SPA lazy-loading.
 */

"use strict";

// ── Title ─────────────────────────────────────────────────────────────────────

function extractTitle() {
  // Specific selectors first — avoid containers that include company name
  const selectors = [
    ".job-details-jobs-unified-top-card__job-title h1",
    ".jobs-unified-top-card__job-title h1",
    ".topcard__title",
    ".job-details-jobs-unified-top-card__job-title",
    ".jobs-unified-top-card__job-title",
    "h1.t-24",
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) {
      const text = (el.innerText || el.textContent || "").trim();
      if (text) return text;
    }
  }

  // Fallback: document.title is "Role at Company | LinkedIn" or "Role - Company | LinkedIn"
  const parsed = parseFromDocTitle();
  return parsed.title;
}

// ── Company ───────────────────────────────────────────────────────────────────

function extractCompany() {
  // Best signal: a link whose href contains /company/
  for (const a of document.querySelectorAll("a[href*='/company/']")) {
    const text = (a.innerText || a.textContent || "").trim();
    if (text && text.length < 80) return text;
  }

  const selectors = [
    ".job-details-jobs-unified-top-card__company-name a",
    ".job-details-jobs-unified-top-card__company-name",
    ".jobs-unified-top-card__company-name a",
    ".jobs-unified-top-card__company-name",
    ".topcard__org-name-link",
    ".jobs-details-top-card__company-url",
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) {
      const text = (el.innerText || el.textContent || "").trim();
      if (text) return text;
    }
  }

  // Last resort: title parsing
  const parsed = parseFromDocTitle();
  return parsed.company;
}

// ── Location ──────────────────────────────────────────────────────────────────

function extractLocation() {
  const selectors = [
    ".job-details-jobs-unified-top-card__primary-description-container .tvm__text",
    ".jobs-unified-top-card__bullet",
    ".job-details-jobs-unified-top-card__bullet",
    ".topcard__flavor--bullet",
    ".jobs-unified-top-card__workplace-type",
    "[data-test-id='job-card-location']",
  ];
  for (const sel of selectors) {
    // Some of these selectors match multiple elements; take the first short one
    for (const el of document.querySelectorAll(sel)) {
      const text = (el.innerText || el.textContent || "").trim();
      // Location strings are short; skip salary / workplace chips
      if (text && text.length < 100 && !/\$|per\s+(year|hour)/i.test(text)) {
        return text.split(/\n/)[0].trim();
      }
    }
  }
  return "";
}

// ── Salary ────────────────────────────────────────────────────────────────────

function extractSalary() {
  const salaryRe = /[$£€¥₹][\d,]+|[\d,]+[kK]\s*(\/\s*(yr|year|hour|hr))?|per\s+(year|hour|month)/i;

  const chipSelectors = [
    ".job-details-jobs-unified-top-card__job-insight",
    ".jobs-unified-top-card__job-insight",
    ".job-details-preferences-and-skills__pill",
    ".job-details-jobs-unified-top-card__job-insight-view-model-secondary",
    ".compensation__salary",
    "[aria-label*='salary' i]",
  ];
  for (const sel of chipSelectors) {
    for (const el of document.querySelectorAll(sel)) {
      const text = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
      if (salaryRe.test(text) && text.length < 200) return text;
    }
  }

  // Text-node scan
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const strongRe = /[$£€][\d,]+(?:\s*[kK])?\s*[-–—]\s*[$£€][\d,]+/;
  let node;
  while ((node = walker.nextNode())) {
    const t = node.textContent.trim();
    if (strongRe.test(t) && t.length < 200) return t;
  }
  return "";
}

// ── Description ───────────────────────────────────────────────────────────────

function extractDescription() {
  // Try known containers
  const selectors = [
    "#job-details",
    ".jobs-description__content",
    ".jobs-description-content__text",
    ".jobs-description",
    ".description__text",
    ".jobs-box__html-content",
    "[data-test-id='job-description']",
    ".job-view-layout",
  ];

  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (!el) continue;
    const text = domToText(el);
    if (text.length > 100) return text;
  }

  // Structural heuristic: find the <section> or <div> that contains the
  // most text and looks like a job description (has bullet points or paragraphs)
  let best = "";
  for (const el of document.querySelectorAll("section, article, [class*='description'], [class*='details']")) {
    const text = domToText(el);
    if (text.length > best.length && text.length > 200) {
      best = text;
    }
  }
  if (best) return best;

  // Nuclear fallback: grab everything inside <main>
  const main = document.querySelector("main");
  if (main) {
    const text = domToText(main);
    if (text.length > 100) return text.slice(0, 8000);
  }

  return "";
}

function domToText(el) {
  const clone = el.cloneNode(true);
  // Remove nav, header, button elements that add noise
  clone.querySelectorAll("nav, header, footer, button, script, style, [aria-hidden='true']")
    .forEach((n) => n.remove());
  clone.querySelectorAll("br").forEach((br) => br.replaceWith("\n"));
  clone.querySelectorAll("li").forEach((li) => {
    li.prepend(document.createTextNode("• "));
    li.append(document.createTextNode("\n"));
  });
  clone.querySelectorAll("p, div, h1, h2, h3, h4, h5, section").forEach((b) =>
    b.append(document.createTextNode("\n"))
  );
  return (clone.innerText || clone.textContent || "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

// ── document.title parser ─────────────────────────────────────────────────────

function parseFromDocTitle() {
  // Strip trailing "| LinkedIn" or "- LinkedIn"
  let raw = document.title
    .replace(/\s*[|–-]\s*LinkedIn\s*$/i, "")
    .trim();

  // "Role at Company"
  const atIdx = raw.search(/\bat\b/i);
  if (atIdx > 0) {
    return {
      title:   raw.slice(0, atIdx).trim(),
      company: raw.slice(atIdx + 3).trim(),
    };
  }

  // "Role - Company" or "Role | Company" (last separator wins for company)
  const sepMatch = raw.match(/^(.+?)(?:\s[-–|]\s|\s[-–|])(.+)$/);
  if (sepMatch) {
    return { title: sepMatch[1].trim(), company: sepMatch[2].trim() };
  }

  return { title: raw, company: "" };
}

// ── Main scrape ────────────────────────────────────────────────────────────────

function scrapeJob() {
  return {
    job_title:       extractTitle(),
    company:         extractCompany(),
    location:        extractLocation(),
    salary:          extractSalary(),
    job_description: extractDescription(),
    job_url:         window.location.href.split("?")[0],
    source:          "linkedin",
    captured_at:     new Date().toISOString(),
  };
}

function dataQuality(d) {
  return [d.job_title, d.company, d.location, d.job_description]
    .filter(Boolean).length;
}

// ── Retry (SPA lazy-load) ─────────────────────────────────────────────────────

async function scrapeWithRetry(maxWaitMs = 4000, intervalMs = 400) {
  let best = scrapeJob();
  if (dataQuality(best) === 4) return best;

  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, intervalMs));
    const attempt = scrapeJob();
    if (dataQuality(attempt) > dataQuality(best)) best = attempt;
    if (dataQuality(best) === 4) break;
  }
  return best;
}

// ── Message listener ──────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  if (request.action === "scrapeJob") {
    scrapeWithRetry()
      .then((data) => sendResponse({ success: true, data }))
      .catch((err)  => sendResponse({ success: false, error: err.message }));
    return true;
  }
});
