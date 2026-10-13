# Huayapp HTML Scraper Design

**Date:** 2026-10-10

**Status:** Phase 1 verified; Phase 2 approved

## Goal

Collect publicly rendered lottery results from `https://huayapp.com/` without using Huayapp's official API, normalize verified values, and make the data available for the existing lottery system.

## Verified source structure

- `GET https://huayapp.com/` returns an HTML page containing lottery cards.
- The current page exposes 142 cards across 9 categories, but this count may change.
- A card is identified by `.lotto-card[data-lotto-id]`.
- Card metadata is stored in `data-lotto-id`, `data-lotto-name`, `data-category`, `data-date-update`, and `data-date-display`.
- Prize labels are in `.lotto-cell-label` inside `.lotto-cell`.
- Historical navigation is exposed by `button.button-after-result`; the page loads history dynamically after the button is activated.
- Winning numbers are not text nodes. They are drawn into `canvas.frontend-canvas-obf` elements from obfuscated `data-val` values.
- The browser-rendered page visibly shows real values, but the accessibility tree and DOM text do not expose those values.
- Some cards explicitly show pending or suspended states such as `รอผลออก` or `งด`; those must not be treated as numbers.
- `robots.txt` currently allows crawling (`User-agent: *`, `Allow: /`). This is not treated as legal permission; the scraper will use conservative request pacing and will not bypass access controls.

## Extraction strategy

1. Use `requests` and `BeautifulSoup4/lxml` to fetch and parse the page shell, card metadata, labels, dates, and explicit status text.
2. Use Playwright only for cards whose result values are canvas-rendered or require the historical modal.
3. Capture the rendered canvas pixels and run OCR/vision against the rendered number. OCR output is accepted only when it matches the expected digit count and validation rules.
4. Reject ambiguous OCR, missing canvases, pending results, suspended results, changed layouts, and incomplete prize groups. Do not infer values from obfuscated tokens.
5. Keep a source snapshot or compact audit record for accepted and rejected records.

The first implementation will target one verified page/card flow: the current Thai government lottery card (`lotto-card-100`) and its latest result. Category discovery and historical navigation will be added only after this flow has an offline fixture and validation test.

## Normalized record

```json
{
  "source": "huayapp.com",
  "lottery_id": "100",
  "lottery_name": "รัฐบาลไทย",
  "category": "หวยทางการ",
  "result_date": "YYYY-MM-DD",
  "result_time": null,
  "round": null,
  "prizes": [
    {"prize_name": "รางวัลที่ 1", "numbers": ["000000"]}
  ],
  "status": "published",
  "scraped_at": "ISO-8601",
  "source_url": "https://huayapp.com/",
  "source_text": null
}
```

All numbers remain strings so leading zeroes are preserved. The example values above are schema placeholders, not observed winning numbers.

## Reliability and safety

- Use a bounded timeout, exponential retry only for transient failures, and a configurable delay between page/browser operations.
- Never bypass CAPTCHA, login, anti-bot controls, or other access restrictions.
- Treat explicit unpublished/suspended states separately from network or parser failures.
- Use a stable uniqueness key based on source, lottery ID, date, round, and prize name.
- Never replace an existing published record with an incomplete or invalid scrape.
- Log URL, selector, category, and failure reason for every rejected record.

## Integration boundary

The scraper will initially be a standalone Python package and SQLite store. After the minimal extraction is proven, an adapter will map verified records into the existing application's result tables or a new normalized table; no mapping will be invented before the target system's required fields are confirmed.

## Testing boundary

- Unit tests use sanitized saved HTML and canvas/OCR fixtures; they never depend on live network access.
- Integration tests are opt-in and clearly labeled as network tests.
- At least one integration assertion must compare parsed metadata and rendered result output against the currently observed source page.
- No synthetic winning number will be reported as a successful live integration result.

## Known limitations

- The current source deliberately hides numbers in canvas, so a pure requests/BeautifulSoup implementation cannot recover the winning values.
- OCR/vision can fail on visual changes, low-resolution canvases, or animation/loading states; uncertain output must be rejected.
- Historical data is loaded dynamically and must be collected only through verified UI navigation.
- The site may change selectors, obfuscation, canvas rendering, categories, or result schedules without notice.
