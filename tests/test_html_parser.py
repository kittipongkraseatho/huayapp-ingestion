from datetime import date
from pathlib import Path

from huayapp_scraper.html_parser import parse_cards


FIXTURE = Path(__file__).parent / "fixtures" / "thai_gov_latest.html"


def test_parse_verified_card_metadata_and_canvas_slots():
    cards = parse_cards(FIXTURE.read_text(encoding="utf-8"), "https://huayapp.com/")

    card = next(card for card in cards if card.lottery_id == "100")
    assert card.lottery_name == "รัฐบาลไทย"
    assert card.category == "หวยทางการ"
    assert card.result_date == date(2026, 10, 1)
    assert card.result_date_display == "01/10/69"
    assert card.status == "published"
    assert [(slot.prize_name, slot.number_count) for slot in card.prize_slots] == [
        ("รางวัลที่ 1", 1),
        ("3 ตัวบน", 1),
        ("2 ตัวล่าง", 1),
        ("3 ตัวหน้า", 2),
        ("3 ตัวหลัง", 2),
    ]
    assert "openBackwardModal" in (card.historical_action or "")


def test_parser_distinguishes_pending_and_suspended_cards():
    cards = parse_cards(FIXTURE.read_text(encoding="utf-8"), "https://huayapp.com/")

    by_id = {card.lottery_id: card for card in cards}
    assert by_id["155"].status == "pending"
    assert by_id["158"].status == "suspended"
