# ระบบสูตรหวยยี่กี่ VIP — SPA + Firebase + Local Backend

Single Page Application (HTML/CSS/JS) สำหรับระบบคำนวณสูตรหวยยี่กี่/หวยหุ้น พร้อมระบบหลังบ้าน

## ไฟล์ในโปรเจกต์

| ไฟล์ | คำอธิบาย |
| --- | --- |
| `index.html` | SPA หลัก (109 KB) — ทำงานได้ทันทีแม้ไม่มี backend |
| `server.ts` | Bun server เบาๆ สำหรับ Lottery Snapshot API (optional) |
| `package.json` | Dependencies สำหรับ Bun server |
| `README.md` | ไฟล์นี้ |

## โหมดการทำงาน

1. **LocalStorage mode** (default) — เปิด `index.html` ได้เลย ไม่ต้องตั้งค่าอะไร
   - ข้อมูลอยู่ใน browser เครื่องนั้น
   - เหมาะสำหรับ dev / demo / ใช้คนเดียว
2. **Firebase mode** (cloud) — sync ข้อมูลข้ามเครื่อง/ผู้ใช้
   - ใช้ Firebase Firestore (free tier 1GB)
   - เปิดจากปุ่ม "ตั้งค่า Firebase" ในแถบบน
3. **Backend mode** (optional) — ใช้ร่วมกับ `server.ts` เพื่อดึงผลหวยสด
   - รองรับ Bun (แนะนำ) หรือ Node

---

## Quick Start (LocalStorage mode — ไม่ต้องตั้งอะไร)

1. เปิดไฟล์ `index.html` ใน browser
2. กรอกรหัส VIP: **`VIPDRJR`** เพื่อเข้าหน้าคำนวณ
3. กดปุ่ม "แอดมิน" → รหัสผ่าน **`mochi4422`** เพื่อเข้าแผงควบคุม

---

## เปิด Firebase Mode (แนะนำสำหรับ production)

มี 3 วิธีใส่ Firebase config — เรียงตามลำดับความง่าย:

### วิธี A: กรอกในไฟล์ HTML (แนะนำ — ง่ายสุด)

1. สร้าง Firebase Project (ดูขั้นตอนด้านล่าง)
2. เปิด `index.html` ใน text editor
3. หา `const HARDCODED_FIREBASE_CONFIG` แล้วกรอกค่า:
   ```js
   const HARDCODED_FIREBASE_CONFIG = {
     apiKey: "AIzaSy...",                    // ← กรอก
     authDomain: "your-app.firebaseapp.com", // ← กรอก
     projectId: "your-app",                 // ← กรอก
     storageBucket: "your-app.appspot.com", // optional
     messagingSenderId: "1234567890",       // optional
     appId: "1:1234:web:abcd",              // ← กรอก
   };
   ```
4. บันทึกไฟล์ แล้วเปิดเว็บ → pill ที่ header เปลี่ยนเป็น **🔥 FIREBASE** ทันที

**ข้อดี:** commit ลง git ได้ ทุกคนที่ clone repo ก็ใช้ Firebase เดียวกัน ไม่ต้องตั้งค่าใหม่

**ข้อเสีย:** ถ้าแชร์ repo สาธารณะ คนอื่นเห็น config (ใช้ Firestore rules แก้ได้)

### วิธี B: ผ่าน Setup Wizard ในเว็บ (เก็บ config ใน browser)

1. เปิด `index.html`
2. กดปุ่ม **"ตั้งค่า Firebase"** (ขวาบน)
3. กรอก apiKey, authDomain, projectId, appId
4. กด **"ทดสอบการเชื่อมต่อ"** → ถ้า ✅ ผ่าน กด **"บันทึกและเปิดใช้งาน"**
5. โหมดจะเปลี่ยนเป็น **🔥 FIREBASE** (เห็นที่ pill มุมขวาบน)

**ข้อดี:** ไม่ต้องแก้ไฟล์, เปลี่ยน config ได้ทันที

**ข้อเสีย:** config อยู่ใน localStorage ของ browser นั้นเครื่องเดียว

### ลำดับความสำคัญของ config

```
1. HARDCODED_FIREBASE_CONFIG ในไฟล์ (ชนะเสมอ)
2. localStorage (จาก Setup Wizard)
3. ไม่มี = ใช้ LocalStorage mode
```

---

## สร้าง Firebase Project (ทำก่อนใช้งาน)

### 1. สร้าง Firebase Project (ฟรี)

1. ไปที่ https://console.firebase.google.com/
2. กด "Add project" → ตั้งชื่อ → Continue
3. ปิด "Enable Google Analytics" (ไม่จำเป็น) → Create project
4. ในหน้า Project Overview → กดไอคอน **Web** (`</>`)
5. ตั้งชื่อ app → Register app
6. **คัดลอก config object** (apiKey, authDomain, projectId, appId, ฯลฯ)

### 2. สร้าง Firestore Database

1. เมนูซ้าย → **Firestore Database** → Create database
2. เลือก **Start in test mode** (สำหรับ dev — 30 วัน)
3. เลือก region (เช่น asia-southeast1) → Enable

### Firestore Collections (สร้างอัตโนมัติเมื่อมีการเขียน)

```
settings/global              → { vipCode, adminPassword, lineId, formulas, ... }
banners/...                  → (placeholder — สำหรับเก็บ URL แบนเนอร์)
yikiResults/{round}          → { round, time, top3, bot2 }
stocksResults/{symbol_date}  → { symbol, date, top3, bot2, open, close }
```

### Firestore Rules (ตั้งใน Firebase console)

สำหรับ dev ทดสอบ (อย่าใช้ใน production):
```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /{document=**} {
      allow read, write: if request.time < timestamp.date(date.add(request.time, days, 30));
    }
  }
}
```

สำหรับ production ใช้:
```
match /settings/{doc} { allow read, write: if false; }  // write only via admin SDK
match /yikiResults/{doc} { allow read: if true; allow write: if false; }
match /stocksResults/{doc} { allow read: if true; allow write: if false; }
```

---

## รัน Backend (Bun server — optional)

ใช้ `server.ts` เพื่อให้เว็บดึงผลหวยจาก API จริง (ผ่าน `/api/lottery-snapshot`)

### ติดตั้ง Bun (ถ้ายังไม่มี)

Bun มีอยู่ในเครื่องนี้แล้ว (v1.3.14) — ถ้ายังไม่มีติดตั้งจาก https://bun.sh

### รัน Server

```bash
cd "C:\Users\kittiphong.k\Documents\Default Project\big"
bun run server.ts
```

Server จะรันที่ `http://localhost:8787` และสร้างไฟล์ `lottery.db` (SQLite) อัตโนมัติ

ทดสอบ:
```bash
curl http://localhost:8787/api/lottery-snapshot
# { "yiki": [...], "stocks": [...], "serverTime": "..." }
```

### เชื่อมต่อ Frontend กับ Backend

ใน **Admin Panel → API ดึงผล** tab:
- **Yiki API URL**: `http://localhost:8787/api/lottery-snapshot` (ตอน dev)
- **Stocks API URL**: (เว้นว่างไว้ — ใช้ค่าเดียวกัน)

หรือแก้ใน `index.html` โดยตรง:
```js
yikiApiUrl: 'http://localhost:8787/api/lottery-snapshot',
```

> **หมายเหตุ:** ถ้า deploy บน server จริง ให้เปลี่ยน `localhost` เป็น domain ของคุณ

### Unified lottery feed (FastAPI ingestion service)

ระบบผลหวยทั้งหมดใช้ package ใน `huayapp_scraper` และ `huayapp-api/app.py` เป็น ingestion service หลัก โดยรองรับการค้นพบผลทุก card ของ Huayapp, source registry และผลจากแหล่ง public ที่ตั้งค่าไว้ แหล่งที่ไม่มี URL/parser ที่ยืนยันได้จะแสดงเป็น `unavailable` และไม่สร้างผลปลอม

คำสั่งดึงทุก card ของ Huayapp:

```powershell
python main.py scrape-all --db lottery.db
```

Environment variables ที่ใช้กับ source registry:

```text
REFRESH_INTERVAL_SECONDS=60
ENABLED_LOTTERY_SOURCES=huayapp,thai-government,lao,hanoi,malaysia,thai-stocks,foreign-stocks
THAI_GOV_SOURCE_URL=
SAVINGS_LOTTERY_SOURCE_URL=
LAO_SOURCE_URL=
HANOI_SOURCE_URL=
MALAYSIA_SOURCE_URL=
THAI_STOCKS_SOURCE_URL=
FOREIGN_STOCKS_SOURCE_URL=
DATABASE_PATH=lottery.db
```

API หลักของ ingestion service:

```text
GET  /api/lottery-results?source=&country=&category=&date=&limit=500
GET  /api/lottery-sources
POST /api/lottery-refresh       # body ว่าง หรือ {"sources":["lao"]}
```

ทุก endpoint ที่อยู่บน FastAPI ใช้ access policy เดียวกับ Huayapp API เดิม (`SCRAPE_API_KEY` และ `ALLOWED_IPS`/`ALLOWED_DOMAINS`) ส่วน browser ใช้ `huayApiUrl` และ `huayApiKey` ใน config เดิมเพื่ออ่าน feed

---

## API Response Format

`GET /api/lottery-snapshot` ต้อง return:

```json
{
  "yiki": [
    { "round": "882401", "time": "14:32:11", "top3": "582", "bot2": "47" },
    { "round": "882400", "time": "14:28:31", "top3": "193", "bot2": "06" }
  ],
  "stocks": [
    { "symbol": "SET", "date": "01/10", "top3": "582", "bot2": "47", "open": "1,432.50", "close": "1,438.20" }
  ],
  "serverTime": "2026-10-01T15:32:00.000Z"
}
```

Unified results response:

```json
{
  "results": [
    {
      "source": "lao",
      "source_item_id": "lao-2026-10-01",
      "lottery_name": "Lao Lottery",
      "country": "LA",
      "category": "regional",
      "result_date": "2026-10-01",
      "status": "published",
      "source_url": "https://example.test/results",
      "prizes": [{"prize_name": "1st Prize", "numbers": ["0123"]}]
    }
  ],
  "serverTime": "2026-10-11T00:00:00.000Z"
}
```

เมื่อ source ล่ม ระบบคงผล `published` เดิมไว้และเปลี่ยน source state เป็น `stale` พร้อม `last_error`; เมื่อยังไม่มี URL/parser จะเป็น `unavailable`

---

## ฟีเจอร์

### หน้าบ้าน (Frontend)
- ✅ Banner carousel 5 ภาพ (auto-slide 4.5s)
- ✅ 5 ปุ่มหลัก: LINE / หวย 1 / หวย 2 / ทักไลน์ / คัดลอก Line ID
- ✅ VIP Unlock (รหัส: `VIPDRJR`)
- ✅ 3 Tabs หลังปลดล็อก:
  - 🎯 **หวยยี่กี่ VIP** — กรอกเลข 5 ตัว, คำนวณ รูดบน/รูดล่าง/เจาะ 5
  - 📈 **คำนวณหวยหุ้น** — เลือกหุ้น 9 ตลาด, คำนวณ 5 ชุด
  - 📊 **ผลหวย & สถิติ** — ตารางย้อนหลัง 8 แถว
- ✅ Mobile responsive (2x2 grid + responsive)
- ✅ นาฬิกา/วันที่ realtime ไทย
- ✅ Auto-fetch ผลหวยทุก 60s (ตั้งได้)

### ระบบหลังบ้าน (Backend)
- ✅ 2 โหมด: LocalStorage (default) + Firebase Firestore
- ✅ Setup wizard สำหรับใส่ Firebase config
- ✅ เก็บ config (VIP code, admin password, line ID, formulas, API URLs) ใน cloud
- ✅ Auto-detect mode (LOCAL vs FIREBASE pill ที่ header)
- ✅ Admin Panel 5 tabs:
  1. แบนเนอร์
  2. 4 ปุ่มหน้าหลัก
  3. รหัส VIP & สูตร
  4. เปลี่ยนรหัสแอดมิน
  5. API ดึงผล
- ✅ Optional Bun server (SQLite) สำหรับดึงผลหวย

### Authentication
- VIP code: `VIPDRJR` (แก้ได้ในแผงควบคุม)
- Admin password: `mochi4422` (แก้ได้ในแผงควบคุม)
- ตรวจสอบฝั่ง client (สำหรับ LocalStorage mode) และฝั่ง Firestore (สำหรับ Firebase mode)

---

## โครงสร้างข้อมูล Firestore

### Collection: `settings/global`
```json
{
  "vipCodes": [
    { "id": "legacy-default", "code": "VIPDRJR", "expiry": "" }
  ],
  "vipCode": "VIPDRJR",
  "adminPassword": "mochi4422",
  "lineId": "@146zutdu",
  "bannerImages": ["", "", "", "", ""],
  "formulas": [12, 45, 78, 23, 56],
  "fetchIntervalSec": 60,
  "yikiApiUrl": "",
  "stocksApiUrl": ""
}
```

`vipCodes` รองรับรหัส VIP ได้ไม่จำกัดรายการ โดยแต่ละรายการกำหนด `expiry` เป็นวันที่รูปแบบ `YYYY-MM-DD` ได้ หากเว้นว่างจะไม่มีวันหมดอายุ ผู้ดูแลสามารถเพิ่ม แก้ไข และลบรหัสได้จาก Admin Panel ส่วน `vipCode` เดิมยังคงรองรับเพื่อให้ระบบ migrate ข้อมูลเก่าอัตโนมัติ

### Collection: `yikiResults/{round}`
```json
{
  "round": "882401",
  "time": "14:32:11",
  "top3": "582",
  "bot2": "47"
}
```

### Collection: `stocksResults/{symbol_date}`
```json
{
  "symbol": "SET",
  "date": "01/10",
  "top3": "582",
  "bot2": "47",
  "open": "1,432.50",
  "close": "1,438.20"
}
```

---

## Trade-offs

| โหมด | ข้อดี | ข้อเสีย |
| --- | --- | --- |
| **LocalStorage** | ไม่ต้อง setup, เปิดได้เลย, ไม่มี cloud cost | ข้อมูลอยู่เครื่องเดียว, ลบ browser = หายหมด |
| **Firebase** | Sync ข้ามเครื่อง, free tier 1GB, realtime | ต้องสร้างโปรเจกต์, มี quota (50K reads/day) |
| **Backend (Bun)** | ดึงผลหวยจาก API จริงได้, ควบคุม data เอง | ต้อง deploy server, ต้องดูแลเอง |

**แนะนำ:** เริ่มจาก LocalStorage เพื่อ dev/demo แล้วค่อยย้ายไป Firebase เมื่อพร้อม production

---

## เปิดไฟล์ index.html แบบ static

ใช้ web server ใดก็ได้ เช่น:

```bash
# Python
python -m http.server 8000

# Bun
bunx serve .

# Node
npx serve .
```

แล้วเปิด http://localhost:8000

**ไม่แนะนำ** เปิด `file://` ตรงๆ เพราะ Firebase Auth/Firestore บาง feature อาจมีปัญหากับ CORS — แต่ LocalStorage mode ใช้ได้ปกติ

---

## TODO (สำหรับ Production)

- [ ] เปลี่ยน VIP code / admin password จาก default
- [ ] ตั้ง Firestore rules ให้ปลอดภัย (ไม่เปิด public write)
- [ ] เปิด Firebase Auth + เปลี่ยน admin login เป็น email/password
- [ ] Deploy `index.html` บน Firebase Hosting หรือ Netlify (ฟรี)
- [ ] หา API หวยยี่กี่/หุ้นจริง (เช่นจาก leklai.com, set.or.th) → ใส่ในช่อง API URL
- [ ] ตั้ง HTTPS สำหรับ backend (Cloudflare, Railway, Fly.io)
