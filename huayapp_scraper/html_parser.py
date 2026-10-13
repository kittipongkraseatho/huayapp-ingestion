from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup, Tag

from .models import LotteryCard, PrizeSlot, Status
from .validator import normalize_thai_date


def _card_status(card: Tag) -> Status:
    text = card.get_text(" ", strip=True)
    if "รอผล" in text:
        return "pending"
    if "งด" in text:
        return "suspended"
    if card.select("canvas.frontend-canvas-obf"):
        return "published"
    return "unpublished"


def _result_date(card: Tag) -> date | None:
    update = (card.get("data-date-update") or "").strip()
    display = (card.get("data-date-display") or "").strip()
    if update:
        try:
            return datetime.fromisoformat(update[:10]).date()
        except ValueError:
            pass
    if display:
        try:
            return normalize_thai_date(display)
        except ValueError:
            return None
    return None


def _result_time(card: Tag) -> str | None:
    schedule = (card.get("data-schedule-time") or "").strip()
    return schedule or None


def _parse_card(card: Tag, source_url: str) -> LotteryCard:
    status = _card_status(card)
    slots: list[PrizeSlot] = []
    for cell in card.select(".lotto-cell"):
        label_node = cell.select_one(".lotto-cell-label")
        prize_name = label_node.get_text(" ", strip=True) if label_node else ""
        if not prize_name:
            continue
        canvas_count = len(cell.select("canvas.frontend-canvas-obf"))
        slot_status: Status = "published" if canvas_count else status
        slots.append(PrizeSlot(prize_name, canvas_count, slot_status))

    historical = card.select_one("button.button-after-result")
    return LotteryCard(
        lottery_id=(card.get("data-lotto-id") or "").strip(),
        lottery_name=(card.get("data-lotto-name") or "").strip(),
        category=(card.get("data-category") or "").strip(),
        result_date=_result_date(card),
        result_date_display=(card.get("data-date-display") or "").strip() or None,
        result_time=_result_time(card),
        status=status,
        prize_slots=tuple(slots),
        source_url=source_url,
        historical_action=historical.get("onclick") if historical else None,
    )


def parse_cards(html: str, source_url: str) -> list[LotteryCard]:
    # lxml is preferred in production; the stdlib parser keeps offline checks
    # usable when a platform cannot install the optional native wheel.
    parser = "lxml"
    try:
        import lxml  # noqa: F401
    except ImportError:
        parser = "html.parser"
    soup = BeautifulSoup(html, parser)
    return [_parse_card(card, source_url) for card in soup.select(".lotto-card[data-lotto-id]")]


def parse_card(card_html: str, source_url: str) -> LotteryCard:
    cards = parse_cards(card_html, source_url)
    if len(cards) != 1:
        raise ValueError(f"expected exactly one lottery card, found {len(cards)}")
    return cards[0]
