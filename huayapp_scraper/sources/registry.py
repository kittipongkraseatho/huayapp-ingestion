from __future__ import annotations

from ..config import Config
from .base import SourceSpec
from .external import ConfiguredPublicAdapter, parse_public_result_cards
from .huayapp import HuayappAdapter


SOURCE_DEFINITIONS = (
    ("huayapp", "Huayapp", "TH", "huayapp"),
    ("thai-government", "หวยรัฐบาลไทย", "TH", "government"),
    ("savings-lottery", "หวยออมสิน/ธ.ก.ส.", "TH", "government"),
    ("lao", "หวยลาว", "LA", "regional"),
    ("hanoi", "หวยฮานอย", "VN", "regional"),
    ("malaysia", "หวยมาเลย์", "MY", "regional"),
    ("thai-stocks", "หุ้นไทย", "TH", "stock"),
    ("foreign-stocks", "หุ้นต่างประเทศ", "INTL", "stock"),
)


def build_source_registry(config: Config) -> dict[str, ConfiguredPublicAdapter]:
    enabled = set(config.enabled_sources)
    registry: dict[str, ConfiguredPublicAdapter] = {}
    for source_id, name, country, category in SOURCE_DEFINITIONS:
        url = config.source_url if source_id == "huayapp" else config.source_urls.get(source_id, "")
        is_enabled = not enabled or source_id in enabled
        spec = SourceSpec(source_id, name, country, category, url, is_enabled)
        if source_id == "huayapp":
            registry[source_id] = HuayappAdapter(spec)
        else:
            registry[source_id] = ConfiguredPublicAdapter(spec, parser=parse_public_result_cards)
    return registry
