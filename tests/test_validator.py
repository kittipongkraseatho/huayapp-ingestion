from datetime import date, datetime, timezone

import pytest

from huayapp_scraper.models import LotteryResult, PrizeResult
from huayapp_scraper.validator import _expected_digits, normalize_thai_date, validate_record


def _result(*, numbers=None, status="published"):
    return LotteryResult(
        source="huayapp.com",
        lottery_id="100",
        lottery_name="รัฐบาลไทย",
        category="หวยทางการ",
        result_date=date(2026, 10, 1),
        result_time=None,
        round=None,
        prizes=[
            PrizeResult("รางวัลที่ 1", [numbers or "012345"]),
            PrizeResult("2 ตัวล่าง", ["07"]),
        ],
        status=status,
        scraped_at=datetime.now(timezone.utc),
        source_url="https://huayapp.com/",
    )


def test_normalize_thai_display_date_to_iso_date():
    assert normalize_thai_date("01/10/69") == date(2026, 10, 1)
    assert normalize_thai_date("1 ตุลาคม 2569") == date(2026, 10, 1)


def test_normalize_thai_date_rejects_impossible_date():
    with pytest.raises(ValueError):
        normalize_thai_date("31/02/69")


def test_validate_record_preserves_leading_zeroes_and_digit_lengths():
    result = _result()
    validation = validate_record(result)

    assert validation.valid is True
    assert result.prizes[0].numbers == ["012345"]
    assert result.prizes[1].numbers == ["07"]


def test_validate_record_rejects_incomplete_or_non_numeric_values():
    assert validate_record(_result(numbers="1234")).valid is False
    assert validate_record(_result(numbers="12A345")).valid is False
    assert validate_record(_result(status="pending")).valid is False


def test_expected_digits_handles_legacy_and_huayapp_labels():
    assert _expected_digits("รางวัลที่ 1") == 6
    assert _expected_digits("2 ตัวล่าง") == 2
    assert _expected_digits("3 ตัวบน") == 3
    assert _expected_digits("4 ตัวล่าง") == 4
    # ``เลขบน`` is intentionally flexible: Huayapp uses 5 digits for newer
    # ฮานอย rounds but 6–7 digits for older ออมสิน / ธ.ก.ส. / ลาว draws.
    # Returning ``None`` lets the OCR result stand and lets downstream
    # validation compare against the trailing "3 ตัวบน" cell.
    assert _expected_digits("เลขบน") is None
    # Unknown label keeps None (HTML-driven; don't fabricate length)
    assert _expected_digits("รางวัลอื่น") is None
