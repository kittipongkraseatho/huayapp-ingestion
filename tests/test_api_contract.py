import sys
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

sys.path.insert(0, "huayapp-api")
import app as app_module  # noqa: E402

from huayapp_scraper.config import Config  # noqa: E402
from huayapp_scraper.models import LotteryResult, PrizeResult  # noqa: E402
from huayapp_scraper.storage import SQLiteStore  # noqa: E402


def make_result(tmp_path):
    return LotteryResult(
        source="lao",
        lottery_id="lao-1",
        lottery_name="Lao Lottery",
        category="regional",
        result_date=date(2026, 10, 1),
        result_time="19:30",
        round="2026-10-01",
        prizes=[PrizeResult("1st Prize", ["0123"])],
        status="published",
        scraped_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        source_url="https://example.test/results",
        source_item_id="lao-1",
        country="LA",
    )


def client_for(monkeypatch, tmp_path):
    app_module.app.dependency_overrides[app_module.require_api_access] = lambda: None
    monkeypatch.setattr(app_module, "config", lambda: Config(database_path=tmp_path / "results.db"))
    return TestClient(app_module.app)


def test_lottery_results_endpoint_applies_filters_and_limit(monkeypatch, tmp_path):
    store = SQLiteStore(tmp_path / "results.db")
    store.upsert(make_result(tmp_path))
    store.close()
    client = client_for(monkeypatch, tmp_path)

    response = client.get("/api/lottery-results?country=LA&category=regional&limit=1")

    assert response.status_code == 200
    assert len(response.json()["results"]) == 1
    assert response.json()["results"][0]["source_item_id"] == "lao-1"


def test_lottery_sources_endpoint_returns_last_error(monkeypatch, tmp_path):
    store = SQLiteStore(tmp_path / "results.db")
    store.upsert_source_state(
        "lao",
        name="Lao Lottery",
        country="LA",
        category="regional",
        url="https://example.test/results",
        enabled=True,
        status="stale",
        last_error="temporary outage",
    )
    store.close()
    client = client_for(monkeypatch, tmp_path)

    response = client.get("/api/lottery-sources")

    assert response.status_code == 200
    assert response.json()["sources"][0]["last_error"] == "temporary outage"


def test_lottery_refresh_endpoint_forwards_selected_sources(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path)
    calls = []

    class Report:
        results = 2
        source_states = []
        errors = []

    def fake_refresh(config, *, source_ids=None):
        calls.append(source_ids)
        return Report()

    monkeypatch.setattr(app_module, "refresh_all", fake_refresh)

    response = client.post("/api/lottery-refresh", json={"sources": ["lao"]})

    assert response.status_code == 200
    assert calls == [["lao"]]
    assert response.json()["report"]["results"] == 2
