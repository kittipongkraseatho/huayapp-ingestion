# Huayapp HTML Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python 3.11+ scraper that collects verified Huayapp lottery metadata and browser-rendered canvas numbers, validates them, and stores/export results in SQLite, JSON, and CSV without using Huayapp's official API.

**Architecture:** `requests` + BeautifulSoup/lxml parse the server HTML and discover cards. Playwright renders only the selected card and historical modal; an OCR adapter reads canvas pixels and rejects ambiguous output. A normalized dataclass flows through validation into idempotent SQLite storage and CLI exports.

**Tech Stack:** Python 3.11+, requests, beautifulsoup4, lxml, Playwright, Pillow, rapidocr-onnxruntime, pytest.

**Spec:** `docs/superpowers/specs/2026-10-10-huayapp-html-scraper-design.md`

## Global Constraints

- Primary source is `https://huayapp.com/`; do not silently replace HTML scraping with the official API.
- Numbers are strings and must preserve leading zeroes.
- Do not bypass CAPTCHA, authentication, anti-bot protections, or access controls.
- Reject ambiguous, incomplete, pending, suspended, or layout-changed records.
- Unit tests run offline with fixtures; live integration tests are opt-in.
- No fabricated winning number is evidence of live integration success.
- This workspace is not a Git repository; do not attempt commits or destructive worktree operations.

## Review Focus

- Canvas values are not DOM text; test that missing/ambiguous OCR is rejected rather than guessed.
- Thai Buddhist dates must normalize to ISO dates without changing the displayed source text.
- Pending (`รอผลออก`) and suspended (`งด`) cells must not become numbers.
- Repeated runs must not duplicate a result and incomplete records must not overwrite published rows.
- CSV must preserve number strings with leading zeroes and Unicode prize names.

### Task 1: Project skeleton, models, metadata parser, and validator

**Files:**
- Create: `huayapp_scraper/__init__.py`
- Create: `huayapp_scraper/models.py`
- Create: `huayapp_scraper/config.py`
- Create: `huayapp_scraper/html_parser.py`
- Create: `huayapp_scraper/validator.py`
- Create: `tests/fixtures/thai_gov_latest.html`
- Create: `tests/test_html_parser.py`
- Create: `tests/test_validator.py`
- Create: `requirements.txt`
- Create: `.env.example`

**Interfaces:**
- `parse_cards(html: str, source_url: str) -> list[LotteryCard]`
- `parse_card(card_html: str, source_url: str) -> LotteryCard`
- `normalize_thai_date(value: str) -> date`
- `validate_record(record: LotteryResult) -> ValidationResult`

- [ ] Write failing fixture tests for verified card selectors, status extraction, and preserved metadata.
- [ ] Run `pytest tests/test_html_parser.py tests/test_validator.py -q` and verify failure is due to missing modules/functions.
- [ ] Implement typed models, config defaults, HTML parsing, Buddhist-date conversion, and record validation.
- [ ] Run the focused tests and verify they pass.
- [ ] Run the full available pytest suite and record the result.

### Task 2: HTTP client, browser canvas capture, OCR adapter, and one-card scraper

**Files:**
- Create: `huayapp_scraper/http_client.py`
- Create: `huayapp_scraper/ocr.py`
- Create: `huayapp_scraper/browser.py`
- Create: `huayapp_scraper/scraper.py`
- Create: `tests/test_http_client.py`
- Create: `tests/test_ocr.py`
- Create: `tests/test_scraper.py`

**Interfaces:**
- `HttpClient.get(url: str) -> str`
- `CanvasOCR.read(image: Image.Image, expected_digits: int | None) -> str | None`
- `BrowserScraper.scrape_card(lottery_id: str) -> LotteryResult`
- `scrape_latest(config: Config, lottery_id: str = "100") -> LotteryResult`

- [ ] Write failing tests for retry/backoff classification, OCR digit-count rejection, and rejection of pending/suspended cards.
- [ ] Run the focused tests and verify failure before implementation.
- [ ] Implement bounded HTTP retries, Playwright card selection, canvas screenshots, and OCR behind an injectable adapter.
- [ ] Implement the minimal verified flow for `lotto-card-100`; do not decode `data-val`.
- [ ] Run focused tests and verify pass.
- [ ] Run an opt-in live probe against `https://huayapp.com/` and save only sanitized diagnostics; report any OCR uncertainty instead of storing it.

### Task 3: SQLite storage, deduplication, and exports

**Files:**
- Create: `huayapp_scraper/storage.py`
- Create: `tests/test_storage.py`
- Create: `tests/test_exports.py`

**Interfaces:**
- `SQLiteStore(path: Path)`
- `SQLiteStore.upsert(result: LotteryResult) -> bool`
- `SQLiteStore.list_results(...) -> list[LotteryResult]`
- `export_json(results, path) -> None`
- `export_csv(results, path) -> None`

- [ ] Write failing tests for schema creation, stable uniqueness, incomplete overwrite protection, JSON string preservation, and CSV Unicode/leading zeroes.
- [ ] Run focused tests and verify failure.
- [ ] Implement normalized tables, indexes, JSON audit payload, idempotent upsert, and exports.
- [ ] Run focused tests and verify pass.

### Task 4: CLI, logging, documentation, and scheduling hooks

**Files:**
- Create: `huayapp_scraper/cli.py`
- Create: `main.py`
- Create: `huayapp_scraper/scheduler.py`
- Create: `tests/test_cli.py`
- Create: `huayapp_scraper/README.md`

**Interfaces:**
- CLI commands: `inspect`, `scrape-latest`, `scrape`, `export`, `stats`, `validate`.
- `schedule_latest(config: Config, interval_seconds: int) -> None`

- [ ] Write failing CLI tests for inspect, stats, and export command routing.
- [ ] Run focused tests and verify failure.
- [ ] Implement argparse CLI, structured logging, progress/failure summaries, and a scheduler hook that reuses the scraper without starting duplicate work.
- [ ] Document setup, Playwright browser installation, rate limits, OCR limitations, CSV import precautions, and live-test opt-in.
- [ ] Run all unit tests and `python main.py inspect`.

### Task 5: Verification and integration report

**Files:**
- Modify: `huayapp_scraper/README.md`
- Create: `docs/superpowers/reports/2026-10-10-huayapp-scraper-verification.md`

- [ ] Run the complete offline test suite.
- [ ] Run the live inspect command against the verified page.
- [ ] Run the live scraper only if browser/OCR dependencies are available and the result passes validation.
- [ ] Report exact live status, selectors, records accepted/rejected, and limitations without inventing results.
