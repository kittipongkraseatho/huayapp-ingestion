# Huayapp Ingestion Cost Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce unnecessary Chromium, OCR, and polling work while preserving result correctness and existing API payloads.

**Architecture:** Keep the existing FastAPI lifespan refresh loop, but make each refresh reuse one loaded page instead of navigating once per lottery card. Track store ownership explicitly so internally-created stores close reliably. Increase the default refresh interval to 1800 seconds and frontend polling to 300 seconds.

**Tech Stack:** Python 3.11, FastAPI, Playwright sync API, pytest, vanilla JavaScript, Railway TOML configuration.

**Spec:** `docs/superpowers/specs/2026-10-19-cost-optimization-design.md`

## Global Constraints

- Preserve existing API response shapes and lottery-result correctness.
- The accepted freshness target is a maximum refresh interval of approximately 30 minutes.
- Do not move deployment to Railway Cron, change database providers, or alter authentication in this pass.
- Existing unrelated working-tree changes must be preserved.

---

### Task 1: Refresh interval configuration

**Files:**
- Modify: `huayapp_scraper/config.py:41,70`
- Modify: `huayapp-api/app.py:25-36`
- Modify: `railway.toml:18,42`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `Config.from_env()` and `REFRESH_INTERVAL_SECONDS`.
- Produces: `Config.refresh_interval_seconds == 1800` by default; an explicit environment value remains clamped to at least 60 seconds.

- [ ] **Step 1: Write the failing test**

Add these tests to `tests/test_config.py`:

```python
def test_default_refresh_interval_is_thirty_minutes():
    assert Config().refresh_interval_seconds == 1800


def test_from_env_overrides_refresh_interval(monkeypatch):
    monkeypatch.setenv("REFRESH_INTERVAL_SECONDS", "2700")
    assert Config.from_env().refresh_interval_seconds == 2700
```

- [ ] **Step 2: Run the focused tests and verify the default test fails**

Run: `pytest tests/test_config.py::test_default_refresh_interval_is_thirty_minutes tests/test_config.py::test_from_env_overrides_refresh_interval -v`

Expected: the default test fails because the current default is 900 seconds; the override test passes.

- [ ] **Step 3: Implement the minimal configuration change**

Change `Config.refresh_interval_seconds` from `900` to `1800`. Update the adjacent comments in `config.py` and `app.py` to say the production default is 1800 seconds. Change the Railway documentation and `[env]` default from `900` to `1800`. Do not change the minimum clamp of 60 seconds or the environment variable name.

- [ ] **Step 4: Run the focused tests**

Run: `pytest tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the task**

```bash
git add tests/test_config.py huayapp_scraper/config.py huayapp-api/app.py railway.toml
git commit -m "perf: reduce default refresh frequency"
```

### Task 2: Reuse one browser page per refresh

**Files:**
- Modify: `huayapp_scraper/refresh.py:181-295`
- Test: `tests/test_refresh.py`

**Interfaces:**
- Consumes: `refresh_all_cards(config, store=None, page=None, progress_callback=None)`.
- Produces: one source-page navigation per refresh, per-card success/failure reporting, and persistence through the existing `Store` protocol.

- [ ] **Step 1: Add a fake-page seam and write the failing test**

In `tests/test_refresh.py`, import `refresh_all_cards` and add a small fake page whose `goto`, `wait_for_selector`, `wait_for_timeout`, `content`, and `locator` methods can be instrumented. Patch the module-level `parse_cards`, `CanvasGlyphDecoder`, and `_decode_value` so the test uses two published fixture cards without launching Playwright. Assert that `page.goto_calls == 1`, `page.wait_calls == 1`, and both results are persisted. Add a second test with a caller-owned fake store and assert `store.close_calls == 0` after the function returns.

The test must observe public behavior through `refresh_all_cards`: it should not inspect private browser handles or call `_iter` directly.

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `pytest tests/test_refresh.py -k "one_page or caller_owned_store" -v`

Expected: FAIL because the current implementation calls `goto` and the two-second wait once per published card, and store ownership is not tracked correctly.

- [ ] **Step 3: Implement one navigation and explicit store ownership**

At the start of `refresh_all_cards`, store `provided_store = store is not None`, then open a store only when `store is None`. Wrap the complete discovery/browser/persistence flow in `try/finally` and close the store only when `provided_store` is false.

Inside the browser iteration, move these operations before the card loop:

```python
ctx_page.goto(
    config.source_url,
    wait_until="domcontentloaded",
    timeout=int(config.request_timeout * 1000),
)
ctx_page.wait_for_selector(
    ".lotto-card",
    state="visible",
    timeout=int(config.request_timeout * 1000),
)
ctx_page.wait_for_timeout(2000)
page_now = parse_cards(ctx_page.content(), config.source_url)
cards_now = {card.lottery_id: card for card in page_now}
```

Then iterate `published` and select `card_now = cards_now.get(lottery_id)`. Keep the existing per-card locator, decode, validation, upsert, progress callback, and failure handling. Remove the per-card `goto`, `wait_for_selector`, `wait_for_timeout`, and repeated `parse_cards` calls. If the source page uses a different stable card selector than `.lotto-card`, use the existing `#lotto-card-{lottery_id}` selector for one known published card before the loop and retain the per-card lookup as the readiness check without navigation.

- [ ] **Step 4: Run the focused tests**

Run: `pytest tests/test_refresh.py -k "one_page or caller_owned_store" -v`

Expected: PASS, with exactly one navigation and no close call on the caller-owned store.

- [ ] **Step 5: Run the full Python test suite**

Run: `pytest -q`

Expected: PASS.

- [ ] **Step 6: Commit the task**

```bash
git add tests/test_refresh.py huayapp_scraper/refresh.py
git commit -m "perf: reuse browser page during refresh"
```

### Task 3: Reduce frontend polling without changing API contracts

**Files:**
- Modify: `index.html:684,3091`
- Test: `tests/huayapp-display-contract.mjs`

**Interfaces:**
- Consumes: existing `fetchRemoteData()` and `Store` configuration.
- Produces: default polling interval of 300 seconds; manual refresh buttons and endpoint URLs remain unchanged.

- [ ] **Step 1: Write the failing contract assertion**

Add this assertion to `tests/huayapp-display-contract.mjs`:

```javascript
assert.match(html, /fetchIntervalSec:\s*300/, 'remote polling defaults to five minutes');
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run: `bun test tests/huayapp-display-contract.mjs`

Expected: FAIL because the current default is 60 seconds.

- [ ] **Step 3: Implement the minimal polling change**

Change `fetchIntervalSec: 60` to `fetchIntervalSec: 300`. Keep the existing admin minimum of 60 seconds so an explicit operator setting remains supported. Do not remove or rename any API endpoint calls.

- [ ] **Step 4: Run the contract test**

Run: `bun test tests/huayapp-display-contract.mjs`

Expected: PASS.

- [ ] **Step 5: Commit the task**

```bash
git add index.html tests/huayapp-display-contract.mjs
git commit -m "perf: slow default frontend polling"
```

### Task 4: Final verification and diff review

**Files:**
- Inspect: `huayapp_scraper/refresh.py`
- Inspect: `huayapp_scraper/config.py`
- Inspect: `huayapp-api/app.py`
- Inspect: `railway.toml`
- Inspect: `index.html`

- [ ] **Step 1: Run all available automated checks**

Run:

```bash
pytest -q
bun test tests/huayapp-display-contract.mjs
bun test tests/server-contract.mjs
```

Expected: all commands exit 0.

- [ ] **Step 2: Review the final diff**

Run: `git diff HEAD~3..HEAD --stat; git status --short`

Confirm that only the intended commits are included and the pre-existing modifications to `index.html`, `tests/huayapp-display-contract.mjs`, and `pr-body.md` were not overwritten or accidentally staged outside their intended task changes.

- [ ] **Step 3: Report verification and remaining operational action**

Report the test commands and results, then tell the operator to set Railway's explicit `REFRESH_INTERVAL_SECONDS=1800` if the service already has an older environment override. No deployment or secret rotation is performed by this plan.
