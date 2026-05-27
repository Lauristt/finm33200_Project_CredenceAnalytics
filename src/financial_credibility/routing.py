"""Official-source routing decisions for atomic financial claims."""

from __future__ import annotations

import re

from .models import AtomicClaim


def route_sources(claim: str | AtomicClaim, official_only: bool = True) -> dict[str, object]:
    """Return the source adapters that should be tried for a claim."""
    text = claim.text if isinstance(claim, AtomicClaim) else claim
    lower = text.lower()
    routes: list[str] = []
    reasons: list[str] = []

    if _contains(lower, "revenue", "sales", "income", "eps", "cash flow", "debt", "assets", "liabilities", "margin", "buyback", "repurchase", "leverage"):
        routes.extend(["sec_company_facts", "sec_recent_filings"])
        reasons.append("company financial statement claim")
    if _contains(lower, "xbrl", "ixbrl", "inline xbrl", "taxonomy", "dimensions", "ferc"):
        routes.extend(["xbrl_us_api", "arelle"])
        reasons.append("structured XBRL claim")
    if _contains(lower, "inflation", "cpi", "consumer price", "fed funds", "interest rate",
                 "unemployment", "jobless", "payroll", "nonfarm", "gdp", "treasury yield",
                 "10-year", "10 year", "brent", "wti", "crude", "oil price", "gold",
                 "copper", "natural gas", "s&p 500", "s&p500", "dow jones", "nasdaq",
                 "eur/usd", "euro", "usd/jpy", "yen", "gbp/usd"):
        routes.append("fred")
        reasons.append("macro / commodity / index / FX time-series claim (FRED)")
    if _contains(lower, "bea", "nipa", "personal income", "regional gdp", "industry accounts", "balance of payments"):
        routes.append("bea_api")
        reasons.append("BEA economic accounts claim")
    if _contains(lower, "bls", "ppi", "payroll", "wage", "jolts", "productivity"):
        routes.append("bls_api")
        reasons.append("BLS labor or price statistics claim")
    if _contains(lower, "z.1", "flow of funds", "financial accounts", "federal reserve ddp"):
        routes.append("federal_reserve_ddp")
        reasons.append("Federal Reserve Board statistical release claim")
    if _contains(lower, "federal debt", "public debt", "treasury", "fiscal", "deficit", "surplus"):
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
    if _contains(lower, "ofr", "stfm", "repo", "short-term funding", "money market"):
        routes.append("ofr_stfm")
        reasons.append("OFR funding-market claim")
    if _contains(lower, "ecb", "euro area", "eurozone", "hicp"):
        routes.append("ecb_data_portal")
        reasons.append("ECB euro-area statistics claim")
    if _contains(lower, "bis", "cross-border banking", "international debt securities", "financial stability"):
        routes.append("bis_data_portal")
        reasons.append("BIS global financial statistics claim")
    if _contains(lower, "imf", "weo", "reserves", "fiscal monitor"):
        routes.append("imf_data_api")
        reasons.append("IMF international macro claim")
    if _contains(lower, "world bank", "wdi", "development indicator", "international debt statistics"):
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
        routes.extend(["sec_company_facts", "sec_recent_filings"])
        reasons.append("default official company-source route")

    if not official_only:
        routes.extend(["company_ir", "financial_media", "data_vendor"])

    return {
        "claim": text,
        "official_only": official_only,
        "routes": list(dict.fromkeys(routes)),
        "reasons": reasons,
    }


def _contains(text: str, *needles: str) -> bool:
    return any(re.search(rf"\b{re.escape(needle)}\b", text) for needle in needles)
