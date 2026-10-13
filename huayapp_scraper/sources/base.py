from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Protocol

from ..models import LotteryResult


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    name: str
    country: str
    category: str
    url: str
    enabled: bool = True


@dataclass
class SourceFetch:
    results: list[LotteryResult] = field(default_factory=list)
    status: str = "failed"
    fetched_at: datetime | None = None
    error: str | None = None


class SourceAdapter(Protocol):
    spec: SourceSpec

    def fetch(self, config) -> SourceFetch:
        ...


Parser = Callable[[str, SourceSpec], list[LotteryResult]]
