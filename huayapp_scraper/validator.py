from __future__ import annotations

import re
from datetime import date

from .models import LotteryResult, ValidationResult

_THAI_MONTHS = {
    "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
    "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
    "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12,
}


def normalize_thai_date(value: str) -> date:
    raw = " ".join(value.strip().split())
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", raw)
    if match:
        day, month, year = (int(part) for part in match.groups())
        if year < 100:
            year += 2500
        if year >= 2400:
            year -= 543
        return date(year, month, day)

    match = re.fullmatch(r"(\d{1,2})\s+([^\s]+)\s+(\d{4})", raw)
    if match and match.group(2) in _THAI_MONTHS:
        day = int(match.group(1))
        year = int(match.group(3)) - 543
        return date(year, _THAI_MONTHS[match.group(2)], day)

    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    raise ValueError(f"unsupported date format: {value!r}")


def _expected_digits(prize_name: str) -> int | None:
    if "รางวัลที่ 1" in prize_name:
        return 6
    if "2 ตัว" in prize_name:
        return 2
    if "3 ตัว" in prize_name:
        return 3
    if "4 ตัว" in prize_name:
        return 4
    # ``เลขบน`` is intentionally NOT pinned to a fixed digit count: some
    # Huayapp rounds (older ออมสิน / ธ.ก.ส. / ลาว draws, etc.) store a 6- or
    # 7-digit number in the same cell that newer ฮานอย rounds use 5 digits.
    # Downstream ``validate_record`` reuses this helper; returning ``None``
    # means we accept whatever the OCR returns and rely on the 3 ตัวบน cell
    # to flag inconsistencies.
    return None


def validate_record(record: LotteryResult) -> ValidationResult:
    errors: list[str] = []
    if not record.source or not record.source_url:
        errors.append("source and source_url are required")
    if not record.lottery_id or not record.lottery_name:
        errors.append("lottery identity is required")
    if record.status != "published":
        errors.append(f"record status is {record.status}, not published")
    if not record.prizes:
        errors.append("at least one prize is required")

    for prize in record.prizes:
        if not prize.numbers:
            errors.append(f"{prize.prize_name}: no numbers")
            continue
        expected = _expected_digits(prize.prize_name)
        for number in prize.numbers:
            if not re.fullmatch(r"\d+", number or ""):
                errors.append(f"{prize.prize_name}: non-numeric number")
            elif expected is not None and len(number) != expected:
                errors.append(f"{prize.prize_name}: expected {expected} digits")

    return ValidationResult(not errors, tuple(errors))
