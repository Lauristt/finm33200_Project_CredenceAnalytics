"""Official-source routing decisions for atomic financial claims."""

from __future__ import annotations

import re

from .asset_universe import normalize_asset_class
from .entity_extraction import heuristic_asset_classes_from_text
from .models import AtomicClaim
from .price_history import PRICE_HISTORY_ASSET_CLASSES, needs_historical_price_data


def route_sources(
    claim: str | AtomicClaim,
    official_only: bool = True,
    asset_classes: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict[str, object]:
    """Return the source adapters that should be tried for a claim."""
    text = claim.text if isinstance(claim, AtomicClaim) else claim
    lower = text.lower()
    detected_asset_classes = _asset_classes_for_routing(text, asset_classes)
    routes: list[str] = []
    reasons: list[str] = []

    if _contains(lower, "revenue", "sales", "income", "eps", "cash flow", "debt", "assets", "liabilities", "margin", "buyback", "repurchase", "leverage"):
        routes.extend(["sec_company_facts", "sec_recent_filings"])
        reasons.append("company financial statement claim")
    if needs_historical_price_data(text, detected_asset_classes):
        routes.append("historical_prices")
        reasons.append("asset-class-aware historical price action claim")
        if _allows_price_history(detected_asset_classes):
            routes.append("market_prices_vendor")
            reasons.append("supplemental market price source for traded asset")
    if _contains(
        lower,
        "stock price",
        "share price",
        "market cap",
        "market value",
        "s&p 500",
        "spx",
        "nasdaq 100",
        "ndx",
        "dow jones",
        "russell 2000",
        "record high",
        "closing high",
        "rally",
        "selloff",
        "outperformed",
        "underperformed",
    ) and _allows_price_history(detected_asset_classes):
        routes.extend(["historical_prices", "market_prices_vendor"])
        reasons.append("market price or index-performance claim")
    if _contains(lower, "xbrl", "ixbrl", "inline xbrl", "taxonomy", "dimensions", "ferc"):
        routes.extend(["xbrl_us_api", "arelle"])
        reasons.append("structured XBRL claim")
    if _contains(
        lower,
        "inflation",
        "cpi",
        "pce",
        "core pce",
        "fed funds",
        "federal funds",
        "sofr",
        "interest rate",
        "unemployment",
        "payrolls",
        "nonfarm payrolls",
        "nfp",
        "gdp",
        "treasury yield",
        "dgs2",
        "dgs10",
        "dgs30",
        "high yield spread",
        "high-yield spread",
        "hy oas",
        "investment grade spread",
        "corporate bond spread",
        "corporate spreads",
        "ig oas",
        "wti",
        "brent",
        "gold",
        "natural gas",
        "henry hub",
        "eur/usd",
        "usd/jpy",
        "yen",
        "gbp/usd",
        "sterling",
        "usd/cad",
        "usd/chf",
        "aud/usd",
        "dollar index",
        "trade weighted dollar",
    ):
        routes.append("fred")
        reasons.append("macro time-series claim")
    if _contains(lower, "bea", "nipa", "pce", "core pce", "personal income", "regional gdp", "industry accounts", "balance of payments"):
        routes.append("bea_api")
        reasons.append("BEA economic accounts claim")
    if _contains(lower, "bls", "cpi", "core cpi", "ppi", "payroll", "wage", "jolts", "productivity", "unemployment"):
        routes.append("bls_api")
        reasons.append("BLS labor or price statistics claim")
    if _contains(lower, "eia", "wti", "brent", "crude oil", "oil price", "petroleum", "natural gas", "henry hub", "gasoline", "inventory", "stockpiles", "energy"):
        routes.append("eia_api")
        reasons.append("EIA energy statistics claim")
    if _contains(lower, "z.1", "flow of funds", "financial accounts", "federal reserve ddp"):
        routes.append("federal_reserve_ddp")
        reasons.append("Federal Reserve Board statistical release claim")
    if _contains(lower, "federal debt", "public debt", "treasury", "fiscal deficit", "fiscal surplus", "deficit", "surplus"):
        routes.append("treasury_fiscal_data")
        reasons.append("U.S. fiscal data claim")
    if _contains(lower, "lei", "legal entity", "issuer", "counterparty", "subsidiary"):
        routes.append("gleif_entity")
        reasons.append("legal entity mapping claim")
    if _contains(lower, "figi", "isin", "cusip", "sedol", "security identifier", "ticker mapping"):
        routes.append("openfigi")
        reasons.append("security identifier mapping claim")
    if _contains(lower, "cftc", "cot", "commitments of traders", "futures", "open interest", "swaps"):
        routes.append("cftc_cot")
        reasons.append("CFTC derivatives positioning claim")
    if _contains(lower, "finra", "trace", "broker", "dealer", "fixed income", "corporate bond", "bond trade", "registration", "short interest"):
        routes.append("finra_query_api")
        reasons.append("FINRA regulatory dataset claim")
    if _contains(lower, "ofr", "stfm", "repo", "short-term funding", "money market"):
        routes.append("ofr_stfm")
        reasons.append("OFR funding-market claim")
    if _contains(lower, "ecb", "euro area", "eurozone", "hicp", "euro exchange rate", "euro reference rate"):
        routes.append("ecb_data_portal")
        reasons.append("ECB euro-area statistics claim")
    if _contains(lower, "bis", "cross-border banking", "international debt securities", "debt securities", "financial stability", "otc derivatives"):
        routes.append("bis_data_portal")
        reasons.append("BIS global financial statistics claim")
    if _contains(lower, "imf", "weo", "reserves", "fiscal monitor"):
        routes.append("imf_data_api")
        reasons.append("IMF international macro claim")
    if _contains(lower, "world bank", "wdi", "development indicator", "international debt statistics") or _world_bank_country_indicator_context(lower):
        routes.append("world_bank_indicators")
        reasons.append("World Bank indicator claim")
    if _contains(lower, "esma", "mifid", "ucits", "aifmd", "eu register"):
        routes.append("esma_registers")
        reasons.append("ESMA regulatory register claim")
    if _contains(lower, "bank of england", "boe", "sterling", "bank rate"):
        routes.append("bank_of_england")
        reasons.append("Bank of England statistics claim")
    if _contains(lower, "nasdaq data link", "quandl"):
        routes.append("nasdaq_data_link")
        reasons.append("Nasdaq Data Link platform claim")
    if not routes:
        reasons.append("no structured official route matched")

    if not official_only:
        routes.extend(["company_ir", "financial_media", "data_vendor"])

    return {
        "claim": text,
        "official_only": official_only,
        "asset_classes": detected_asset_classes,
        "routes": list(dict.fromkeys(routes)),
        "reasons": reasons,
    }


def _asset_classes_for_routing(text: str, asset_classes: list[str] | tuple[str, ...] | set[str] | None) -> list[str]:
    explicit = [normalize_asset_class(item) for item in (asset_classes or []) if item]
    inferred = heuristic_asset_classes_from_text(text)
    return list(dict.fromkeys([*explicit, *inferred]))


def _allows_price_history(asset_classes: list[str]) -> bool:
    return not asset_classes or bool(set(asset_classes) & PRICE_HISTORY_ASSET_CLASSES)


def _contains(text: str, *needles: str) -> bool:
    return any(re.search(rf"\b{re.escape(needle)}\b", text) for needle in needles)


def _world_bank_country_indicator_context(text: str) -> bool:
    has_indicator = _contains(
        text,
        "gdp",
        "gross domestic product",
        "population",
        "inflation",
        "cpi",
        "unemployment",
        "external debt",
        "international debt",
        "current account",
    )
    has_country = _contains(
        text,
        "all countries",
        "country",
        "countries",
        "china",
        "cn",
        "united states",
        "us",
        "usa",
        "japan",
        "united kingdom",
        "uk",
        "germany",
        "france",
        "india",
        "brazil",
        "world",
        "global",
    )
    return has_indicator and has_country
