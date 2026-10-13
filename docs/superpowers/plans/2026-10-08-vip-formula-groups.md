# VIP Formula Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** จัดการ์ดสูตร VIP 8 ใบเป็น 3 หมวดตามภาพอ้างอิง โดยไม่เปลี่ยน logic การคำนวณ

**Architecture:** เก็บ `VIP_FORMULAS` เป็นแหล่งข้อมูลการคำนวณเดิม แล้วเพิ่ม metadata สำหรับชื่อแสดง/กลุ่ม/ลำดับ. `renderVipCards` จะสร้าง wrapper ของแต่ละกลุ่มและแทรกการ์ดเข้า wrapper; card event และ data attributes เดิมยังคงใช้ร่วมกับ copy/filter-independent actions.

**Tech Stack:** HTML, Tailwind CDN classes, vanilla JavaScript ES module

**Spec:** `docs/superpowers/specs/2026-10-08-vip-formula-groups-design.md`

## Global Constraints

- สูตรคำนวณ `digitFn`, `ballCount`, `startOffset`, `pills` ต้องไม่เปลี่ยน
- ใช้ mapping ID 2/3, 5/6, 9/13/15/18 ตาม spec
- แสดง 8 สูตรครบในสามหมวดหลังคำนวณ
- ลบ filter UI เดิมและไม่สร้าง filter state ใหม่
- รองรับ mobile เป็นหนึ่งคอลัมน์ และคงปุ่มคัดลอก/บันทึก/ประวัติ

## File Map

- Modify: `index.html:426-451` — filter controls and formula container markup
- Modify: `index.html:1065-1105` — formula metadata only if needed for display labels
- Modify: `index.html:1212-1223` — remove obsolete filter listeners
- Modify: `index.html:1534-1645` — grouped rendering and card labels
- Create: `docs/superpowers/specs/2026-10-08-vip-formula-groups-design.md`
- Create: `docs/superpowers/plans/2026-10-08-vip-formula-groups.md`

### Task 1: Define display grouping and remove obsolete filter UI

**Files:**
- Modify: `index.html` formula filter markup and `VIP_FORMULAS` metadata

- [ ] **Step 1: Write the failing static assertion**

Run a Node check that extracts `VIP_FORMULAS` source and asserts the source does not yet contain the required display group metadata. Expected: FAIL before implementation.

- [ ] **Step 2: Add explicit metadata**

Add `displayGroup`, `displayLabel`, and `displayOrder` to the eight entries without changing calculation properties:

```js
{ id: 2, displayGroup: 'รูด19ประตู', displayLabel: 'สูตร 1', displayOrder: 1 }
{ id: 3, displayGroup: 'รูด19ประตู', displayLabel: 'สูตร 2', displayOrder: 2 }
{ id: 5, displayGroup: 'พิกัด', displayLabel: 'พิกัดบน', displayOrder: 1 }
{ id: 6, displayGroup: 'พิกัด', displayLabel: 'พิกัดล่าง', displayOrder: 2 }
{ id: 9, displayGroup: 'ปัก', displayLabel: 'ปักสิบบน', displayOrder: 1 }
{ id: 13, displayGroup: 'ปัก', displayLabel: 'ปักสิบล่าง', displayOrder: 2 }
{ id: 15, displayGroup: 'ปัก', displayLabel: 'ปักหน่วยบน', displayOrder: 3 }
{ id: 18, displayGroup: 'ปัก', displayLabel: 'ปักหน่วยล่าง', displayOrder: 4 }
```

- [ ] **Step 3: Replace old filter controls**

Remove the `data-vip-filter` buttons and leave the history/save/copy actions. Change the result container to a single-column responsive stack, keeping `id="vipFormulaCarousel"`.

- [ ] **Step 4: Run static assertion again**

Assert all eight IDs have the exact group/label mapping and no `data-vip-filter` remains in the VIP section. Expected: PASS.

### Task 2: Render grouped formula cards

**Files:**
- Modify: `index.html` `initVipCarousel`, `applyVipFilter`, and `renderVipCards`

- [ ] **Step 1: Write the failing rendering assertion**

Use a browser smoke test after entering sample values and clicking calculate. Assert the DOM has group headings `สูตรรูด 19 ประตู`, `สูตรพิกัด`, `สูตรปัก`, and cards in ID order `[2,3,5,6,9,13,15,18]`. Expected: FAIL before grouped renderer exists.

- [ ] **Step 2: Remove obsolete filter listener and function**

Delete the `data-vip-filter` listener from `initVipCarousel`. Remove or make `applyVipFilter` unused; no new filter state is needed.

- [ ] **Step 3: Build group containers in `renderVipCards`**

Create three group wrappers in the required order, each with a heading and a `data-formula-group` attribute. Append each formula card into the wrapper selected by `f.displayGroup`. Keep card `data-formula-id`, copy button selector, click selection, and existing balls/pills HTML intact.

- [ ] **Step 4: Use display labels in card headers and copy text**

Render `f.displayLabel` in the visible header while preserving formula ID in `data-formula-id`. Update copied text to include the display label and original ID only when useful; do not change copied numbers.

- [ ] **Step 5: Run browser rendering assertion**

Start a local server, unlock with the existing VIP code, fill sample result `top3=123`, `bot2=45`, click calculate, and verify:

```js
group headings === ['สูตรรูด 19 ประตู', 'สูตรพิกัด', 'สูตรปัก']
formula ids === ['2','3','5','6','9','13','15','18']
card count === 8
```

Expected: PASS.

### Task 3: Regression verification

**Files:**
- Verify: `index.html`
- Modify: none unless a regression is found

- [ ] **Step 1: Verify calculation values are unchanged**

For `top3=123`, `bot2=45`, compare balls from each ID against the existing `digitFn` output; expected values remain ID 2 `6,7,8,9,0,1`, ID 3 `7,8,9,0,1,2`, ID 5 `8,9,0,1,2,3`, ID 6 `5,6,7,8,9,0`, ID 9 `9,0,1`, ID 13 `9,0,1`, ID 15 `6,7,8,9,0,1`, ID 18 `2,3,4,5,6,7`.

- [ ] **Step 2: Verify copy and surrounding actions**

Click a card copy button and confirm clipboard text still contains the card numbers; verify `บันทึกผล`, `ประวัติการคำนวณ`, and `คัดลอกสูตรสำเร็จรูป` remain present.

- [ ] **Step 3: Run syntax check and whitespace check**

Run the existing Node module parse command. Run `git diff --check` when Git is available; otherwise inspect changed regions because this workspace has no Git repository.
