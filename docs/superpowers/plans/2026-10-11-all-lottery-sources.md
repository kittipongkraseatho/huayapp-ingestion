# All Lottery Sources Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** เพิ่ม ingestion pipeline ที่ดึงผลหวยทุก card จาก Huayapp และแหล่งสาธารณะภายนอกหลายกลุ่ม เก็บผลใน SQLite รูปแบบกลาง และแสดงผลในแท็บรวม/แท็บแยกพร้อม auto-refresh และ source health status

**Architecture:** ให้ Python package ใน `huayapp_scraper` เป็น ingestion service หลัก เพราะมี HTTP, Playwright/OCR, validator และ SQLite store อยู่แล้ว แยก source adapter ออกจาก storage และ API; ให้ FastAPI ใน `huayapp-api/app.py` เป็น API สำหรับ refresh/status/results ส่วน `server.ts` รักษา compatibility และอ่าน normalized tables ได้โดยไม่แตะตาราง legacy

**Tech Stack:** Python 3.11+, FastAPI, Pydantic, Playwright, BeautifulSoup, SQLite, Bun/TypeScript, static HTML + Tailwind classes, pytest, Node contract tests

**Spec:** `docs/superpowers/specs/2026-10-11-all-lottery-sources-design.md`

## Global Constraints

- ค้นพบและดึงการ์ดผลทั้งหมดของ Huayapp แบบ dynamic ไม่จำกัดเฉพาะ lottery ID เดิม
- ใช้ source adapter/registry สำหรับแหล่งภายนอก และใช้ public endpoint/HTML ที่อนุญาตเท่านั้น
- ไม่ bypass CAPTCHA, authentication, access control หรือเงื่อนไขการใช้งานของเว็บ
- ตัวเลขทุกตัวเก็บเป็น string เพื่อรักษาเลขศูนย์นำหน้า
- ผล pending/suspended/incomplete ห้ามเขียนทับผล published เดิม
- แหล่งหนึ่งล่มต้องไม่หยุดการดึงแหล่งอื่น และต้องเก็บ error ล่าสุดกับสถานะ stale
- auto-refresh ทุก 60 วินาทีขณะหน้าที่เกี่ยวข้องเปิดอยู่ และมี manual refresh
- ห้ามลบหรือ migrate ตาราง legacy `yiki_results` และ `stocks_results`
- ทุก adapter ที่เปิดใช้งานต้องมี fixture/parser test; แหล่งที่ไม่มี public endpoint ที่ยืนยันได้ต้องรายงาน `unavailable` แทนการเดาข้อมูล
- Workspace ปัจจุบันไม่มี Git repository จึงให้ใช้ test/diff checkpoints แทนคำสั่ง commit และห้ามอ้างว่ามี commit

---

## File Map

### Existing files to modify

- `huayapp_scraper/models.py` — เพิ่ม metadata ของ source item, country และ source payload โดยรักษา constructor เดิมให้ใช้ได้
- `huayapp_scraper/config.py` — เพิ่ม interval และ source configuration จาก environment
- `huayapp_scraper/storage.py` — migration แบบ additive, normalized result upsert/list, source health state
- `huayapp_scraper/scraper.py` — scrape ทุก card และคืนผล/ข้อผิดพลาดรายรายการ
- `huayapp_scraper/cli.py` — คำสั่ง `scrape-all` และ `refresh`
- `huayapp-api/app.py` — results/sources/refresh endpoints และ background refresh lifecycle
- `server.ts` — additive schema/API compatibility สำหรับ normalized results
- `index.html` — แท็บรวม/แยก, filters, source status, refresh และ timer
- `README.md` — วิธีตั้งค่า source, รัน ingestion, endpoint และข้อจำกัด
- `tests/test_config.py`, `tests/test_storage.py`, `tests/test_scraper.py`, `tests/test_cli.py` — regression และ feature tests
- `tests/huayapp-display-contract.mjs` — อัปเดต display contract และเพิ่ม unified-results contract

### New files to create

- `huayapp_scraper/sources/__init__.py` — public source adapter exports
- `huayapp_scraper/sources/base.py` — `SourceSpec`, `SourceFetch`, `SourceAdapter` protocol และ shared error/result types
- `huayapp_scraper/sources/registry.py` — `build_source_registry(config)` และ source enable/disable resolution
- `huayapp_scraper/sources/huayapp.py` — adapter ที่ค้นพบทุก card และใช้ browser decoder ของเดิม
- `huayapp_scraper/sources/external.py` — configured public HTML/JSON adapters และ source-specific normalization hooks
- `huayapp_scraper/refresh.py` — orchestration, per-source isolation, retry/status recording
- `tests/fixtures/external/` — sanitized fixture ของทุก source adapter ที่เปิดใช้งาน
- `tests/test_sources.py` — adapter/registry/normalization tests
- `tests/test_refresh.py` — orchestration, stale/error และ isolation tests
- `tests/test_api_contract.py` — FastAPI endpoint tests
- `tests/server-contract.mjs` — static/HTTP contract checks for Bun compatibility

---

### Task 1: Extend the canonical result model and SQLite schema

**Files:**
- Modify: `huayapp_scraper/models.py`
- Modify: `huayapp_scraper/storage.py`
- Modify: `server.ts`
- Test: `tests/test_storage.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: existing `LotteryResult`, `PrizeResult`, `SQLiteStore.upsert()` and legacy SQLite database files
- Produces: `LotteryResult.source_item_id: str`, `LotteryResult.country: str`, `LotteryResult.metadata: dict[str, str]`; `SQLiteStore.list_results()` returning those fields; `SQLiteStore.upsert_source_state()` and `SQLiteStore.list_source_states()`

- [ ] **Step 1: Write the failing model/storage tests**

Add tests that construct a result with `source_item_id="thai-gov-1"`, `country="TH"`, and `metadata={"open": "1432.50"}`, then assert the values survive `upsert()` and `list_results()`. Add a migration test that creates an old-schema `lottery_results` table, opens `SQLiteStore`, and asserts the new columns and `lottery_sources` table exist.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```powershell
py -3.11 -m pytest tests/test_storage.py -q
```

Expected: FAIL because the model does not accept the new fields and the old schema has no normalized/source-health columns.

- [ ] **Step 3: Add backward-compatible model fields**

Append defaulted fields to `LotteryResult` so existing tests and callers remain valid:

```python
source_item_id: str = ""
country: str = ""
metadata: dict[str, str] = field(default_factory=dict)
```

Use `lottery_id` as the fallback source item ID when reading legacy rows.

- [ ] **Step 4: Implement additive SQLite migrations**

In `SQLiteStore._create_schema()`, create new columns only with `ALTER TABLE ... ADD COLUMN` after checking `PRAGMA table_info(lottery_results)`. Add `metadata_json TEXT NOT NULL DEFAULT '{}'`, `source_item_id TEXT NOT NULL DEFAULT ''`, and `country TEXT NOT NULL DEFAULT ''`. Add `lottery_sources` with `source_id` primary key, display metadata, enabled/status, `last_attempt_at`, `last_success_at`, `last_error`, and `result_count`.

Update `upsert()` and `list_results()` to serialize/deserialize metadata and use `source_item_id or lottery_id` for identity. Keep the existing unique key and legacy tables unchanged.

- [ ] **Step 5: Add Bun schema compatibility**

In `server.ts`, add the same columns and `lottery_sources` table using guarded `PRAGMA table_info` checks. Do not remove or rename `yiki_results`, `stocks_results`, `lottery_results`, or `lottery_prizes`.

- [ ] **Step 6: Run focused and regression tests**

Run:

```powershell
py -3.11 -m pytest tests/test_storage.py tests/test_config.py -q
```

Expected: all focused tests pass, including the existing idempotency and incomplete-result protection tests.

- [ ] **Step 7: Checkpoint the workspace**

Run `git status --short`; if it reports that this directory is not a repository, record that fact in the task notes and continue without a commit.

### Task 2: Define source adapter contracts and registry

**Files:**
- Create: `huayapp_scraper/sources/__init__.py`
- Create: `huayapp_scraper/sources/base.py`
- Create: `huayapp_scraper/sources/registry.py`
- Modify: `huayapp_scraper/config.py`
- Test: `tests/test_sources.py`

**Interfaces:**
- Consumes: `Config` and normalized `LotteryResult`
- Produces:
  - `SourceSpec(source_id: str, name: str, country: str, category: str, url: str, enabled: bool)`
  - `SourceFetch(results: list[LotteryResult], status: str, fetched_at: datetime, error: str | None)`
  - `SourceAdapter.fetch(config: Config) -> SourceFetch`
  - `build_source_registry(config: Config) -> dict[str, SourceAdapter]`

- [ ] **Step 1: Write contract tests for registry and source isolation**

Test that `build_source_registry()` always contains `huayapp`, `thai-government`, `savings-lottery`, `lao`, `hanoi`, `malaysia`, `thai-stocks`, and `foreign-stocks`; each spec has a non-empty ID/name/category; disabled sources are excluded from fetch selection but remain visible through status reporting.

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```powershell
py -3.11 -m pytest tests/test_sources.py -q
```

Expected: FAIL because the source package and registry do not exist.

- [ ] **Step 3: Implement the shared source types**

Use dataclasses and a `Protocol` in `base.py`. Restrict `SourceFetch.status` to `published`, `stale`, `failed`, and `unavailable`; keep adapter errors as data so one failure does not raise out of the whole refresh.

- [ ] **Step 4: Add configuration and registry resolution**

Extend `Config.from_env()` with `refresh_interval_seconds` defaulting to `60`, `source_request_timeout`, and comma-separated `ENABLED_LOTTERY_SOURCES`. Give each source an explicit environment URL such as `THAI_GOV_SOURCE_URL`, `LAO_SOURCE_URL`, `HANOI_SOURCE_URL`, `MALAYSIA_SOURCE_URL`, `THAI_STOCKS_SOURCE_URL`, and `FOREIGN_STOCKS_SOURCE_URL`; an empty URL produces an `unavailable` source rather than a fabricated result.

- [ ] **Step 5: Implement the configured public adapter boundary**

In `external.py`, define `ConfiguredPublicAdapter` that performs bounded GET requests through the existing `HttpClient`, passes HTML/JSON to a source parser, validates every result, and returns `SourceFetch`. Do not make browser automation or anti-bot bypass a fallback. Expose a parser hook so each source fixture can use its own selectors without changing storage/API code.

- [ ] **Step 6: Run the tests and type/syntax checks**

Run:

```powershell
py -3.11 -m pytest tests/test_sources.py -q
py -3.11 -m compileall huayapp_scraper
```

Expected: all source contract tests pass and compilation exits with code 0.

### Task 3: Make Huayapp discovery scrape every published card

**Files:**
- Create: `huayapp_scraper/sources/huayapp.py`
- Modify: `huayapp_scraper/scraper.py`
- Modify: `huayapp_scraper/cli.py`
- Test: `tests/test_scraper.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: existing `parse_cards()`, `BrowserScraper.scrape_card()`, and `SQLiteStore`
- Produces: `scrape_all(config: Config) -> tuple[list[LotteryResult], list[dict[str, str]]]` and CLI command `python main.py scrape-all --db <path>`

- [ ] **Step 1: Add a fixture-driven discovery test**

Mock `HttpClient.get()` with `tests/fixtures/thai_gov_latest.html`, mock `BrowserScraper.scrape_card()` to return a valid result for each published card, and assert `scrape_all()` attempts every published card while returning a per-card error for pending/unpublished cards.

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
py -3.11 -m pytest tests/test_scraper.py::test_scrape_all_discovers_every_published_card -q
```

Expected: FAIL because `scrape_all()` is not defined.

- [ ] **Step 3: Implement dynamic Huayapp discovery**

Fetch the index once, call `parse_cards()`, select cards with `status == "published"`, and process each ID. Catch `ScrapeError` per card, append an error record, and continue. Set `source_item_id` to the card lottery ID and `country` to `TH` without changing `build_result_from_card()` validation.

- [ ] **Step 4: Add CLI support**

Add `scrape-all` to `huayapp_scraper/cli.py`. It must upsert successful results, print one JSON line per result/error, return exit code 0 when at least one result was stored, and return 1 only when every attempted card failed.

- [ ] **Step 5: Run focused and existing scraper tests**

Run:

```powershell
py -3.11 -m pytest tests/test_scraper.py tests/test_cli.py -q
```

Expected: the new discovery test and all existing parser/CLI tests pass.

### Task 4: Implement source-specific normalization and refresh orchestration

**Files:**
- Create: `huayapp_scraper/refresh.py`
- Modify: `huayapp_scraper/sources/external.py`
- Modify: `huayapp_scraper/sources/registry.py`
- Create: `tests/fixtures/external/` fixture files for each source parser that is enabled
- Test: `tests/test_sources.py`
- Test: `tests/test_refresh.py`

**Interfaces:**
- Consumes: `SourceAdapter`, `SourceFetch`, `SQLiteStore`, and source URLs from `Config`
- Produces: `RefreshReport(results: int, source_states: list[dict[str, str]], errors: list[dict[str, str]])` and `refresh_all(config: Config, source_ids: list[str] | None = None) -> RefreshReport`

- [ ] **Step 1: Add sanitized fixture tests for normalized result shape**

For every source adapter that has a reachable public source, add a fixture and test that the parser emits `country`, `category`, `source_item_id`, ISO date, string numbers, and at least one prize. For a source with no validated public endpoint, add a test asserting `unavailable` with a non-empty reason and no fabricated result.

- [ ] **Step 2: Run adapter tests and verify missing implementations fail**

Run:

```powershell
py -3.11 -m pytest tests/test_sources.py -q
```

Expected: FAIL for any source listed in the registry without a fixture-backed parser.

- [ ] **Step 3: Implement the source parsers**

Implement only selectors/JSON paths evidenced by the fixture for each source. Normalize Thai/Buddhist dates through the existing validator utilities, keep all number values as strings, and map source-specific fields such as stock open/close into `metadata` while exposing result numbers through named prizes.

- [ ] **Step 4: Implement refresh isolation and persistence**

In `refresh.py`, iterate adapters independently, call each adapter with bounded retries, upsert valid results, and call `SQLiteStore.upsert_source_state()` on success, stale, failed, or unavailable. A failure from one adapter must be included in `RefreshReport.errors` and must not prevent later adapters from running.

- [ ] **Step 5: Add stale protection tests**

Use a fake adapter that first returns a published result and then raises a timeout. Assert that the second refresh keeps the published row, records `stale` and the error, and does not create a duplicate. Add a second fake adapter that succeeds in the same run to prove isolation.

- [ ] **Step 6: Run source and refresh tests**

Run:

```powershell
py -3.11 -m pytest tests/test_sources.py tests/test_refresh.py tests/test_storage.py -q
```

Expected: all fixture, normalization, idempotency, stale, and isolation tests pass.

### Task 5: Expose unified results, source health, and manual refresh through FastAPI

**Files:**
- Modify: `huayapp-api/app.py`
- Modify: `huayapp_scraper/refresh.py`
- Test: `tests/test_api_contract.py`

**Interfaces:**
- Consumes: `SQLiteStore.list_results()`, `SQLiteStore.list_source_states()`, and `refresh_all()`
- Produces:
  - `GET /api/lottery-results?source=&country=&category=&date=&limit=` → `{ "results": [...], "serverTime": "..." }`
  - `GET /api/lottery-sources` → `{ "sources": [...], "serverTime": "..." }`
  - `POST /api/lottery-refresh` body `{ "sources": ["..."] }` or `{}` → `{ "report": {...}, "serverTime": "..." }`

- [ ] **Step 1: Write API tests before endpoints**

Use FastAPI’s test client with monkeypatched store/refresh functions. Assert result filters are applied, `limit` is bounded to 500, source status includes the last error, and POST refresh forwards selected source IDs.

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```powershell
py -3.11 -m pytest tests/test_api_contract.py -q
```

Expected: FAIL with 404 for the new routes.

- [ ] **Step 3: Implement filtered results and source status endpoints**

Keep the existing API key/IP/domain guard on protected endpoints. Serialize dates/datetimes with ISO strings and return empty arrays, not errors, when filters match no rows. Reject invalid limits with FastAPI validation.

- [ ] **Step 4: Implement manual refresh and background scheduling**

Add a FastAPI lifespan task that waits for `refresh_interval_seconds`, runs `refresh_all()` in a worker thread so Playwright/HTTP work does not block the event loop, and cancels cleanly on shutdown. `POST /api/lottery-refresh` runs one immediate refresh in the same service and returns the report.

- [ ] **Step 5: Run API and existing backend tests**

Run:

```powershell
py -3.11 -m pytest tests/test_api_contract.py tests/test_storage.py tests/test_scraper.py -q
```

Expected: all API, storage, and scraper tests pass.

### Task 6: Keep Bun server snapshot and legacy routes compatible

**Files:**
- Modify: `server.ts`
- Create: `tests/server-contract.mjs`

**Interfaces:**
- Consumes: shared `lottery.db` normalized tables
- Produces: `GET /api/lottery-results`, `GET /api/lottery-sources`, and `GET /api/lottery-snapshot` with an additional `results`/`sources` payload while preserving `yiki`, `stocks`, and `huayapp`

- [ ] **Step 1: Add static route contract assertions**

Assert that `server.ts` contains the normalized result/source queries, preserves `/api/lottery-snapshot`, and still returns the legacy keys. Run the contract once before implementation to record the expected failure.

- [ ] **Step 2: Implement safe query helpers**

Add helpers for bounded `limit`, optional source/country/category/date filters, prize reconstruction, and source-state mapping. Use parameterized SQL values; only interpolate the already bounded numeric limit.

- [ ] **Step 3: Add routes without changing legacy behavior**

Return the new normalized arrays from dedicated routes. Extend snapshot with `results` and `sources` but keep the existing `yiki`, `stocks`, and `huayapp` shapes unchanged so current frontend code continues to work.

- [ ] **Step 4: Run Bun/Node contract checks**

Run:

```powershell
node tests/server-contract.mjs
```

Expected: `Server API contract: PASS`.

### Task 7: Add unified and split result tabs with refresh/status UI

**Files:**
- Modify: `index.html`
- Modify: `tests/huayapp-display-contract.mjs`

**Interfaces:**
- Consumes: `GET /api/lottery-results`, `GET /api/lottery-sources`, `POST /api/lottery-refresh`, and existing `Store.getConfig()`/`fetchIntervalSec`
- Produces: DOM IDs `lottery-results-panel`, `lottery-source-filter`, `lottery-country-filter`, `lottery-category-filter`, `lottery-date-filter`, `btn-lottery-refresh`, and `lottery-source-status`

- [ ] **Step 1: Extend the display contract tests**

Assert that the HTML contains the new tab, filter IDs, refresh button, source-status panel, fetch paths, and rendering of `source_url`; retain the existing Huayapp and stock assertions. Remove the old negative assertions that prohibited source/link rendering because the new design requires both.

- [ ] **Step 2: Run the display contract and verify it fails**

Run:

```powershell
node tests/huayapp-display-contract.mjs
```

Expected: FAIL because the unified tab and endpoint references are not present.

- [ ] **Step 3: Add the tab and filter controls**

Add a unified results section and four category subviews that share one data state. Use native `select`/date input controls and a refresh button; do not duplicate result rendering logic per category.

- [ ] **Step 4: Implement fetch, filter, and status state**

Add `lotteryResultsState`, `lotterySourcesState`, `fetchLotteryResults()`, `fetchLotterySources()`, `refreshLotteryResults()`, and `renderLotteryResults()`. Render number strings verbatim, show source/country/category/status/date, and create a safe anchor with `rel="noreferrer"` for `source_url`.

- [ ] **Step 5: Wire auto-refresh and manual refresh**

Reuse the existing `fetchTimer` and configured `fetchIntervalSec`, clamp the interval to at least 60 seconds for the unified feed, refresh only while the app is visible, and clear the timer on page lifecycle teardown. Manual refresh must show loading state and leave existing results visible until the response succeeds.

- [ ] **Step 6: Run UI contract and regression checks**

Run:

```powershell
node tests/huayapp-display-contract.mjs
node tests/vip-formulas-contract.mjs
```

Expected: both contracts pass and existing VIP/stock UI markers remain present.

### Task 8: Document configuration, run the full verification suite, and record limitations

**Files:**
- Modify: `README.md`
- Modify: `huayapp_scraper/README.md`
- Test: all existing `tests/` files and new contract tests

**Interfaces:**
- Consumes: final CLI/API/UI behavior from Tasks 1–7
- Produces: operator documentation for source URLs, environment variables, scheduler, API key/access controls, and unavailable-source behavior

- [ ] **Step 1: Document the supported commands and environment variables**

Document `scrape-all`, `refresh`, `GET /api/lottery-results`, `GET /api/lottery-sources`, `POST /api/lottery-refresh`, `REFRESH_INTERVAL_SECONDS`, enabled source list, each source URL variable, `DATABASE_PATH`, and the existing API access variables. State that source availability depends on public access and that stale values are retained when a source fails.

- [ ] **Step 2: Run the complete Python suite**

Run:

```powershell
py -3.11 -m pytest -q
```

Expected: exit code 0 with zero failures.

- [ ] **Step 3: Run all Node/Bun contract checks**

Run:

```powershell
node tests/huayapp-display-contract.mjs
node tests/vip-formulas-contract.mjs
node tests/server-contract.mjs
```

Expected: every command prints `PASS` and exits 0.

- [ ] **Step 4: Run a local API smoke check**

Start the configured FastAPI service and issue:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health
Invoke-WebRequest 'http://127.0.0.1:8000/api/lottery-results?limit=10' -Headers @{ 'X-API-Key' = $env:SCRAPE_API_KEY }
Invoke-WebRequest http://127.0.0.1:8000/api/lottery-sources -Headers @{ 'X-API-Key' = $env:SCRAPE_API_KEY }
```

Expected: health is 200, result/source endpoints return JSON arrays, and an unavailable source reports a reason rather than fabricated results.

- [ ] **Step 5: Review the final diff/status**

Run `git diff --check` only if a Git repository is present; otherwise inspect the changed file list and rerun the full suite. Report any source that remains unavailable explicitly instead of claiming all markets are live.

---

## Plan Self-Review

- Spec coverage: normalized schema and additive storage are Task 1; adapter registry and public-source policy are Task 2/4; dynamic Huayapp discovery is Task 3; source health/stale handling is Task 4/5; API is Task 5/6; unified/split UI and 60-second/manual refresh are Task 7; tests and documentation are Task 8.
- Completeness check: no unfinished markers or unbounded “handle later” steps are used; unavailable sources have an explicit testable outcome.
- Type consistency: all later tasks consume the `SourceSpec`, `SourceFetch`, `SourceAdapter`, `RefreshReport`, and endpoint shapes defined above.
- Scope: the plan keeps legacy yiki/stocks storage and screens intact and isolates external source changes behind adapters and a unified feed.
