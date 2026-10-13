from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

Status = Literal["published", "pending", "suspended", "unpublished", "failed"]


@dataclass(frozen=True)
class PrizeSlot:
    prize_name: str
    number_count: int
    status: Status


@dataclass(frozen=True)
class LotteryCard:
    lottery_id: str
    lottery_name: str
    category: str
    result_date: date | None
    result_date_display: str | None
    result_time: str | None
    status: Status
    prize_slots: tuple[PrizeSlot, ...]
    source_url: str
    historical_action: str | None = None


@dataclass
class PrizeResult:
    prize_name: str
    numbers: list[str] = field(default_factory=list)


@dataclass
class LotteryResult:
    source: str
    lottery_id: str
    lottery_name: str
    category: str
    result_date: date
    result_time: str | None
    round: str | None
    prizes: list[PrizeResult]
    status: Status
    scraped_at: datetime
    source_url: str
    source_text: str | None = None
    source_item_id: str = ""
    country: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...] = ()
