# Selector Cookbook

## Login forms
Username/email and password fields are usually `input[type=email]`, `input[type=password]`, but some sites obfuscate with generic names. Fallbacks:
- `input[autocomplete=username]` / `input[autocomplete=current-password]`
- `input[name*=email i]`, `input[name*=user i]`

## Infinite scroll
- Wait for a known "load more" element OR scroll height to change.
- `browser_scroll` + `browser_wait` for new content selector. Bail after N scrolls without change.

## Modal dismissal
- Try `[aria-label*=close i]`, `button[class*=close i]`, `[role=dialog] button:has-text(×)`.
- If a modal blocks interaction, screenshot first — sometimes it's a consent banner with a different "Reject all" path.

## Dynamic IDs (React, Vue)
React often generates IDs like `:r5:`, `:r6:`. Don't rely on them. Use:
- ARIA roles: `[role=button][name=Submit]`
- Data attributes: `[data-testid=submit]`
- Text content: `button:has-text("Submit")`

## Iframes
`browser_extract_text` may miss iframe content. If a page has an iframe (e.g., Stripe Elements, YouTube embeds), interactions inside require explicit iframe targeting — may need to ask the user for a different approach.

## Rate limiting
A single fast loop against one domain will trigger bot detection. Insert `browser_wait` of 500-2000ms between actions on the same site.
