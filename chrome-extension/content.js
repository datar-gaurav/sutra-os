/**
 * Sutra Job Capture — LinkedIn content script
 *
 * Extracts job details from LinkedIn job view pages and makes them available
 * to the popup via chrome.runtime messaging.
 *
 * LinkedIn's DOM changes frequently. Each field tries several selectors in
 * order so the script degrades gracefully rather than failing completely.
 */

"use strict";

/**
 * Try a list of CSS selectors and return the trimmed text of the first match,
 * or fallback if none match.
 */
function trySelectors(selectors, fallback = "") {
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.textContent.trim()) {
      return el.textContent.trim();
    }
  }
  return fallback;
}

/**
 * Extract salary info — LinkedIn shows it in an insight chip or a dedicated section.
 */
function extractSalary() {
  // Try structured salary insight chips
  const insights = document.querySelectorAll(
    ".job-details-jobs-unified-top-card__job-insight, " +
    ".jobs-unified-top-card__job-insight, " +
    ".job-details-preferences-and-skills__pill"
  );
  for (const el of insights) {
    const text = el.textContent.trim();
    // Salary strings contain currency symbols or "per year/hour/month"
    if (/[$£€¥₹]|per\s+(year|hour|month|annum)|k\/yr|salary/i.test(text)) {
      return text.replace(/\s+/g, " ").trim();
    }
  }

  // Fallback: scan all text nodes for salary patterns
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const salaryRe = /\$[\d,]+\s*[-–]\s*\$[\d,]+|\$[\d,]+[kK]?\s*(\/\s*(yr|year|hour|hr))?/;
  let node;
  while ((node = walker.nextNode())) {
    if (salaryRe.test(node.textContent)) {
      return node.textContent.trim().slice(0, 120);
    }
  }

  return "";
}

/**
 * Extract the full job description text.
 */
function extractDescription() {
  const selectors = [
    "#job-details",
    ".jobs-description__content",
    ".jobs-description-content__text",
    ".description__text",
    "[data-test-id='job-description']",
    ".job-details-jobs-unified-top-card__job-description",
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) {
      // Preserve newlines from block elements
      const clone = el.cloneNode(true);
      clone.querySelectorAll("br").forEach((br) => br.replaceWith("\n"));
      clone.querySelectorAll("li").forEach((li) => {
        li.prepend(document.createTextNode("• "));
        li.append(document.createTextNode("\n"));
      });
      clone.querySelectorAll("p, div, h1, h2, h3, h4").forEach((block) => {
        block.append(document.createTextNode("\n"));
      });
      const text = clone.textContent.replace(/\n{3,}/g, "\n\n").trim();
      if (text.length > 50) return text;
    }
  }
  return "";
}

/**
 * Scrape all job details from the current page.
 */
function scrapeJob() {
  const jobTitle = trySelectors([
    "h1.job-details-jobs-unified-top-card__job-title",
    "h1.topcard__title",
    ".job-details-jobs-unified-top-card__job-title h1",
    ".jobs-unified-top-card__job-title h1",
    ".jobs-details-top-card__job-title",
    "h1",
  ]);

  const company = trySelectors([
    ".job-details-jobs-unified-top-card__company-name a",
    ".job-details-jobs-unified-top-card__company-name",
    ".topcard__org-name-link",
    ".jobs-unified-top-card__company-name a",
    ".jobs-unified-top-card__company-name",
    "[data-test-id='job-card-company-name']",
  ]);

  const location = trySelectors([
    ".job-details-jobs-unified-top-card__bullet",
    ".jobs-unified-top-card__bullet",
    ".topcard__flavor--bullet",
    ".jobs-details-top-card__bullet",
    "[data-test-id='job-card-location']",
  ]);

  const salary = extractSalary();
  const jobDescription = extractDescription();
  const jobUrl = window.location.href.split("?")[0]; // strip tracking params

  return {
    job_title: jobTitle,
    company,
    location,
    salary,
    job_description: jobDescription,
    job_url: jobUrl,
    source: "linkedin",
    captured_at: new Date().toISOString(),
  };
}

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  if (request.action === "scrapeJob") {
    try {
      sendResponse({ success: true, data: scrapeJob() });
    } catch (err) {
      sendResponse({ success: false, error: err.message });
    }
  }
  return true; // keep message channel open for async sendResponse
});
