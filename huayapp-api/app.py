from __future__ import annotations

import os
import hmac
import ipaddress
import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from huayapp_scraper.config import Config
from huayapp_scraper.models import LotteryResult
from huayapp_scraper.scraper import ScrapeError, scrape_latest
from huayapp_scraper.refresh import refresh_all, refresh_all_cards
from huayapp_scraper.storage import open_store


async def _refresh_loop():
    # ``Config.refresh_interval_seconds`` is the single source of truth (env
    # var: REFRESH_INTERVAL_SECONDS, default 1800s). The floor of 60s keeps
    # a misconfigured env var from spawning overlapping refreshes.
    while True:
        cfg = config()
        try:
            await asyncio.to_thread(refresh_all_cards, cfg)
        except Exception as exc:  # noqa: BLE001 — never let the loop die
            import logging

            logging.getLogger("huayapp.refresh").exception("refresh failed: %s", exc)
        await asyncio.sleep(max(60, cfg.refresh_interval_seconds))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_refresh_loop())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(
    title="Huayapp Results API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)

origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "*").split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=origins != ["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class ScrapeRequest(BaseModel):
    lottery_id: str = Field(default="100", min_length=1, max_length=32)


class RefreshRequest(BaseModel):
    sources: list[str] = Field(default_factory=list, max_length=32)


def config() -> Config:
    return Config.from_env()


def result_payload(result: LotteryResult) -> dict:
    payload = asdict(result)
    payload["result_date"] = result.result_date.isoformat()
    payload["scraped_at"] = result.scraped_at.isoformat()
    return payload


def list_payload(lottery_id: str | None, limit: int) -> list[dict]:
    store = open_store(config())
    try:
        results = [item for item in store.list_results(lottery_id) if item.source == "huayapp.com"]
        return [result_payload(item) for item in results[:limit]]
    finally:
        store.close()


def _env_list(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def _request_ip(request: Request) -> str | None:
    # Railway sits behind a proxy. Only trust forwarded headers when explicitly
    # enabled; otherwise use the socket peer address.
    if os.getenv("TRUST_PROXY_HEADERS", "true").lower() not in {"0", "false", "no"}:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            candidate = forwarded.split(",", 1)[0].strip()
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                return None
    if request.client and request.client.host:
        try:
            return str(ipaddress.ip_address(request.client.host))
        except ValueError:
            return None
    return None


def _origin_host(request: Request) -> str | None:
    origin = request.headers.get("origin")
    if not origin:
        return None
    try:
        return (urlsplit(origin).hostname or "").lower().rstrip(".") or None
    except ValueError:
        return None


def _ip_allowed(client_ip: str | None, allowed_ips: list[str]) -> bool:
    if not client_ip:
        return False
    try:
        address = ipaddress.ip_address(client_ip)
        return any(address in ipaddress.ip_network(item, strict=False) for item in allowed_ips)
    except ValueError:
        return False


def _domain_allowed(host: str | None, allowed_domains: list[str]) -> bool:
    if not host:
        return False
    for item in allowed_domains:
        pattern = item.lower().rstrip(".")
        if pattern.startswith("*."):
            suffix = pattern[2:]
            if host.endswith("." + suffix):
                return True
        elif host == pattern:
            return True
    return False


def require_api_access(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> None:
    expected_key = os.getenv("SCRAPE_API_KEY")
    if not expected_key:
        raise HTTPException(status_code=503, detail="SCRAPE_API_KEY is not configured")
    if not x_api_key or not hmac.compare_digest(x_api_key, expected_key):
        raise HTTPException(status_code=401, detail="invalid scrape API key")

    allowed_ips = _env_list("ALLOWED_IPS")
    allowed_domains = _env_list("ALLOWED_DOMAINS")
    if not allowed_ips and not allowed_domains:
        raise HTTPException(status_code=503, detail="ALLOWED_IPS or ALLOWED_DOMAINS is not configured")

    if not _ip_allowed(_request_ip(request), allowed_ips) and not _domain_allowed(_origin_host(request), allowed_domains):
        raise HTTPException(status_code=403, detail="client IP or origin domain is not allowed")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/huayapp-results")
def huayapp_results(
    lottery_id: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=100, ge=1, le=500),
    _: None = Depends(require_api_access),
) -> dict:
    return {"huayapp": list_payload(lottery_id, limit)}


@app.post("/api/scrape/latest")
def scrape_latest_result(
    request: ScrapeRequest,
    _: None = Depends(require_api_access),
) -> JSONResponse:
    try:
        result = scrape_latest(config(), request.lottery_id)
        store = open_store(config())
        try:
            inserted = store.upsert(result)
        finally:
            store.close()
        return JSONResponse({"inserted": inserted, "result": result_payload(result)})
    except ScrapeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/stats")
def stats(_: None = Depends(require_api_access)) -> dict[str, dict[str, int]]:
    store = open_store(config())
    try:
        return {"results": store.stats()}
    finally:
        store.close()


@app.get("/api/lottery-results")
def lottery_results(
    source: str | None = Query(default=None, max_length=64),
    country: str | None = Query(default=None, max_length=8),
    category: str | None = Query(default=None, max_length=32),
    date: str | None = Query(default=None, max_length=16),
    limit: int = Query(default=100, ge=1, le=500),
    _: None = Depends(require_api_access),
) -> dict:
    store = open_store(config())
    try:
        results = store.list_results()
        if source:
            results = [item for item in results if item.source == source]
        if country:
            results = [item for item in results if item.country == country]
        if category:
            results = [item for item in results if item.category == category]
        if date:
            results = [item for item in results if item.result_date.isoformat() == date]
        return {
            "results": [result_payload(item) for item in results[:limit]],
            "serverTime": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        store.close()


@app.get("/api/lottery-sources")
def lottery_sources(_: None = Depends(require_api_access)) -> dict:
    store = open_store(config())
    try:
        return {
            "sources": store.list_source_states(),
            "serverTime": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        store.close()


@app.post("/api/lottery-refresh")
def lottery_refresh(request: RefreshRequest, _: None = Depends(require_api_access)) -> dict:
    report = refresh_all(config(), source_ids=request.sources or None)
    return {
        "report": asdict(report) if hasattr(report, "__dataclass_fields__") else {
            "results": report.results,
            "source_states": report.source_states,
            "errors": report.errors,
        },
        "serverTime": datetime.now(timezone.utc).isoformat(),
    }
