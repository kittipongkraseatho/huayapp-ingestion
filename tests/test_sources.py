from huayapp_scraper.config import Config
from huayapp_scraper.sources.base import SourceSpec
from huayapp_scraper.sources.external import ConfiguredPublicAdapter
from huayapp_scraper.sources.registry import build_source_registry


EXPECTED_SOURCE_IDS = {
    "huayapp",
    "thai-government",
    "savings-lottery",
    "lao",
    "hanoi",
    "malaysia",
    "thai-stocks",
    "foreign-stocks",
}


def test_source_registry_contains_all_supported_source_groups():
    registry = build_source_registry(Config())

    assert EXPECTED_SOURCE_IDS.issubset(registry)
    assert all(adapter.spec.source_id for adapter in registry.values())
    assert all(adapter.spec.name for adapter in registry.values())
    assert all(adapter.spec.category for adapter in registry.values())


def test_source_registry_marks_disabled_sources_without_removing_them(monkeypatch):
    monkeypatch.setenv("ENABLED_LOTTERY_SOURCES", "huayapp,lao")

    registry = build_source_registry(Config.from_env())

    assert registry["huayapp"].spec.enabled is True
    assert registry["lao"].spec.enabled is True
    assert registry["hanoi"].spec.enabled is False


def test_configured_adapter_without_public_url_is_explicitly_unavailable():
    spec = SourceSpec(
        source_id="test-source",
        name="Test source",
        country="TH",
        category="government",
        url="",
        enabled=True,
    )

    result = ConfiguredPublicAdapter(spec).fetch(Config())

    assert result.status == "unavailable"
    assert result.results == []
    assert result.error
