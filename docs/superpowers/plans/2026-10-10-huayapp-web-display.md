# Huayapp Web Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a separate Huayapp results panel to the existing Firebase-hosted page and fetch validated results from the deployed Railway API.

**Architecture:** Keep the existing yiki/stocks flows unchanged. Add a small browser client in `index.html` that calls `GET /api/huayapp-results`, sends the Railway client API key, stores the latest response in runtime state, and renders one card per lottery result with prize rows and error/loading states.

**Tech Stack:** Existing single-file HTML/JavaScript SPA, browser `fetch`, Firebase Hosting, Railway FastAPI API.

**Spec:** `docs/superpowers/specs/2026-10-10-huayapp-html-scraper-design.md`

## Global Constraints

- Use `https://api-huay-production.up.railway.app` as the API base URL.
- Preserve existing yiki/stocks behavior.
- Preserve lottery numbers as strings, including leading zeroes.
- Send `X-API-Key` only from runtime browser code; do not write the key to Git documentation or logs.
- Treat the browser key as a client key, not a secret.
- Render API failure and empty states without breaking the rest of the page.

### Task 1: Huayapp API client and configuration

**Files:**
- Modify: `index.html`

**Interfaces:**
- Add `DEFAULT_CONFIG.huayApiUrl` with the Railway results endpoint base.
- Add runtime `huayappResults` state.
- Add `fetchHuayappResults(config)` returning `{ ok: boolean, results: Array, error?: string }`.

- [ ] Add a dedicated Huayapp URL/key configuration without changing yiki/stocks fields.
- [ ] Fetch `GET ${huayApiUrl}/api/huayapp-results?limit=20` with `X-API-Key`.
- [ ] Keep response numbers as received strings and reject malformed non-array responses.

### Task 2: Huayapp results panel

**Files:**
- Modify: `index.html`

**Interfaces:**
- Add a standalone section with id `huayapp-results-panel`.
- Add renderer `renderHuayappResults(results, state)`.

- [ ] Render lottery name, category, result date/time, status, and all prize rows.
- [ ] Render loading, empty, and error states.
- [ ] Keep the panel visually separate from current yiki/stocks cards.

### Task 3: Verification

**Files:**
- Modify: `index.html`

- [ ] Run a JavaScript syntax check using Bun.
- [ ] Confirm the Railway endpoint responds with the configured key and allowed Origin.
- [ ] Confirm the page contains the new panel and Railway URL.
- [ ] Run the existing project checks that do not require a browser deployment.
