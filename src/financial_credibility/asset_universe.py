"""Built-in asset-class universes for post-extraction hard filtering."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ToolkitConfig


@dataclass(frozen=True)
class AssetUniverseRecord:
    """One canonical asset/instrument allowed under an asset class."""

    asset_class: str
    symbol: str
    name: str
    entity_type: str
    aliases: tuple[str, ...] = ()
    source: str = "built_in_asset_universe"


@dataclass(frozen=True)
class AssetUniverse:
    """Lookup table used to hard-filter non-equity extracted entities."""

    records: dict[str, tuple[AssetUniverseRecord, ...]]
    source: str
    notes: tuple[str, ...] = ()

    @property
    def loaded(self) -> bool:
        return bool(self.records)

    def match(self, entity: dict[str, Any]) -> AssetUniverseRecord | None:
        asset_class = normalize_asset_class(entity.get("asset_class"), entity.get("entity_type"))
        candidates = _candidate_keys(entity)
        for record in self.records.get(asset_class, ()):
            record_keys = _record_keys(record)
            if candidates & record_keys:
                return record
        return None


def load_asset_universe(config: ToolkitConfig) -> AssetUniverse:
    """Load built-in plus optional local asset universes."""
    if not config.enable_asset_universe_filter:
        return AssetUniverse(records={}, source="disabled", notes=("asset_universe_filter_disabled",))

    records = list(BUILT_IN_ASSETS)
    notes: list[str] = []
    if config.asset_universe_file:
        path = Path(str(config.asset_universe_file)).expanduser()
        try:
            records.extend(parse_asset_universe(path.read_text(encoding="utf-8")))
            notes.append(f"asset_universe_file:{path}")
        except Exception as exc:
            notes.append(f"asset_universe_load_failed:{type(exc).__name__}")

    grouped: dict[str, list[AssetUniverseRecord]] = {}
    for record in records:
        grouped.setdefault(normalize_asset_class(record.asset_class, record.entity_type), []).append(record)
    return AssetUniverse(
        records={key: tuple(value) for key, value in grouped.items()},
        source="built_in+local" if config.asset_universe_file else "built_in",
        notes=tuple(notes),
    )


def parse_asset_universe(text: str) -> list[AssetUniverseRecord]:
    """Parse local JSON asset universe additions.

    Accepted shape:
    {"assets": [{"asset_class": "equity_index", "symbol": "FOO", ...}]}
    or a bare list of asset records.
    """
    raw = json.loads(text)
    rows = raw.get("assets", raw) if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        return []
    records = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip()
        name = str(item.get("name") or symbol).strip()
        asset_class = normalize_asset_class(item.get("asset_class"), item.get("entity_type"))
        entity_type = str(item.get("entity_type") or asset_class).strip()
        aliases = item.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        if symbol and name and asset_class:
            records.append(
                AssetUniverseRecord(
                    asset_class=asset_class,
                    symbol=symbol,
                    name=name,
                    entity_type=entity_type,
                    aliases=tuple(str(alias) for alias in aliases if str(alias).strip()),
                    source="local_asset_universe",
                )
            )
    return records


def normalize_asset_class(value: Any, entity_type: Any = None) -> str:
    """Normalize model/free-form class labels to project asset-class ids."""
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    entity_raw = str(entity_type or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "public_company": "single_name_equity",
        "company": "single_name_equity",
        "stock": "single_name_equity",
        "equity": "single_name_equity",
        "issuer": "single_name_equity",
        "index": "equity_index",
        "equity_index": "equity_index",
        "stock_index": "equity_index",
        "index_future": "equity_index_future",
        "equity_future": "equity_index_future",
        "equity_index_futures": "equity_index_future",
        "etf": "fund_etf",
        "fund": "fund_etf",
        "fund_etf": "fund_etf",
        "commodity": "commodity",
        "commodities": "commodity",
        "commodity_future": "commodity_future",
        "commodity_futures": "commodity_future",
        "future": "commodity_future",
        "futures": "commodity_future",
        "currency": "fx",
        "currency_pair": "fx",
        "currency_index": "fx",
        "foreign_exchange": "fx",
        "fx": "fx",
        "rate": "rates",
        "rates": "rates",
        "interest_rate": "rates",
        "sovereign_rate": "rates",
        "credit": "credit",
        "credit_derivative": "credit",
        "macro": "macro_indicator",
        "macro_indicator": "macro_indicator",
        "economic_indicator": "macro_indicator",
        "crypto": "crypto",
        "cryptoasset": "crypto",
        "fixed_income": "fixed_income",
        "bond": "fixed_income",
        "volatility_index": "volatility_index",
        "volatility": "volatility_index",
    }
    return aliases.get(raw) or aliases.get(entity_raw) or raw or "other"


def normalize_asset_key(value: Any) -> str:
    """Normalize aliases/symbols for robust matching."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _candidate_keys(entity: dict[str, Any]) -> set[str]:
    keys = set()
    for field in ["symbol", "ticker", "name"]:
        value = entity.get(field)
        key = normalize_asset_key(value)
        if key:
            keys.add(key)
    return keys


def _record_keys(record: AssetUniverseRecord) -> set[str]:
    values = [record.symbol, record.name, *record.aliases]
    return {key for key in (normalize_asset_key(value) for value in values) if key}


def _asset(
    asset_class: str,
    symbol: str,
    name: str,
    entity_type: str,
    aliases: tuple[str, ...] = (),
) -> AssetUniverseRecord:
    return AssetUniverseRecord(
        asset_class=asset_class,
        symbol=symbol,
        name=name,
        entity_type=entity_type,
        aliases=aliases,
    )


BUILT_IN_ASSETS: tuple[AssetUniverseRecord, ...] = (
    _asset("equity_index", "SPX", "S&P 500 Index", "index", ("S&P 500", "SP500", "S&P500")),
    _asset("equity_index", "NDX", "Nasdaq 100 Index", "index", ("NASDAQ 100", "Nasdaq-100")),
    _asset("equity_index", "DJIA", "Dow Jones Industrial Average", "index", ("Dow Jones", "Dow")),
    _asset("equity_index", "RUT", "Russell 2000 Index", "index", ("Russell 2000",)),
    _asset("volatility_index", "VIX", "CBOE Volatility Index", "index", ("volatility index",)),
    _asset("equity_index_future", "ES", "E-mini S&P 500 Futures", "future", ("ES futures", "E-mini S&P")),
    _asset("equity_index_future", "NQ", "E-mini Nasdaq 100 Futures", "future", ("NQ futures", "E-mini Nasdaq")),
    _asset("equity_index_future", "RTY", "E-mini Russell 2000 Futures", "future", ("RTY futures",)),
    _asset("fund_etf", "SPY", "SPDR S&P 500 ETF", "etf", ("SPDR S&P 500",)),
    _asset("fund_etf", "QQQ", "Invesco QQQ Trust", "etf", ("Nasdaq 100 ETF",)),
    _asset("fund_etf", "IWM", "iShares Russell 2000 ETF", "etf", ("Russell 2000 ETF",)),
    _asset("fund_etf", "HYG", "iShares iBoxx High Yield Corporate Bond ETF", "etf", ("high yield ETF",)),
    _asset("fund_etf", "LQD", "iShares Investment Grade Corporate Bond ETF", "etf", ("investment grade ETF",)),
    _asset("fund_etf", "TLT", "iShares 20+ Year Treasury Bond ETF", "etf", ("long Treasury ETF",)),
    _asset("fund_etf", "GLD", "SPDR Gold Shares", "etf", ("gold ETF",)),
    _asset("fund_etf", "USO", "United States Oil Fund", "etf", ("oil ETF",)),
    _asset("commodity", "WTI", "WTI Crude Oil", "commodity", ("West Texas Intermediate", "crude oil")),
    _asset("commodity", "BRENT", "Brent Crude Oil", "commodity", ("Brent",)),
    _asset("commodity", "XAU", "Gold", "commodity", ("gold",)),
    _asset("commodity", "XAG", "Silver", "commodity", ("silver",)),
    _asset("commodity", "COPPER", "Copper", "commodity", ("copper",)),
    _asset("commodity", "NATGAS", "Natural Gas", "commodity", ("natural gas", "Henry Hub")),
    _asset("commodity_future", "CL", "WTI Crude Oil Futures", "future", ("NYMEX crude oil futures",)),
    _asset("commodity_future", "GC", "Gold Futures", "future", ("COMEX gold futures",)),
    _asset("commodity_future", "SI", "Silver Futures", "future", ("COMEX silver futures",)),
    _asset("commodity_future", "HG", "Copper Futures", "future", ("COMEX copper futures",)),
    _asset("commodity_future", "NG", "Natural Gas Futures", "future", ("Henry Hub futures",)),
    _asset("fx", "EUR/USD", "EUR/USD", "currency_pair", ("EURUSD",)),
    _asset("fx", "USD/JPY", "USD/JPY", "currency_pair", ("USDJPY",)),
    _asset("fx", "GBP/USD", "GBP/USD", "currency_pair", ("GBPUSD",)),
    _asset("fx", "AUD/USD", "AUD/USD", "currency_pair", ("AUDUSD",)),
    _asset("fx", "USD/CAD", "USD/CAD", "currency_pair", ("USDCAD",)),
    _asset("fx", "USD/CHF", "USD/CHF", "currency_pair", ("USDCHF",)),
    _asset("fx", "USD/CNH", "USD/CNH", "currency_pair", ("USDCNH",)),
    _asset("fx", "DXY", "U.S. Dollar Index", "currency_index", ("dollar index", "US Dollar Index")),
    _asset("rates", "FEDFUNDS", "Federal Funds Rate", "interest_rate", ("fed funds", "federal funds rate")),
    _asset("rates", "SOFR", "SOFR", "interest_rate", ("Secured Overnight Financing Rate",)),
    _asset("rates", "DGS10", "10-Year Treasury Yield", "sovereign_rate", ("10-year Treasury", "10Y Treasury", "UST 10Y")),
    _asset("rates", "DGS2", "2-Year Treasury Yield", "sovereign_rate", ("2-year Treasury", "2Y Treasury", "UST 2Y")),
    _asset("macro_indicator", "CPI", "Consumer Price Index", "macro_indicator", ("inflation", "consumer price index")),
    _asset("macro_indicator", "CORE_CPI", "Core CPI", "macro_indicator", ("core inflation",)),
    _asset("macro_indicator", "PCE", "PCE Price Index", "macro_indicator", ("personal consumption expenditures",)),
    _asset("macro_indicator", "PMI", "Purchasing Managers' Index", "macro_indicator", ("manufacturing PMI", "services PMI", "composite PMI", "purchasing managers index", "purchasing managers' index")),
    _asset("macro_indicator", "GDP", "Gross Domestic Product", "macro_indicator", ("gross domestic product",)),
    _asset("macro_indicator", "UNRATE", "Unemployment Rate", "macro_indicator", ("unemployment",)),
    _asset("macro_indicator", "NFP", "Nonfarm Payrolls", "macro_indicator", ("nonfarm payrolls", "payrolls")),
    _asset("credit", "HY_CREDIT", "High Yield Credit", "credit", ("HY spread", "HY spreads", "high yield spreads")),
    _asset("credit", "IG_CREDIT", "Investment Grade Credit", "credit", ("IG spread", "IG spreads", "investment grade spreads")),
    _asset("credit", "CDX", "CDX Credit Index", "credit_derivative", ("CDX IG", "CDX HY")),
    _asset("credit", "ITRAXX", "iTraxx Credit Index", "credit_derivative", ("iTraxx",)),
    _asset("credit", "CDS", "Credit Default Swap", "credit_derivative", ("credit default swap",)),
    _asset("crypto", "BTC", "Bitcoin", "cryptoasset", ("Bitcoin",)),
    _asset("crypto", "ETH", "Ether", "cryptoasset", ("Ethereum", "Ether")),
)
