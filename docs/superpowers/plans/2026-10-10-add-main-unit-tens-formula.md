# Add 18 Additional Formulas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** เพิ่มสูตรใหม่ 18 รายการแยกจาก 21 สูตรเดิม ให้ใช้ร่วมกันผ่านชุดสูตรกลาง และจัด display ให้ตรงเว็บอ้างอิง

**Architecture:** เพิ่ม IDs 22-39 ใน `VIP_FORMULAS` ของ `index.html`. เพิ่ม `valuesFn` สำหรับสูตรหลายผลลัพธ์/ผลลัพธ์ไม่ต่อเนื่อง และให้ renderer เดิมของ Yiki กับ Stocks วนชุดสูตรกลางเดียวกัน

**Tech Stack:** HTML, inline JavaScript, Tailwind utility classes, Node/browser smoke checks

**Spec:** `docs/superpowers/specs/2026-10-10-add-main-unit-tens-formula-design.md`

## Global Constraints

- สูตรใหม่ 18 รายการต้องไม่แก้หรือลบสูตรเดิม
- ใช้ `H/T/U` และ `TB/UB` ตามสัญกรณ์ที่กำหนด
- สูตรทุกค่าต้อง normalize เป็นเลข 0-9
- ต้องทำงานทั้ง Yiki และ Stocks ผ่าน `VIP_FORMULAS`

## Review Focus

- สูตรหลายผลลัพธ์ต้องไม่ถูกแปลงเป็นเลขเรียงต่อกัน: ตรวจ `ดับเบิ้ลบวก`, `บวกคงที่`, `มังกรทอง`
- สูตรคูณเศรษฐีพันล้านต้องแยกเลขหลักหน่วยของจำนวนเต็มและทศนิยมตำแหน่งแรก
- สูตร `T10`/`TB10` ต้องใช้ค่าตัวเลขสองหลักถูกต้อง
- UI ต้องแยกจำนวนสูตรในระบบ 18 สูตรออกจากจำนวนสูตรที่เปิดแสดง 8 สูตร
- ประวัติ/คัดลอกต้องรวมสูตร IDs 22-39 ผ่านการวนชุดกลาง

### Task 1: Add the shared formulas and update counts

**Files:**
- Modify: `index.html` (formula helpers, `VIP_FORMULAS`, renderer group, and static counts)
- Test: `tests/vip-formulas-contract.mjs`

**Interfaces:**
- Consumes: existing `formula()`, `addDigits()`, `computeBalls()`, and shared `VIP_FORMULAS`
- Produces: formula IDs 22-39 and `valuesFn` support for multi-output formulas

- [x] **Step 1: Add assertions for the formula contract**

  Assert all 18 requested names, multi-output support, representative calculated values, and the 8 active display IDs.

- [x] **Step 2: Run the focused contract check and confirm it fails before implementation**

  Run `node tests/vip-formulas-contract.mjs`; expected failure because the new formulas and count are absent.

- [x] **Step 3: Add the formulas and multi-output engine**

  Add IDs 22-39 with the exact names and expressions from the supplied table. Extend `computeBalls()` to use `valuesFn` when present while preserving existing sequential formulas.

- [x] **Step 4: Update the renderer and all static formula counts**

  Add the reference formula groups to Yiki and show only the 8 active formulas while retaining all formula data.

- [x] **Step 5: Run focused, syntax, and full-suite checks**

  Run the focused contract test, inline JavaScript syntax check, existing display contract, and `PYTHONPATH=. pytest -q`. Expected: all targeted checks pass and the Python suite remains green.

- [x] **Step 6: Review the diff**

  Confirm existing formula entries and history/copy loops remain intact, with only the new shared formulas, renderer group, and count changes added.
