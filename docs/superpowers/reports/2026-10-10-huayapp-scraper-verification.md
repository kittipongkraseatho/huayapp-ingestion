# Huayapp scraper verification

Date: 2026-10-10 (Asia/Bangkok)

## Offline verification

- Full pytest suite: **21 passed**.
- Fixtures contain sanitized placeholder canvas tokens only.
- Tests cover card metadata/status parsing, Thai Buddhist date normalization,
  retry classification, rendered-glyph acceptance/rejection, pending and
  suspended cards, SQLite deduplication, incomplete overwrite protection, and
  JSON/CSV leading-zero preservation.

## Live verification

Source: [https://huayapp.com/](https://huayapp.com/)

- `GET /` reachable.
- 142 result cards discovered across 9 categories during this run.
- Verified selectors:
  - `.lotto-card[data-lotto-id]`
  - `.lotto-cell-label`
  - `canvas.frontend-canvas-obf`
  - `button.button-after-result`
- `scrape-latest --lottery-id 100` succeeded with Chromium device scale 3.
- One published record was stored in `live-huayapp-template.db`.
- A second live run was idempotent (`inserted: 0`); database stats remained
  `published: 1` and `validate` returned `valid: true`.
- The accepted record date was `2026-10-01`; all values were validated as
  digit strings, including leading-zero values `058`.

The canvas values are read from browser-rendered pixels. The implementation
does not read or decode the site's `data-val` attributes. A normal OCR attempt
was rejected as ambiguous; the final reader uses glyph templates rendered from
the canvas context and requires every glyph score to pass the configured
threshold.

## Known scope

The current implementation is a safe latest-card pipeline. It does not yet
automatically traverse the historical modal. Latest results are now written to
the existing Bun app's `lottery.db` in separate `lottery_results` and
`lottery_prizes` tables, and are available from `/api/huayapp-results` plus the
`huayapp` field in `/api/lottery-snapshot`.
