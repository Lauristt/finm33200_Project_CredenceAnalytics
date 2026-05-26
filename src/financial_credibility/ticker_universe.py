"""Official ticker universe loading for post-extraction validation."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import ToolkitConfig
from .net import urlopen_request


SEC_COMPANY_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
DEFAULT_SEC_USER_AGENT = "Credence Analytics research contact@example.com"


@dataclass(frozen=True)
class TickerRecord:
    ticker: str
    cik: str
    name: str
    exchange: str
    source: str = "sec_company_tickers_exchange"


@dataclass(frozen=True)
class TickerUniverse:
    records: dict[str, TickerRecord]
    source: str
    notes: tuple[str, ...] = ()

    def get(self, ticker: str | None) -> TickerRecord | None:
        if not ticker:
            return None
        for key in _ticker_keys(str(ticker)):
            if key in self.records:
                return self.records[key]
        return None

    @property
    def loaded(self) -> bool:
        return bool(self.records)


def load_ticker_universe(config: ToolkitConfig) -> TickerUniverse:
    """Load the official ticker universe from file/cache/SEC, without failing extraction."""
    if not config.enable_ticker_universe_filter:
        return TickerUniverse(records={}, source="disabled", notes=("ticker_universe_filter_disabled",))

    source_files = [config.ticker_universe_file, config.ticker_universe_cache_file]
    for source_file in [item for item in source_files if item]:
        path = Path(str(source_file)).expanduser()
        if path.exists():
            try:
                records = parse_ticker_universe(path.read_text(encoding="utf-8"))
                return TickerUniverse(records=records, source=str(path), notes=())
            except Exception as exc:
                return TickerUniverse(
                    records={},
                    source=str(path),
                    notes=(f"ticker_universe_load_failed:{type(exc).__name__}",),
                )

    if not config.enable_ticker_universe_fetch:
        return TickerUniverse(records={}, source="none", notes=("ticker_universe_unavailable",))

    return _fetch_and_cache_ticker_universe(
        cache_file=config.ticker_universe_cache_file,
        sec_user_agent=config.sec_user_agent,
        request_timeout=min(float(config.request_timeout), 8.0),
        allow_insecure_ssl_fallback=config.allow_insecure_ssl_fallback,
    )


def parse_ticker_universe(text: str) -> dict[str, TickerRecord]:
    """Parse SEC company ticker JSON formats into a ticker-indexed mapping."""
    raw = json.loads(text)
    rows = _iter_sec_rows(raw)
    records: dict[str, TickerRecord] = {}
    for item in rows:
        ticker = str(item.get("ticker") or "").upper().replace("/", ".").strip()
        cik = _normalize_cik(item.get("cik") or item.get("cik_str"))
        name = str(item.get("name") or item.get("title") or "").strip()
        exchange = str(item.get("exchange") or "").strip()
        if ticker and cik and name:
            record = TickerRecord(ticker=ticker, cik=cik, name=name, exchange=exchange)
            for key in _ticker_keys(ticker):
                records[key] = record
    return records


@lru_cache(maxsize=4)
def _fetch_and_cache_ticker_universe(
    cache_file: str | None,
    sec_user_agent: str | None,
    request_timeout: float,
    allow_insecure_ssl_fallback: bool,
) -> TickerUniverse:
    request = urllib.request.Request(
        SEC_COMPANY_TICKERS_EXCHANGE_URL,
        headers={
            "User-Agent": sec_user_agent or DEFAULT_SEC_USER_AGENT,
            "Accept": "application/json",
            "Host": "www.sec.gov",
        },
        method="GET",
    )
    try:
        with urlopen_request(
            request,
            timeout=request_timeout,
            allow_insecure_ssl_fallback=allow_insecure_ssl_fallback,
        ) as response:
            text = response.read().decode("utf-8")
        if cache_file:
            path = Path(cache_file).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        records = parse_ticker_universe(text)
        return TickerUniverse(records=records, source=SEC_COMPANY_TICKERS_EXCHANGE_URL, notes=())
    except Exception as exc:
        return TickerUniverse(
            records={},
            source=SEC_COMPANY_TICKERS_EXCHANGE_URL,
            notes=(f"ticker_universe_fetch_failed:{type(exc).__name__}",),
        )


def _iter_sec_rows(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict) and isinstance(raw.get("fields"), list) and isinstance(raw.get("data"), list):
        fields = [str(field) for field in raw["fields"]]
        return [dict(zip(fields, row)) for row in raw["data"] if isinstance(row, list)]
    if isinstance(raw, dict):
        values = raw.values()
        return [item for item in values if isinstance(item, dict)]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def _normalize_cik(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits.zfill(10) if digits else ""


def _ticker_keys(value: str) -> list[str]:
    ticker = value.upper().replace("/", ".").strip()
    keys = [ticker]
    if "." in ticker:
        keys.append(ticker.replace(".", "-"))
    if "-" in ticker:
        keys.append(ticker.replace("-", "."))
    return list(dict.fromkeys(keys))
