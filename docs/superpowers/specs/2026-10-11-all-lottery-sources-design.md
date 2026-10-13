# All Lottery Sources Integration Design

วันที่: 2026-10-11

## เป้าหมาย

ขยายระบบให้ดึงผลหวยทุกประเภทที่ตรวจพบจาก Huayapp และเพิ่มแหล่งข้อมูลภายนอก ได้แก่ หวยรัฐบาลไทย หวยออมสิน/ธ.ก.ส. หวยลาว หวยฮานอย หวยมาเลย์ หุ้นไทย และหุ้นต่างประเทศ โดยใช้โครงสร้างข้อมูลกลาง แสดงผลทั้งแบบรวมและแบบแยกประเภท และรองรับการรีเฟรชอัตโนมัติทุก 60 วินาทีพร้อมปุ่มรีเฟรชทันที

## ขอบเขต

### รวมในงาน

- ค้นพบและดึงการ์ดผลทั้งหมดของ Huayapp แบบ dynamic ไม่จำกัดเฉพาะ lottery ID เดิม
- เพิ่ม source adapter/registry สำหรับแหล่งภายนอกตามกลุ่มที่ระบุ
- แปลงผลทั้งหมดเป็น normalized result และเก็บใน SQLite แบบ idempotent
- เพิ่ม API รวมผล, สถานะแหล่งข้อมูล และคำสั่ง refresh
- เพิ่มแท็บผลหวยทั้งหมดและแท็บแยกหวยไทย/ต่างประเทศ/หวยหุ้น/Huayapp
- แสดงสถานะสด กำลังดึง ข้อมูลเก่า และดึงไม่สำเร็จ รวมถึงเวลาอัปเดตและ URL ต้นทาง
- คงความเข้ากันได้กับผลยี่กี่และหุ้นเดิม
- ใช้เฉพาะข้อมูลสาธารณะที่อนุญาต ไม่หลบ CAPTCHA, authentication หรือ access control

### ไม่รวมในงาน

- การรับประกันว่าทุกตลาดมี API หรือแหล่งข้อมูลที่เสถียร
- การ bypass กลไกป้องกันบอตหรือเงื่อนไขการใช้งานของเว็บ
- การลบหรือ migrate ตาราง legacy `yiki_results` และ `stocks_results`
- การเพิ่มระบบสมาชิกหรือสิทธิ์ใหม่

## สถาปัตยกรรม

```text
Scheduler / ปุ่มรีเฟรช
        ↓
Source Registry
        ↓
Adapter ของแต่ละแหล่ง
        ↓
Normalize + Validate
        ↓
SQLite upsert + history
        ↓
API รวม
        ↓
แท็บรวม / แท็บแยกประเภท
```

แต่ละ adapter รับ source configuration และคืนผลลัพธ์รูปแบบเดียวกัน แหล่งหนึ่งล่มต้องไม่ทำให้แหล่งอื่นหยุดทำงาน ระบบจะเก็บ error ล่าสุดและคงผล published ล่าสุดไว้เมื่อการดึงรอบใหม่ไม่สำเร็จ

## รูปแบบข้อมูลกลาง

ผลลัพธ์กลางต้องรองรับฟิลด์ต่อไปนี้:

- `source`
- `source_item_id`
- `name`
- `country`
- `category`
- `draw_date`
- `draw_time`
- `round`
- `prizes` เป็นชื่อรางวัลและรายการเลขแบบ string เพื่อรักษาเลขศูนย์นำหน้า
- `status`: `published`, `pending`, `suspended`, `stale`, `failed`
- `source_url`
- `fetched_at`

การ deduplicate ใช้ source, source item, วันที่ออกรางวัล และรอบเป็นหลัก ผลที่ผ่านการยืนยันแล้วห้ามถูกแทนที่ด้วยผลที่ไม่ครบถ้วน

## แหล่งข้อมูลและการค้นพบ

- Huayapp ใช้หน้า public และค้นหา `.lotto-card[data-lotto-id]` ทั้งหมดจากหน้า index แล้วดึงเฉพาะ card ที่มีผลยืนยัน
- แหล่งภายนอกลงทะเบียนเป็น adapter แยกกัน เพื่อให้เปลี่ยน URL/parser ได้โดยไม่กระทบ storage และ UI
- ถ้าแหล่งใดไม่มี public endpoint/HTML ที่ใช้งานได้ ให้เก็บสถานะ unavailable พร้อมเหตุผลแทนการเดาข้อมูล
- ทุก source ต้องมี timeout, retry แบบ backoff, rate limit และ validation ของวันที่/จำนวนเลข/รูปแบบเลข

## API และ UI

เพิ่ม API:

- `GET /api/lottery-results` รองรับ `source`, `country`, `category`, `date`, `limit`
- `GET /api/lottery-sources` คืนสถานะ, เวลา fetch ล่าสุด, error ล่าสุด และจำนวนผลของแต่ละ source
- `POST /api/lottery-refresh` รองรับ refresh ทั้งหมดหรือเลือก source/category

เพิ่ม UI:

- แท็บ `ผลหวยทั้งหมด` สำหรับรวมผลทุก source
- แท็บแยก `หวยไทย`, `หวยต่างประเทศ`, `หวยหุ้น`, `Huayapp`
- ตัวกรอง source, country, category, date และชื่อรายการ
- ปุ่ม refresh ทันที
- auto-refresh ทุก 60 วินาทีขณะหน้าที่เกี่ยวข้องเปิดอยู่
- ป้ายสถานะและเวลาอัปเดต พร้อมลิงก์ต้นทาง
- error ของ source แสดงเฉพาะส่วนของ source นั้น

## ความถูกต้องและความล้มเหลว

- ผล pending/suspended/incomplete จะไม่เขียนทับผล published เดิม
- retry เฉพาะข้อผิดพลาดชั่วคราว และหยุดตามจำนวนครั้งที่กำหนด
- เมื่อ retry หมด ให้บันทึก failure/stale state และเก็บผลล่าสุด
- ตัวเลขทุกตัวเก็บเป็น string
- การ scrape ต้องเคารพ rate limit และเงื่อนไขของต้นทาง

## การทดสอบและเกณฑ์ยอมรับ

- fixture/parser test ครบทุก adapter ที่เปิดใช้งาน
- ตรวจสอบเลขศูนย์นำหน้า วันที่ รอบ และจำนวนรางวัล
- ทดสอบ upsert ซ้ำแล้วไม่เกิดแถวซ้ำ
- ทดสอบผลไม่ครบไม่เขียนทับผล published
- ทดสอบ timeout, retry, source failure และ stale state
- ทดสอบ API filter, source status และ manual refresh
- ทดสอบแท็บรวม/แยกและ responsive layout
- regression test ของยี่กี่ หุ้น และ endpoint เดิมต้องผ่าน

## การตัดสินใจที่ต้องยืนยันระหว่าง implementation

URL และ selector ของแหล่งภายนอกจะถูกตรวจสอบจากแหล่งสาธารณะที่เข้าถึงได้จริงตอนทำ adapter และจะไม่ฝังสมมติฐานว่าแหล่งใดมี API ถาวร หากแหล่งใดไม่ผ่าน validation จะยังคงอยู่ใน registry ด้วยสถานะ unavailable เพื่อให้ระบบสื่อสารข้อจำกัดได้อย่างชัดเจน
