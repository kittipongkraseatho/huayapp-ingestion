# VIP Code CRUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** เปลี่ยนระบบรหัส VIP ให้รองรับรายการรหัสไม่จำกัดพร้อมวันหมดอายุแยกกัน โดยไม่เปลี่ยนสูตรคำนวณ

**Architecture:** ใช้ฟิลด์ `vipCodes` เป็น array ใน config ที่ผ่าน Store เดิมทั้ง LocalStorage และ Firebase. เพิ่ม normalization/migration layer ให้ข้อมูลเก่า `vipCode` ทำงานต่อได้ และให้หน้า login ตรวจรายการที่ normalize แล้ว. หน้า Admin ใช้ CRUD handlers เขียนกลับ `vipCodes` ทันทีผ่าน Store

**Tech Stack:** HTML, Tailwind CDN classes, vanilla JavaScript ES module, LocalStorage, Firebase Firestore ผ่าน adapter เดิม

**Spec:** `docs/superpowers/specs/2026-10-08-vip-code-crud-design.md`

## Global Constraints

- ทำเฉพาะระบบรหัส VIP; ห้ามเปลี่ยน logic หรือค่าของสูตรคำนวณ
- รองรับทั้ง LocalStorage และ Firebase ผ่าน `Store`
- `expiry` ใช้รูปแบบ `YYYY-MM-DD`; เว้นว่างหมายถึงไม่หมดอายุ
- เปรียบเทียบรหัสแบบ trim + uppercase และห้ามรหัสซ้ำแบบ case-insensitive
- ต้องรักษาความเข้ากันได้กับ config เก่าแบบ `vipCode`
- แก้ไฟล์เดิมตาม pattern ของโปรเจกต์; ไม่เพิ่ม dependency ใหม่

## File Map

- Create: `docs/superpowers/specs/2026-10-08-vip-code-crud-design.md` — ข้อกำหนดที่อนุมัติแล้ว
- Create: `docs/superpowers/plans/2026-10-08-vip-code-crud.md` — แผน implementation นี้
- Modify: `index.html:608-640` — default config และ helper normalize/migration
- Modify: `index.html:1006-1055` — ตรวจรหัส VIP หลายรายการและวันหมดอายุ
- Modify: `index.html:1940-2040` — UI CRUD ใน Admin panel
- Modify: `index.html:2020-2350` — populate, handlers, persistence และข้อความ validation
- Verify: `index.html` ผ่าน browser smoke test และ static syntax check

### Task 1: เพิ่ม model และ migration ของรายการรหัส

**Files:**
- Modify: `index.html` ส่วน `DEFAULT_CONFIG`, `refreshConfig()` และ logic config ที่เกี่ยวข้อง

**Interfaces:**
- ผลิต `normalizeVipCodes(config)` คืนค่า `Array<{id: string, code: string, expiry: string}>`
- ผลิต `isVipCodeExpired(entry, now = new Date())` คืนค่า boolean
- ผลิต `findValidVipCode(rawCode, entries, now = new Date())` คืนค่า `{ entry, reason }` โดย `reason` เป็น `valid`, `invalid` หรือ `expired`

- [ ] **Step 1: เพิ่ม test cases แบบ executable ใน browser console checklist**

ตรวจกรณีต่อไปนี้หลัง expose helper ผ่าน `window.__vipCodeTestApi` ชั่วคราวใน dev build:

```js
const api = window.__vipCodeTestApi;
console.assert(api.normalize([{ code: ' vipdrjr ', expiry: '' }])[0].code === 'VIPDRJR');
console.assert(api.find('VIPDRJR', [{ id: '1', code: 'VIPDRJR', expiry: '' }]).reason === 'valid');
console.assert(api.find('VIPDRJR', [{ id: '1', code: 'VIPDRJR', expiry: '2000-01-01' }]).reason === 'expired');
console.assert(api.normalize({ vipCode: 'VIPDRJR' }).length === 1);
```

- [ ] **Step 2: รัน browser smoke test ก่อน implementation**

เปิด `index.html`, เปิด DevTools console และตรวจว่าข้อความ `window.__vipCodeTestApi is undefined` ปรากฏ เพราะ helper ยังไม่ถูกเพิ่ม

- [ ] **Step 3: เพิ่ม default `vipCodes` และ helper functions**

ใช้ค่าเริ่มต้นแบบนี้และไม่ลบ `vipCode` เดิม:

```js
vipCode: 'VIPDRJR',
vipCodes: [{ id: 'legacy-default', code: 'VIPDRJR', expiry: '' }],
```

`normalizeVipCodes` ต้องรับทั้ง array ของ entries และ config object; ถ้าไม่มี array ให้สร้าง entry จาก `vipCode`; ถ้ายังไม่มีทั้งสองให้ใช้ `VIPDRJR`. สร้าง id ด้วย `crypto.randomUUID()` เมื่อทำได้ และ fallback เป็น `vip-${Date.now()}-${index}`. ลบรายการว่างและ deduplicate ด้วย uppercase code.

`isVipCodeExpired` ให้คืน false เมื่อ expiry ว่าง และใช้ `new Date(`${expiry}T23:59:59`)` ตรวจวันสิ้นสุดในเวลาท้องถิ่น

`findValidVipCode` ต้อง trim/uppercase input, คืน `invalid` เมื่อไม่พบ, `expired` เมื่อพบแต่หมดอายุ และ `valid` เมื่อพบรายการที่ยังใช้ได้

- [ ] **Step 4: expose helper สำหรับ smoke test และรัน test cases**

เพิ่ม `window.__vipCodeTestApi = { normalize: normalizeVipCodes, find: (raw, entries, now) => findValidVipCode(raw, entries, now) }` แล้ว reload หน้าและรัน assertions จาก Step 1; คาดหวังไม่เกิด assertion error

- [ ] **Step 5: ตรวจ migration ไม่เปลี่ยนสูตร**

ตั้งค่า `localStorage.lotto_default_config` ให้มี `{ vipCode: 'OLD01', formulas: [12,45,78,23,56] }`, reload และตรวจว่า normalize ได้ `OLD01` และ `formulas` ยังเท่าเดิม

### Task 2: เปลี่ยนการปลดล็อกให้ตรวจรหัสหลายรายการ

**Files:**
- Modify: `index.html` ส่วน `unlockForm` submit handler และข้อความ error ใกล้ `AUTH: VIP UNLOCK`

**Interfaces:**
- Consumes: `currentConfig.vipCodes`, `normalizeVipCodes`, `findValidVipCode`
- Produces: unlock behavior ที่รับรหัสใดก็ได้ในรายการและ reject expired code

- [ ] **Step 1: เขียน failing smoke scenarios**

ใช้ Admin CRUD หรือ LocalStorage ตั้งรายการ `ACTIVE01` (ว่าง), `FUTURE01` (วันอนาคต), `EXPIRED01` (วันในอดีต) แล้วตรวจว่าก่อนแก้ handler ยังรับเฉพาะ `currentConfig.vipCode`

- [ ] **Step 2: เปลี่ยน submit handler เป็น list lookup**

แทนการเทียบ `v===currentConfig.vipCode.toUpperCase()` ด้วย `findValidVipCode(v, currentConfig.vipCodes)`; valid เรียก `unlock()`, expired แสดง `รหัส VIP หมดอายุแล้ว (วันที่ ...)`, invalid แสดง `รหัส VIP ไม่ถูกต้อง`

- [ ] **Step 3: refresh config ให้มี normalized list**

หลัง `Store.getConfig()` ให้กำหนด `currentConfig.vipCodes = normalizeVipCodes(currentConfig)` และคง `currentConfig.vipCode` เป็นค่า legacy แรกเพื่อให้ code อื่นที่อ่านอยู่ไม่พัง

- [ ] **Step 4: รัน smoke test auth**

ตรวจ active, future, expired, invalid อย่างละหนึ่งครั้ง; คาดหวัง active/future เข้า `mainView`, expired/invalid คงอยู่หน้า unlock และแสดงข้อความที่ตรงกรณี

### Task 3: เพิ่ม UI CRUD ใน Admin panel

**Files:**
- Modify: `index.html` ส่วน `data-panel="codes"`, populate และ handlers ใน `openAdminPanel()`

**Interfaces:**
- Consumes: `currentConfig.vipCodes`, `Store.getConfig()`, `Store.setConfig()`
- Produces: controls `admin-vip-code`, `admin-vip-expiry`, `btn-vip-add`, `admin-vip-list`, `btn-vip-cancel`

- [ ] **Step 1: เพิ่ม form และ list markup**

แทนช่อง `admin-vip-code` เดี่ยวด้วยกลุ่มฟอร์มที่มี input รหัส, input date, ปุ่ม `+ เพิ่มรหัส`, ปุ่ม `ยกเลิกแก้ไข` ที่ซ่อนอยู่ และ list container แสดง code, expiry/status, edit/delete

- [ ] **Step 2: เพิ่ม render function**

สร้าง `renderVipCodeList()` ที่อ่าน `currentConfig.vipCodes`, แสดง empty state ได้ และสร้างปุ่มด้วย `data-edit-vip`/`data-delete-vip`; ห้ามใช้ `innerHTML` กับค่ารหัสโดยตรงโดยไม่ escape ให้ใช้ `textContent` หรือ helper escape HTML

- [ ] **Step 3: เพิ่ม validation และ create/update handlers**

เพิ่ม `validateVipCodeForm()` ตรวจ trim non-empty, expiry parse ได้ และ duplicate เมื่อไม่ใช่รายการเดิม. Create สร้าง id ใหม่และ append; update แทน entry ตาม id. บันทึกทันทีด้วย `Store.setConfig({ vipCodes: next, vipCode: next[0]?.code || '' })`, อัปเดต `currentConfig`, reset form และ rerender

- [ ] **Step 4: เพิ่ม edit/delete/cancel handlers**

Edit เติมค่าเข้า form และเก็บ `editingVipId`; delete ใช้ `confirm`, filter id, บันทึกทันที และถ้าลบหมดให้ login ไม่ผ่านจนกว่าจะเพิ่มใหม่. Cancel ล้าง editing state และค่า form

- [ ] **Step 5: ปรับปุ่มบันทึกหลักไม่ให้เขียนทับ CRUD**

ใน `btn-save-admin` อ่านวันหมดอายุได้ตามเดิม แต่ไม่ใช้ `admin-vip-code` เป็น `vipCode` หลัก; บันทึกเฉพาะค่าตั้งค่าอื่นและ `formulas`. ถ้าต้องรักษา legacy ให้ set `vipCode` เป็น code แรกจาก `currentConfig.vipCodes` เท่านั้น

- [ ] **Step 6: รัน smoke test CRUD**

ตรวจเพิ่ม active, เพิ่ม future, เพิ่ม duplicate, แก้ code/expiry, ลบ code, reload หน้า และตรวจข้อมูลยังอยู่ทั้งใน LocalStorage mode และใน Firebase mode ถ้า config Firebase พร้อม

### Task 4: ตรวจความถูกต้องและเอกสาร

**Files:**
- Modify: `README.md` โครงสร้าง config และคำอธิบาย authentication
- Verify: `index.html`, browser console, LocalStorage data

- [ ] **Step 1: อัปเดต README schema**

เปลี่ยนตัวอย่าง `vipCode` เดี่ยวเป็น `vipCodes` array พร้อมระบุ `expiry` ว่างได้ และบอกว่า `vipCode` เดิมยังรองรับเพื่อ migration

- [ ] **Step 2: ตรวจ syntax ของ module**

เปิด `index.html` ผ่าน local server และตรวจ DevTools console ว่าไม่มี `SyntaxError`, `ReferenceError` หรือ unhandled promise rejection

- [ ] **Step 3: ตรวจสูตรคำนวณไม่เปลี่ยน**

คำนวณผลหนึ่งรายการก่อนและหลัง CRUD ด้วย input เดิม แล้วตรวจจำนวน/ค่าผลลัพธ์เท่ากัน รวมถึง `formulas` ใน config ไม่เปลี่ยน

- [ ] **Step 4: ตรวจไฟล์ที่เปลี่ยน**

รัน `git diff --check` ถ้า workspace มี git; ถ้าไม่มี git ให้ใช้ `rg` ตรวจ id ที่เพิ่มทั้งหมดและทบทวน diff ผ่าน `Get-Content`/comparison แทน

