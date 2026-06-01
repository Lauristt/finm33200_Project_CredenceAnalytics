"""Memo-level entity extraction for report generation and agent tools."""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

from .asset_universe import AssetUniverseRecord, load_asset_universe, normalize_asset_class
from .config import ToolkitConfig
from .net import urlopen_request
from .ticker_universe import TickerRecord, load_ticker_universe


_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{0,4}(?:[.-][A-Z])?$")
_INLINE_TICKER_RE = re.compile(r"\$([A-Z]{1,5}(?:[.-][A-Z])?)\b|\(([A-Z]{1,5}(?:[.-][A-Z])?)\)")
_UPPER_TOKEN_RE = re.compile(r"\b([A-Z]{2,5}(?:[.-][A-Z])?)\b")
_AMBIGUOUS_TICKERS = {"AI", "PMI"}
_TIME_SUFFIX_TICKERS = {"AM", "PM"}
_AMBIGUOUS_TICKER_CONTEXT = {
    "AI": re.compile(
        r"\$AI\b|\(AI\)|\b(?:ticker|symbol|NYSE|NASDAQ)\s*[:=]?\s*AI\b|\bC3\.?\s*ai\b",
        re.IGNORECASE,
    ),
    "PMI": re.compile(
        r"\$PMI\b|\(PMI\)|\b(?:ticker|symbol|NYSE|NASDAQ)\s*[:=]?\s*PMI\b",
        re.IGNORECASE,
    ),
}
_TIME_SUFFIX_RE = re.compile(r"(?:\b\d{1,2}:\d{2}(?::\d{2})?|\b\d{1,2})\s*$")
_STOPWORDS = {
    "THE",
    "HOW",
    "US",
    "CEO",
    "CFO",
    "CPI",
    "EPS",
    "EBITDA",
    "EDGAR",
    "BEA",
    "BIS",
    "BLS",
    "BOE",
    "CFTC",
    "ECB",
    "EIA",
    "FINRA",
    "FRED",
    "GAAP",
    "GDP",
    "HICP",
    "IMF",
    "IR",
    "LLM",
    "MD",
    "PMI",
    "SEC",
    "SOFR",
    "TRACE",
    "WDI",
    "AUD",
    "CAD",
    "CHF",
    "CNH",
    "CNY",
    "USA",
    "USD",
    "EUR",
    "GBP",
    "HY",
    "IG",
    "JPY",
    "OAS",
    "PCE",
    "PPI",
    "WTI",
}

_KNOWN_PUBLIC_COMPANIES = [
    (r"\bApple(?: Inc\.?)?\b", "Apple Inc.", "AAPL"),
    (r"\bMicrosoft(?: Corporation| Corp\.?)?\b", "Microsoft Corporation", "MSFT"),
    (r"\bNvidia(?: Corporation| Corp\.?)?\b", "NVIDIA Corporation", "NVDA"),
    (r"\bQualcomm(?: Incorporated| Inc\.?)?\b", "QUALCOMM Incorporated", "QCOM"),
    (r"\bMicron(?: Technology)?(?: Inc\.?)?\b", "Micron Technology, Inc.", "MU"),
    (r"\bBroadcom(?: Inc\.?)?\b", "Broadcom Inc.", "AVGO"),
    (r"\bAmazon(?:\.com)?(?: Inc\.?)?\b", "Amazon.com, Inc.", "AMZN"),
    (r"\bAlphabet(?: Inc\.?)?\b|\bGoogle\b", "Alphabet Inc.", "GOOGL"),
    (r"\bMeta(?: Platforms)?(?: Inc\.?)?\b|\bFacebook\b", "Meta Platforms, Inc.", "META"),
    (r"\bTesla(?: Inc\.?)?\b", "Tesla, Inc.", "TSLA"),
    (r"\bNetflix(?: Inc\.?)?\b", "Netflix, Inc.", "NFLX"),
    (r"\bSnowflake(?: Inc\.?)?\b", "Snowflake Inc.", "SNOW"),
    (r"\bDollar Tree(?: Inc\.?)?\b", "Dollar Tree, Inc.", "DLTR"),
    (r"\bKohl'?s(?: Corporation| Corp\.?)?\b", "Kohl's Corporation", "KSS"),
    (r"\bBest Buy(?: Co\.?)?(?: Inc\.?)?\b", "Best Buy Co., Inc.", "BBY"),
    (r"\bHormel Foods(?: Corporation| Corp\.?)?\b", "Hormel Foods Corporation", "HRL"),
    (r"\bMarvell Technology(?: Inc\.?)?\b|\bMarvell\b", "Marvell Technology, Inc.", "MRVL"),
    (r"\bPhilip Morris(?: International)?(?: Inc\.?)?\b", "Philip Morris International Inc.", "PM"),
    (r"\bJPMorgan Chase(?: & Co\.?)?\b|\bJP Morgan\b", "JPMorgan Chase & Co.", "JPM"),
    (r"\bBank of America(?: Corporation| Corp\.?)?\b", "Bank of America Corporation", "BAC"),
    (r"\bBerkshire Hathaway\b", "Berkshire Hathaway Inc.", "BRK.B"),
]

_KNOWN_SYMBOL_ASSETS = {
    "SPX": ("S&P 500 Index", "equity_index", "index"),
    "NDQ": ("Nasdaq Composite Index", "equity_index", "index"),
    "NDX": ("Nasdaq 100 Index", "equity_index", "index"),
    "DJIA": ("Dow Jones Industrial Average", "equity_index", "index"),
    "RUT": ("Russell 2000 Index", "equity_index", "index"),
    "VIX": ("CBOE Volatility Index", "volatility_index", "index"),
    "ES": ("E-mini S&P 500 Futures", "equity_index_future", "future"),
    "NQ": ("E-mini Nasdaq 100 Futures", "equity_index_future", "future"),
    "RTY": ("E-mini Russell 2000 Futures", "equity_index_future", "future"),
    "CL": ("WTI Crude Oil Futures", "commodity_future", "future"),
    "GC": ("Gold Futures", "commodity_future", "future"),
    "SI": ("Silver Futures", "commodity_future", "future"),
    "HG": ("Copper Futures", "commodity_future", "future"),
    "NG": ("Natural Gas Futures", "commodity_future", "future"),
    "WTI": ("WTI Crude Oil", "commodity", "commodity"),
    "DXY": ("U.S. Dollar Index", "fx", "currency_index"),
    "PMI": ("Purchasing Managers' Index", "macro_indicator", "macro_indicator"),
    "PPI": ("Producer Price Index", "macro_indicator", "macro_indicator"),
    "BTC": ("Bitcoin", "crypto", "cryptoasset"),
    "ETH": ("Ether", "crypto", "cryptoasset"),
    "SPY": ("SPDR S&P 500 ETF", "fund_etf", "etf"),
    "QQQ": ("Invesco QQQ Trust", "fund_etf", "etf"),
    "IWM": ("iShares Russell 2000 ETF", "fund_etf", "etf"),
    "HYG": ("iShares iBoxx High Yield Corporate Bond ETF", "fund_etf", "etf"),
    "LQD": ("iShares Investment Grade Corporate Bond ETF", "fund_etf", "etf"),
    "TLT": ("iShares 20+ Year Treasury Bond ETF", "fund_etf", "etf"),
    "GLD": ("SPDR Gold Shares", "fund_etf", "etf"),
    "USO": ("United States Oil Fund", "fund_etf", "etf"),
}

_ASSET_PATTERNS = [
    (r"\bS&P\s*500\b|\bSPX\b", "S&P 500 Index", "SPX", "equity_index", "index"),
    (r"\bNasdaq\s+Composite\b|\bNasdaq composite\b|\bNDQ\b", "Nasdaq Composite Index", "NDQ", "equity_index", "index"),
    (r"\bNasdaq\s*100\b|\bNDX\b", "Nasdaq 100 Index", "NDX", "equity_index", "index"),
    (r"\bNasdaq\b", "Nasdaq Composite Index", "NDQ", "equity_index", "index"),
    (r"\bDow Jones(?: Industrial Average)?\b|\bDJIA\b|\bthe\s+Dow\b", "Dow Jones Industrial Average", "DJIA", "equity_index", "index"),
    (r"\bRussell\s*2000\b|\bRUT\b", "Russell 2000 Index", "RUT", "equity_index", "index"),
    (r"\bVIX\b|\bvolatility index\b", "CBOE Volatility Index", "VIX", "volatility_index", "index"),
    (r"\bE-?mini S&P(?: 500)?\b|\bES futures?\b", "E-mini S&P 500 Futures", "ES", "equity_index_future", "future"),
    (r"\bE-?mini Nasdaq(?: 100)?\b|\bNQ futures?\b", "E-mini Nasdaq 100 Futures", "NQ", "equity_index_future", "future"),
    (r"\bS&P\s*500 futures?\b|\bSPX futures?\b", "S&P 500 Futures", "ES", "equity_index_future", "future"),
    (r"\bNasdaq(?:\s*100)? futures?\b|\bNDX futures?\b", "Nasdaq Futures", "NQ", "equity_index_future", "future"),
    (r"\bWTI\b|\bWest Texas Intermediate\b|\bcrude oil\b", "WTI Crude Oil", "WTI", "commodity", "commodity"),
    (r"\bBrent\b", "Brent Crude Oil", "BRENT", "commodity", "commodity"),
    (r"\bgold\b|\bXAU\b", "Gold", "XAU", "commodity", "commodity"),
    (r"\bsilver\b|\bXAG\b", "Silver", "XAG", "commodity", "commodity"),
    (r"\bcopper\b", "Copper", "COPPER", "commodity", "commodity"),
    (r"\bnatural gas\b|\bHenry Hub\b", "Natural Gas", "NATGAS", "commodity", "commodity"),
    (r"\bEUR/USD\b|\bEURUSD\b", "EUR/USD", "EUR/USD", "fx", "currency_pair"),
    (r"\bUSD/JPY\b|\bUSDJPY\b", "USD/JPY", "USD/JPY", "fx", "currency_pair"),
    (r"\bGBP/USD\b|\bGBPUSD\b", "GBP/USD", "GBP/USD", "fx", "currency_pair"),
    (r"\bdollar\b.*\byen\b|\byen\b.*\bdollar\b", "USD/JPY", "USD/JPY", "fx", "currency_pair"),
    (r"\beuro\b.*\bdollar\b|\bdollar\b.*\beuro\b", "EUR/USD", "EUR/USD", "fx", "currency_pair"),
    (r"\bDXY\b|\bU\.?S\.? Dollar Index\b|\bdollar index\b", "U.S. Dollar Index", "DXY", "fx", "currency_index"),
    (r"\bCPI\b|\bconsumer price index\b|\binflation\b", "Consumer Price Index", "CPI", "macro_indicator", "macro_indicator"),
    (r"\bcore CPI\b", "Core CPI", "CORE_CPI", "macro_indicator", "macro_indicator"),
    (r"\bPPI\b|\bproducer price index\b", "Producer Price Index", "PPI", "macro_indicator", "macro_indicator"),
    (r"\bPCE\b|\bpersonal consumption expenditures\b", "PCE Price Index", "PCE", "macro_indicator", "macro_indicator"),
    (r"\b(?:manufacturing|services|composite)?\s*PMI\b|\bpurchasing managers'? index\b", "Purchasing Managers' Index", "PMI", "macro_indicator", "macro_indicator"),
    (r"\bGDP\b|\bgross domestic product\b", "Gross Domestic Product", "GDP", "macro_indicator", "macro_indicator"),
    (r"\bunemployment\b|\bUNRATE\b", "Unemployment Rate", "UNRATE", "macro_indicator", "macro_indicator"),
    (r"\bnonfarm payrolls?\b|\bNFP\b|\bpayrolls?\b", "Nonfarm Payrolls", "NFP", "macro_indicator", "macro_indicator"),
    (r"\bFed funds\b|\bfederal funds rate\b|\bFederal Reserve\b(?=.*?\brate)|\bfed rate\b|\bFFR\b", "Federal Funds Rate", "FEDFUNDS", "rates", "interest_rate"),
    (r"\bSOFR\b", "SOFR", "SOFR", "rates", "interest_rate"),
    (r"\b10[- ]year\b.*?\bTreasury\b|\b10Y\b.*?\bTreasury\b|\bDGS10\b|\bT-note\b", "10-Year Treasury Yield", "DGS10", "rates", "sovereign_rate"),
    (r"\b2[- ]year\b.*?\bTreasury\b|\b2Y\b.*?\bTreasury\b|\bDGS2\b", "2-Year Treasury Yield", "DGS2", "rates", "sovereign_rate"),
    (r"\b30[- ]year\b.*?\bTreasury\b|\b30Y\b.*?\bTreasury\b|\bDGS30\b|\blong bond\b", "30-Year Treasury Yield", "DGS30", "rates", "sovereign_rate"),
    (r"\bhigh[- ]yield\b|\bHY spreads?\b|\bHYG\b", "High Yield Credit", "HY_CREDIT", "credit", "credit"),
    (r"\binvestment[- ]grade\b|\bIG spreads?\b|\bLQD\b", "Investment Grade Credit", "IG_CREDIT", "credit", "credit"),
    (r"\bCDX\b|\biTraxx\b|\bCDS\b|\bcredit default swap", "Credit Derivatives", "CREDIT_DERIVATIVES", "credit", "credit_derivative"),
    (r"\bTRACE\b|\bfixed income\b|\bcorporate bonds?\b|\bbond trades?\b", "Fixed Income", "TRACE", "fixed_income", "fixed_income"),
    (r"\bOTC derivatives?\b|\binterest[- ]rate derivatives?\b|\bFX derivatives?\b", "OTC Derivatives", "OTC_DERIV", "derivatives", "derivatives"),
    (r"\bBitcoin\b|\bBTC\b", "Bitcoin", "BTC", "crypto", "cryptoasset"),
    (r"\bEthereum\b|\bEther\b|\bETH\b", "Ether", "ETH", "crypto", "cryptoasset"),
]


def extract_entities_from_memo(
    memo: str,
    config: ToolkitConfig | None = None,
    max_entities: int = 8,
) -> dict[str, Any]:
    """Extract financial entities, symbols, and asset classes from a memo."""
    cfg = config or ToolkitConfig.from_env()
    notes: list[str] = []
    heuristic_entities = _heuristic_entities(memo)
    llm_entities: list[dict[str, Any]] = []
    method = "heuristic"

    provider = cfg.llm_provider.lower()
    try:
        if provider in {"auto", "openai"} and cfg.openai_api_key and cfg.openai_model:
            llm_entities = _openai_extract_entities(memo, cfg)
            method = "openai+heuristic"
        elif provider in {"auto", "anthropic"} and cfg.anthropic_api_key and cfg.anthropic_model:
            llm_entities = _anthropic_extract_entities(memo, cfg)
            method = "anthropic+heuristic"
    except Exception as exc:
        notes.append(f"llm_entity_extraction_fallback:{exc}")
        method = "heuristic"

    merged_entities = _merge_entities(llm_entities + heuristic_entities)
    entities, filter_notes = _filter_ambiguous_entities(merged_entities, memo)
    notes.extend(filter_notes)
    entities, universe_notes = _filter_against_ticker_universe(entities, cfg)
    notes.extend(universe_notes)
    entities, asset_notes = _filter_against_asset_universe(entities, cfg)
    notes.extend(asset_notes)
    entities = entities[:max_entities]
    tickers = _dedupe([item["ticker"] for item in entities if _is_public_company_entity(item)])
    asset_groups = _asset_groups(entities)
    unresolved = [item for item in entities if _is_unresolved_public_company(item)]
    if not tickers and unresolved:
        notes.append("entities_found_without_public_tickers")
    if not entities:
        notes.append("no_entities_extracted")

    return {
        "method": method,
        "entities": entities,
        "tickers": tickers,
        "asset_classes": list(asset_groups.keys()),
        "asset_groups": asset_groups,
        "unresolved_entities": unresolved,
        "non_equity_entities": [item for item in entities if not _is_public_company_entity(item)],
        "notes": notes,
    }


def heuristic_entities_from_text(memo: str, max_entities: int = 8) -> list[dict[str, Any]]:
    """Return local, no-LLM entity guesses for routing and source selection."""
    entities, _notes = _filter_ambiguous_entities(_merge_entities(_heuristic_entities(memo)), memo)
    return entities[:max_entities]


def heuristic_asset_classes_from_text(memo: str) -> list[str]:
    """Return asset classes visible from local entity/pattern extraction only."""
    return list(_asset_groups(heuristic_entities_from_text(memo)).keys())


def _heuristic_entities(memo: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for groups in _INLINE_TICKER_RE.findall(memo):
        ticker = _normalize_ticker(next((item for item in groups if item), ""))
        if ticker:
            known_asset = _KNOWN_SYMBOL_ASSETS.get(ticker)
            if known_asset:
                name, asset_class, entity_type = known_asset
                entities.append(
                    _entity(
                        name=name,
                        ticker=None,
                        symbol=ticker,
                        asset_class=asset_class,
                        entity_type=entity_type,
                        confidence=0.82,
                        source="regex_symbol",
                    )
                )
            else:
                entities.append(_entity(name=ticker, ticker=ticker, confidence=0.82, source="regex_ticker"))

    for token in _UPPER_TOKEN_RE.findall(memo):
        ticker = _normalize_ticker(token)
        if not ticker:
            continue
        known_asset = _KNOWN_SYMBOL_ASSETS.get(ticker)
        if known_asset:
            name, asset_class, entity_type = known_asset
            entities.append(
                _entity(
                    name=name,
                    ticker=None,
                    symbol=ticker,
                    asset_class=asset_class,
                    entity_type=entity_type,
                    confidence=0.68,
                    source="known_asset_symbol",
                )
            )
        elif ticker not in _STOPWORDS:
            entities.append(_entity(name=ticker, ticker=ticker, confidence=0.62, source="regex_uppercase"))

    for pattern, name, ticker in _KNOWN_PUBLIC_COMPANIES:
        if re.search(pattern, memo, re.IGNORECASE):
            entities.append(_entity(name=name, ticker=ticker, confidence=0.74, source="known_alias"))
    for pattern, name, symbol, asset_class, entity_type in _ASSET_PATTERNS:
        if re.search(pattern, memo, re.IGNORECASE):
            entities.append(
                _entity(
                    name=name,
                    ticker=None,
                    symbol=symbol,
                    asset_class=asset_class,
                    entity_type=entity_type,
                    confidence=0.72,
                    source="asset_class_pattern",
                )
            )
    return _merge_entities(entities)


def _openai_extract_entities(memo: str, config: ToolkitConfig) -> list[dict[str, Any]]:
    body = {
        "model": config.openai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You extract public companies, issuers, securities, and tickers from investment memos. "
                    "Return only valid JSON. Prefer exchange tickers for public companies. "
                    "Classify assets across equities, indexes, futures, rates, credit, FX, commodities, macro indicators, ETFs, and crypto. "
                    "Use null ticker for non-company instruments; put their display code in symbol. Do not invent low-confidence tickers. "
                    "Read local context before treating short all-caps tokens as tickers; never extract AM or PM from timestamps like 04:26 PM."
                ),
            },
            {"role": "user", "content": json.dumps(_entity_extraction_payload(memo))},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {config.openai_api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen_request(
        request,
        timeout=config.request_timeout,
        allow_insecure_ssl_fallback=config.allow_insecure_ssl_fallback,
    ) as response:
        raw = json.loads(response.read().decode("utf-8"))
    return _parse_llm_entities(raw["choices"][0]["message"]["content"], "llm_openai")


def _anthropic_extract_entities(memo: str, config: ToolkitConfig) -> list[dict[str, Any]]:
    body = {
        "model": config.anthropic_model,
        "max_tokens": 700,
        "temperature": 0,
        "system": (
            "You extract public companies, issuers, securities, and tickers from investment memos. "
            "Return only valid JSON. Prefer exchange tickers for public companies. "
            "Classify assets across equities, indexes, futures, rates, credit, FX, commodities, macro indicators, ETFs, and crypto. "
            "Use null ticker for non-company instruments; put their display code in symbol. Do not invent low-confidence tickers. "
            "Read local context before treating short all-caps tokens as tickers; never extract AM or PM from timestamps like 04:26 PM."
        ),
        "messages": [
            {
                "role": "user",
                "content": "Return exactly one JSON object.\n\n" + json.dumps(_entity_extraction_payload(memo)),
            }
        ],
    }
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": config.anthropic_api_key or "",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen_request(
        request,
        timeout=config.request_timeout,
        allow_insecure_ssl_fallback=config.allow_insecure_ssl_fallback,
    ) as response:
        raw = json.loads(response.read().decode("utf-8"))
    content = "".join(block.get("text", "") for block in raw.get("content", []))
    return _parse_llm_entities(content, "llm_anthropic")


def _entity_extraction_payload(memo: str) -> dict[str, Any]:
    return {
        "task": "extract_financial_entities",
        "memo": memo,
        "instructions": [
            "Extract only entities that are explicitly mentioned in the memo.",
            "Return public-company tickers when confidently known.",
            "Use surrounding context before treating short all-caps tokens as tickers; AM/PM in publication times or timestamps are not financial entities.",
            "For non-company instruments, set ticker to null and fill symbol with the instrument code or short label.",
            "Classify each item using asset_class: single_name_equity, equity_index, equity_index_future, fund_etf, commodity, commodity_future, fx, rates, credit, macro_indicator, crypto, fixed_income, or other.",
            "Return JSON with an entities array.",
            "Each entity must contain name, ticker, symbol, entity_type, asset_class, confidence_0_to_1, and reason.",
        ],
        "schema": {
            "entities": [
                {
                    "name": "Apple Inc.",
                    "ticker": "AAPL",
                    "symbol": "AAPL",
                    "entity_type": "public_company",
                    "asset_class": "single_name_equity",
                    "confidence_0_to_1": 0.95,
                    "reason": "The memo explicitly mentions Apple.",
                },
                {
                    "name": "Consumer Price Index",
                    "ticker": None,
                    "symbol": "CPI",
                    "entity_type": "macro_indicator",
                    "asset_class": "macro_indicator",
                    "confidence_0_to_1": 0.9,
                    "reason": "The memo explicitly mentions CPI.",
                }
            ]
        },
    }


def _parse_llm_entities(text: str, source: str) -> list[dict[str, Any]]:
    parsed = _loads_json_object(text)
    raw_entities = parsed.get("entities", parsed if isinstance(parsed, list) else [])
    entities = []
    if not isinstance(raw_entities, list):
        return entities
    for item in raw_entities:
        if not isinstance(item, dict):
            continue
        raw_asset_class = str(item.get("asset_class") or "").strip().lower()
        entity_type = str(item.get("entity_type") or "").strip() or "public_company"
        symbol = _normalize_symbol(item.get("symbol") or item.get("identifier") or item.get("ticker") or "")
        known_asset = _KNOWN_SYMBOL_ASSETS.get(str(symbol or "").upper())
        if known_asset:
            known_name, asset_class, entity_type = known_asset
            ticker = None
        else:
            known_name = ""
            asset_class = normalize_asset_class(raw_asset_class or _asset_class_for_entity_type(entity_type), entity_type)
            ticker = _normalize_ticker(item.get("ticker")) if _is_public_company_asset(asset_class, entity_type) else None
        confidence = _clamp_float(item.get("confidence_0_to_1", item.get("confidence")), 0.55)
        name = str(known_name or item.get("name") or ticker or symbol or "").strip()
        if not name and not ticker and not symbol:
            continue
        entities.append(
            _entity(
                name=name,
                ticker=ticker,
                symbol=symbol or ticker,
                asset_class=asset_class,
                entity_type=entity_type,
                confidence=confidence,
                source=source,
                reason=str(item.get("reason") or ""),
            )
        )
    return entities


def _entity(
    name: str,
    ticker: str | None,
    confidence: float,
    source: str,
    entity_type: str = "public_company",
    asset_class: str | None = None,
    symbol: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    normalized_ticker = _normalize_ticker(ticker)
    normalized_asset_class = normalize_asset_class(asset_class or _asset_class_for_entity_type(entity_type), entity_type)
    normalized_symbol = _normalize_symbol(symbol or normalized_ticker or name)
    return {
        "name": name,
        "ticker": normalized_ticker,
        "symbol": normalized_symbol,
        "entity_type": entity_type,
        "asset_class": normalized_asset_class,
        "confidence": round(float(confidence), 3),
        "source": source,
        "reason": reason,
    }


def _merge_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in entities:
        ticker = _normalize_ticker(item.get("ticker"))
        symbol = _normalize_symbol(item.get("symbol") or ticker or item.get("name"))
        name = str(item.get("name") or ticker or symbol or "").strip()
        if not name and not ticker and not symbol:
            continue
        normalized = dict(item)
        normalized["ticker"] = ticker
        normalized["symbol"] = symbol
        normalized["name"] = name
        normalized["asset_class"] = normalize_asset_class(
            normalized.get("asset_class") or _asset_class_for_entity_type(str(normalized.get("entity_type") or "")),
            normalized.get("entity_type"),
        )
        key = f"{normalized['asset_class']}:{ticker or symbol or name.lower()}"
        existing = merged.get(key)
        if not existing:
            merged[key] = normalized
            continue
        if normalized.get("confidence", 0) > existing.get("confidence", 0):
            normalized["source"] = _join_sources(existing.get("source"), normalized.get("source"))
            merged[key] = normalized
        else:
            existing["source"] = _join_sources(existing.get("source"), normalized.get("source"))
    return sorted(merged.values(), key=lambda item: item.get("confidence", 0), reverse=True)


def _filter_ambiguous_entities(entities: list[dict[str, Any]], memo: str) -> tuple[list[dict[str, Any]], list[str]]:
    filtered: list[dict[str, Any]] = []
    notes: list[str] = []
    for item in entities:
        if not _is_public_company_entity(item):
            filtered.append(item)
            continue
        ticker = _normalize_ticker(item.get("ticker"))
        if is_contextual_non_ticker_token(ticker, memo):
            notes.append(f"filtered_contextual_non_ticker:{ticker}")
            continue
        if ticker in _AMBIGUOUS_TICKERS and not _has_explicit_ambiguous_ticker_context(ticker, item, memo):
            notes.append(f"filtered_ambiguous_ticker:{ticker}")
            continue
        filtered.append(item)
    return filtered, _dedupe(notes)


def is_contextual_non_ticker_token(token: Any, memo: str) -> bool:
    """Return true for uppercase tokens that are clearly metadata, not symbols."""
    ticker = _normalize_ticker(token)
    if ticker not in _TIME_SUFFIX_TICKERS:
        return False
    matches = list(
        re.finditer(
            rf"(?<![A-Za-z0-9]){re.escape(ticker)}(?![A-Za-z0-9])",
            memo,
            flags=re.IGNORECASE,
        )
    )
    return bool(matches) and all(_is_time_suffix_occurrence(memo, match.start()) for match in matches)


def _is_time_suffix_occurrence(memo: str, token_start: int) -> bool:
    left = memo[max(0, token_start - 16):token_start]
    return bool(_TIME_SUFFIX_RE.search(left))


def _has_explicit_ambiguous_ticker_context(ticker: str, entity: dict[str, Any], memo: str) -> bool:
    pattern = _AMBIGUOUS_TICKER_CONTEXT.get(ticker)
    if pattern and pattern.search(memo):
        return True
    entity_context = " ".join(
        str(entity.get(field) or "") for field in ["name", "reason", "source", "entity_type"]
    )
    return bool(pattern and pattern.search(entity_context))


def _filter_against_ticker_universe(
    entities: list[dict[str, Any]],
    config: ToolkitConfig,
) -> tuple[list[dict[str, Any]], list[str]]:
    universe = load_ticker_universe(config)
    notes = list(universe.notes)
    if not universe.loaded:
        return entities, notes

    filtered: list[dict[str, Any]] = []
    for item in entities:
        ticker = _normalize_ticker(item.get("ticker"))
        if not ticker or not _is_public_company_entity(item):
            filtered.append(item)
            continue
        record = universe.get(ticker)
        if not record:
            notes.append(f"filtered_unlisted_ticker:{ticker}")
            continue
        filtered.append(_enrich_with_ticker_record(item, record))
    if filtered != entities:
        notes.append(f"ticker_universe_source:{universe.source}")
    return filtered, _dedupe(notes)


def _filter_against_asset_universe(
    entities: list[dict[str, Any]],
    config: ToolkitConfig,
) -> tuple[list[dict[str, Any]], list[str]]:
    universe = load_asset_universe(config)
    notes = list(universe.notes)
    if not universe.loaded:
        return entities, notes

    filtered: list[dict[str, Any]] = []
    for item in entities:
        if _is_public_company_entity(item) or _is_unresolved_public_company(item):
            filtered.append(item)
            continue
        record = universe.match(item)
        if not record:
            asset_class = normalize_asset_class(item.get("asset_class"), item.get("entity_type"))
            symbol = item.get("symbol") or item.get("ticker") or item.get("name") or "unknown"
            notes.append(f"filtered_asset_universe:{asset_class}:{symbol}")
            continue
        filtered.append(_enrich_with_asset_record(item, record))
    if filtered != entities:
        notes.append(f"asset_universe_source:{universe.source}")
    return filtered, _dedupe(notes)


def _enrich_with_asset_record(entity: dict[str, Any], record: AssetUniverseRecord) -> dict[str, Any]:
    enriched = dict(entity)
    enriched["name"] = record.name
    enriched["symbol"] = record.symbol
    enriched["ticker"] = None
    enriched["asset_class"] = record.asset_class
    enriched["entity_type"] = record.entity_type
    enriched["source"] = _join_sources(enriched.get("source"), record.source)
    enriched["confidence"] = round(max(float(enriched.get("confidence", 0.0)), 0.78), 3)
    return enriched


def _enrich_with_ticker_record(entity: dict[str, Any], record: TickerRecord) -> dict[str, Any]:
    enriched = dict(entity)
    if not enriched.get("name") or enriched.get("name") == record.ticker:
        enriched["name"] = record.name
    enriched["ticker"] = record.ticker
    enriched["symbol"] = record.ticker
    enriched["asset_class"] = "single_name_equity"
    enriched["cik"] = record.cik
    enriched["exchange"] = record.exchange
    enriched["source"] = _join_sources(enriched.get("source"), record.source)
    enriched["confidence"] = round(max(float(enriched.get("confidence", 0.0)), 0.86), 3)
    return enriched


def _normalize_ticker(value: Any) -> str | None:
    if value is None:
        return None
    token = str(value).strip().upper().lstrip("$")
    if ":" in token:
        token = token.rsplit(":", 1)[-1].strip()
    token = token.replace("/", ".").replace(" ", "")
    if _TICKER_RE.match(token) and token not in _STOPWORDS:
        return token
    return None


def _normalize_symbol(value: Any) -> str | None:
    if value is None:
        return None
    symbol = re.sub(r"\s+", " ", str(value).strip())
    return symbol.upper() if symbol and len(symbol) <= 24 else symbol or None


def _asset_class_for_entity_type(entity_type: str) -> str:
    normalized = str(entity_type or "").strip().lower()
    mapping = {
        "public_company": "single_name_equity",
        "company": "single_name_equity",
        "equity": "single_name_equity",
        "stock": "single_name_equity",
        "issuer": "single_name_equity",
        "index": "equity_index",
        "future": "commodity_future",
        "futures": "commodity_future",
        "currency_pair": "fx",
        "currency_index": "fx",
        "interest_rate": "rates",
        "sovereign_rate": "rates",
        "macro": "macro_indicator",
    }
    return normalize_asset_class(mapping.get(normalized, normalized or "other"), entity_type)


def _is_public_company_asset(asset_class: str | None, entity_type: str | None = None) -> bool:
    normalized_asset = normalize_asset_class(asset_class, entity_type)
    normalized_type = str(entity_type or "").lower()
    return normalized_asset in {"single_name_equity", "public_company"} or normalized_type == "public_company"


def _is_public_company_entity(entity: dict[str, Any]) -> bool:
    return bool(entity.get("ticker")) and _is_public_company_asset(entity.get("asset_class"), entity.get("entity_type"))


def _is_unresolved_public_company(entity: dict[str, Any]) -> bool:
    if entity.get("ticker"):
        return False
    return _is_public_company_asset(entity.get("asset_class"), entity.get("entity_type"))


def _asset_groups(entities: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in entities:
        asset_class = str(item.get("asset_class") or "other")
        groups.setdefault(asset_class, []).append(item)
    return groups


def _loads_json_object(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    return json.loads(stripped)


def _clamp_float(value: Any, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _join_sources(first: Any, second: Any) -> str:
    sources = [str(item) for item in [first, second] if item]
    return "+".join(_dedupe(sources))
