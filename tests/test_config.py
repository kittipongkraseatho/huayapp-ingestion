import pytest

from pathlib import Path

from huayapp_scraper.config import Config


def test_default_database_is_the_application_database():
    assert Config().database_path == Path("lottery.db")
    assert Config().database_url is None


def test_from_env_reads_database_url():
    from importlib import reload
    import os

    config_module = __import__("huayapp_scraper.config", fromlist=["Config"])
    try:
        os.environ["DATABASE_URL"] = "postgres://user:pass@db.example/lottery"
        reload(config_module)
        cfg = config_module.Config.from_env()
        assert cfg.database_url == "postgres://user:pass@db.example/lottery"
    finally:
        os.environ.pop("DATABASE_URL", None)
        reload(config_module)


def test_from_env_database_url_default_is_none(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    cfg = Config.from_env()
    assert cfg.database_url is None
