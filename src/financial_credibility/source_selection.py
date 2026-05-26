"""Source catalog, LLM-assisted source selection, and policy validation."""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .claims import decompose_claims
from .config import ToolkitConfig
from .models import AtomicClaim, LicenseTag, SourceTier
from .net import urlopen_request
from .routing import route_sources


@dataclass(frozen=True)
class SourceCatalogEntry:
    """One selectable source/tool with coverage and governance metadata."""

    source_id: str
    name: str
    provider_name: str
    authority_tier: SourceTier
    license_tag: LicenseTag
    is_official_primary: bool
    brief_description: str
    detail_file: str
    coverage: list[str]
    best_for: list[str]
    not_for: list[str] = field(default_factory=list)
    required_inputs: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    adapter_status: str = "implemented"
    is_runtime_selectable: bool = True

    def to_prompt_dict(self) -> dict[str, Any]:
        """Return the compact card used for first-pass source selection."""
        return {
            "source_id": self.source_id,
            "name": self.name,
            "authority_tier": self.authority_tier.value,
            "license_tag": self.license_tag.value,
            "is_official_primary": self.is_official_primary,
            "brief_description": self.brief_description,
            "detail_available": bool(self.detail_file),
            "required_inputs": self.required_inputs,
            "adapter_status": self.adapter_status,
            "is_runtime_selectable": self.is_runtime_selectable,
        }

    def to_detail_prompt_dict(self) -> dict[str, Any]:
        """Return the richer card used only after a source survives first pass."""
        payload = self.to_prompt_dict()
        payload.update(
            {
                "detail_file": self.detail_file,
                "coverage": self.coverage,
                "best_for": self.best_for,
                "not_for": self.not_for,
                "detail_markdown": load_source_detail(self.source_id),
            }
        )
        return payload


SOURCE_CATALOG: list[SourceCatalogEntry] = [
    SourceCatalogEntry(
        source_id="sec_company_facts",
        name="SEC Company Facts",
        provider_name="sec_company_facts",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        is_official_primary=True,
        brief_description="Official SEC extracted XBRL company facts for US public-company reported financial statement metrics.",
        detail_file="sec_company_facts.md",
        coverage=["US public company XBRL facts", "revenue", "net income", "EPS", "cash flow", "assets", "debt"],
        best_for=["historical reported financial metrics", "10-K and 10-Q numeric verification"],
        not_for=["MD&A explanations", "earnings call commentary", "market prices"],
        required_inputs=["ticker_or_cik", "metric_hint"],
        keywords=["revenue", "sales", "income", "eps", "cash flow", "assets", "debt", "margin", "financial statement"],
    ),
    SourceCatalogEntry(
        source_id="sec_recent_filings",
        name="SEC Recent Filings",
        provider_name="sec_recent_filings",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        is_official_primary=True,
        brief_description="Official SEC submissions feed and filing metadata for 10-K, 10-Q, 8-K, and related disclosure context.",
        detail_file="sec_recent_filings.md",
        coverage=["10-K", "10-Q", "8-K", "filing dates", "official filing links", "disclosure text"],
        best_for=["filing context", "event verification", "MD&A or management explanation follow-up"],
        not_for=["macro series", "market price"],
        required_inputs=["ticker_or_cik"],
        keywords=["10-k", "10-q", "8-k", "filed", "filing", "mda", "management", "buyback", "repurchase", "guidance"],
    ),
    SourceCatalogEntry(
        source_id="fred",
        name="FRED Macro Series",
        provider_name="fred",
        authority_tier=SourceTier.T2,
        license_tag=LicenseTag.THIRD_PARTY_RESTRICTED,
        is_official_primary=True,
        brief_description="St. Louis Fed FRED/ALFRED economic time-series API for macro observations and vintage-aware checks.",
        detail_file="fred.md",
        coverage=["inflation", "CPI", "interest rates", "fed funds", "GDP", "unemployment", "Treasury yields"],
        best_for=["US macro time-series verification", "release/observation metadata"],
        not_for=["company financial statements"],
        required_inputs=["series_hint"],
        keywords=["inflation", "cpi", "interest", "fed funds", "rate", "gdp", "unemployment", "yield"],
    ),
    SourceCatalogEntry(
        source_id="treasury_fiscal_data",
        name="U.S. Treasury Fiscal Data",
        provider_name="treasury_fiscal_data",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        is_official_primary=True,
        brief_description="U.S. Treasury Fiscal Data API for federal debt, fiscal, rates, and Treasury securities datasets.",
        detail_file="treasury_fiscal_data.md",
        coverage=["federal debt", "debt to the penny", "public debt", "fiscal data"],
        best_for=["US federal debt and fiscal metric verification"],
        not_for=["company fundamentals", "equity prices"],
        required_inputs=["dataset_hint"],
        keywords=["federal debt", "public debt", "fiscal", "treasury debt", "deficit", "surplus"],
    ),
    SourceCatalogEntry(
        source_id="gleif_entity",
        name="GLEIF LEI Records",
        provider_name="gleif_entity",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.CC0,
        is_official_primary=True,
        brief_description="GLEIF LEI records for legal-entity identity resolution, ownership links, and identifier mapping.",
        detail_file="gleif_entity.md",
        coverage=["LEI", "legal entity identity", "issuer identity", "entity names"],
        best_for=["entity resolution", "counterparty or issuer mapping"],
        not_for=["financial metric values"],
        required_inputs=["entity_name_or_identifier"],
        keywords=["lei", "legal entity", "issuer", "counterparty", "entity identity"],
    ),
    SourceCatalogEntry(
        source_id="xbrl_us_api",
        name="XBRL US API",
        provider_name="xbrl_us_api",
        authority_tier=SourceTier.T2,
        license_tag=LicenseTag.THIRD_PARTY_RESTRICTED,
        is_official_primary=False,
        brief_description="XBRL US Public Filings Database API for high-granularity SEC and FERC filed XBRL facts.",
        detail_file="xbrl_us_api.md",
        coverage=["SEC filed XBRL", "FERC filed XBRL", "taxonomy metadata", "dimensions", "facts"],
        best_for=["enhanced XBRL fact search", "cross-company taxonomy-aware comparisons", "FERC utility filings"],
        not_for=["primary source when direct SEC evidence is sufficient", "macro series", "market prices"],
        required_inputs=["entity_or_cik", "concept_or_taxonomy_hint"],
        keywords=["xbrl", "taxonomy", "dimension", "ferc", "hypercube", "fact search"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="arelle",
        name="Arelle XBRL Parser",
        provider_name="arelle",
        authority_tier=SourceTier.T2,
        license_tag=LicenseTag.UNKNOWN,
        is_official_primary=False,
        brief_description="Open-source XBRL/iXBRL parser and validator for local filing validation and taxonomy-aware extraction.",
        detail_file="arelle.md",
        coverage=["XBRL parsing", "Inline XBRL", "taxonomy validation", "SEC EFM validation", "XBRL dimensions"],
        best_for=["local iXBRL parsing", "filing validation", "human-review filing inspection support"],
        not_for=["external data retrieval by itself", "macro observations", "market prices"],
        required_inputs=["filing_url_or_local_xbrl"],
        keywords=["arelle", "ixbrl", "inline xbrl", "validation", "taxonomy", "efm"],
        adapter_status="planned_parser",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="federal_reserve_ddp",
        name="Federal Reserve DDP / Z.1",
        provider_name="federal_reserve_ddp",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        is_official_primary=True,
        brief_description="Federal Reserve Board Data Download Program for selected Board statistical releases, including Z.1 Financial Accounts.",
        detail_file="federal_reserve_ddp.md",
        coverage=["Federal Reserve statistical releases", "Z.1 Financial Accounts", "G.17", "H.8", "G.19"],
        best_for=["Board-release-specific time series", "financial accounts", "flow of funds", "release-file replay"],
        not_for=["company financial statements", "security identifiers"],
        required_inputs=["release_or_series_hint"],
        keywords=["federal reserve", "ddp", "z.1", "financial accounts", "flow of funds", "g.17", "h.8", "g.19"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="bea_api",
        name="BEA API",
        provider_name="bea_api",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        is_official_primary=True,
        brief_description="Bureau of Economic Analysis API for published US economic statistics and related metadata.",
        detail_file="bea_api.md",
        coverage=["GDP", "NIPA", "industry accounts", "regional data", "international transactions", "input-output"],
        best_for=["US GDP and national accounts", "industry and regional macro verification", "BEA release metadata"],
        not_for=["company filings", "ticker identity", "market prices"],
        required_inputs=["dataset_name", "table_or_series_hint", "period"],
        keywords=["bea", "gdp", "nipa", "personal income", "industry", "regional", "balance of payments", "input-output"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="bls_api",
        name="BLS Public Data API",
        provider_name="bls_api",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        is_official_primary=True,
        brief_description="Bureau of Labor Statistics API for published historical time series from BLS surveys.",
        detail_file="bls_api.md",
        coverage=["CPI", "PPI", "employment", "unemployment", "wages", "job openings", "productivity"],
        best_for=["inflation and labor-market verification", "BLS survey time series", "published historical observations"],
        not_for=["company financial statements", "securities identifiers", "Treasury debt"],
        required_inputs=["bls_series_id_or_topic", "period"],
        keywords=["bls", "cpi", "ppi", "jobs", "payroll", "wage", "employment", "unemployment", "jolts", "productivity"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="cftc_cot",
        name="CFTC COT Public Reporting",
        provider_name="cftc_cot",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        is_official_primary=True,
        brief_description="CFTC Commitments of Traders public reporting data and API for futures and options market positioning.",
        detail_file="cftc_cot.md",
        coverage=["COT reports", "futures positions", "options on futures", "open interest", "trader categories"],
        best_for=["futures positioning claims", "market structure checks", "weekly COT trend verification"],
        not_for=["cash equity fundamentals", "company filings", "macroeconomic aggregates"],
        required_inputs=["market_or_contract", "report_date"],
        keywords=["cftc", "cot", "commitments of traders", "futures", "open interest", "swaps", "positions"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="finra_query_api",
        name="FINRA Query API",
        provider_name="finra_query_api",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.THIRD_PARTY_RESTRICTED,
        is_official_primary=True,
        brief_description="FINRA Query API for equity, fixed income, registration, and other regulatory datasets through a standard interface.",
        detail_file="finra_query_api.md",
        coverage=["equity regulatory data", "fixed income data", "registration data", "TRACE-related datasets"],
        best_for=["broker-dealer or fixed-income regulatory checks", "FINRA dataset queries", "large filtered regulatory datasets"],
        not_for=["company-reported financial statements", "macro series"],
        required_inputs=["dataset_group", "dataset_name", "filters"],
        keywords=["finra", "trace", "broker", "dealer", "fixed income", "registration", "short interest"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="ofr_stfm",
        name="OFR Short-term Funding Monitor",
        provider_name="ofr_stfm",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        is_official_primary=True,
        brief_description="Office of Financial Research API for Short-term Funding Monitor series and related market digests.",
        detail_file="ofr_stfm.md",
        coverage=["short-term funding", "repo", "secured funding", "unsecured funding", "money markets"],
        best_for=["systemic-risk and funding-market time-series checks", "OFR STFM series data", "repo-market monitoring"],
        not_for=["company financial statements", "equity prices"],
        required_inputs=["series_or_dataset_hint", "period"],
        keywords=["ofr", "stfm", "repo", "short-term funding", "secured funding", "unsecured funding", "money market"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="openfigi",
        name="OpenFIGI API",
        provider_name="openfigi",
        authority_tier=SourceTier.T2,
        license_tag=LicenseTag.UNKNOWN,
        is_official_primary=False,
        brief_description="OpenFIGI API for mapping tickers, ISINs, CUSIPs, SEDOLs, and other identifiers to FIGI instrument identifiers.",
        detail_file="openfigi.md",
        coverage=["FIGI", "ticker mapping", "ISIN", "CUSIP", "SEDOL", "instrument identity"],
        best_for=["security identifier resolution", "ticker ambiguity checks", "instrument-level mapping"],
        not_for=["financial statement values", "macro observations", "legal entity LEI records"],
        required_inputs=["identifier_type", "identifier_value"],
        keywords=["figi", "openfigi", "isin", "cusip", "sedol", "ticker mapping", "security identifier"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="ecb_data_portal",
        name="ECB Data Portal API",
        provider_name="ecb_data_portal",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        is_official_primary=True,
        brief_description="European Central Bank SDMX API for euro-area official statistics and metadata.",
        detail_file="ecb_data_portal.md",
        coverage=["euro area", "ECB statistics", "exchange rates", "interest rates", "banking", "payments", "HICP"],
        best_for=["euro-area macro and financial statistics", "ECB release-aligned time series", "SDMX metadata checks"],
        not_for=["US company filings", "US labor data"],
        required_inputs=["dataflow", "sdmx_key", "period"],
        keywords=["ecb", "euro", "euro area", "hicp", "exchange rate", "banking", "payments", "sdmx"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="bis_data_portal",
        name="BIS Data Portal API",
        provider_name="bis_data_portal",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        is_official_primary=True,
        brief_description="BIS SDMX RESTful API for public BIS statistical data and metadata.",
        detail_file="bis_data_portal.md",
        coverage=["international banking", "debt securities", "liquidity", "financial stability", "cross-border banking"],
        best_for=["global financial stability statistics", "cross-border banking checks", "international debt securities"],
        not_for=["single-company SEC facts", "US labor statistics"],
        required_inputs=["dataflow", "sdmx_key", "period"],
        keywords=["bis", "international banking", "cross-border", "debt securities", "liquidity", "financial stability", "sdmx"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="imf_data_api",
        name="IMF Data API",
        provider_name="imf_data_api",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.THIRD_PARTY_RESTRICTED,
        is_official_primary=True,
        brief_description="IMF SDMX APIs for importing IMF datasets into data systems and applications.",
        detail_file="imf_data_api.md",
        coverage=["IMF macro data", "WEO", "BOP", "CPI", "reserves", "fiscal monitor"],
        best_for=["cross-country macro checks", "IMF dataset verification", "global economic comparisons"],
        not_for=["US SEC filing facts", "security identifiers"],
        required_inputs=["dataset_or_dataflow", "country_or_series_key", "period"],
        keywords=["imf", "weo", "balance of payments", "bop", "reserves", "fiscal monitor", "country", "sdmx"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="world_bank_indicators",
        name="World Bank Indicators API",
        provider_name="world_bank_indicators",
        authority_tier=SourceTier.T2,
        license_tag=LicenseTag.CC_BY,
        is_official_primary=True,
        brief_description="World Bank Indicators API for time-series indicators across World Bank databases.",
        detail_file="world_bank_indicators.md",
        coverage=["World Development Indicators", "country indicators", "international debt", "development metrics"],
        best_for=["long-run country comparisons", "development and macro indicators", "World Bank database checks"],
        not_for=["company filings", "market prices"],
        required_inputs=["country", "indicator_id", "period"],
        keywords=["world bank", "wdi", "indicator", "country", "development", "international debt"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="esma_registers",
        name="ESMA Registers",
        provider_name="esma_registers",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        is_official_primary=True,
        brief_description="ESMA registers and machine-to-machine services for EU financial-market regulatory datasets.",
        detail_file="esma_registers.md",
        coverage=["EU registers", "MiFID", "UCITS", "AIFMD", "benchmarks", "sanctions", "positions"],
        best_for=["EU regulatory registration checks", "market venue/product register lookups", "ESMA-maintained datasets"],
        not_for=["US SEC filings", "macro time series"],
        required_inputs=["register_name", "query_fields"],
        keywords=["esma", "mifid", "ucits", "aifmd", "eu register", "benchmark", "sanctions"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="bank_of_england",
        name="Bank of England Database",
        provider_name="bank_of_england",
        authority_tier=SourceTier.T1,
        license_tag=LicenseTag.PUBLIC_OFFICIAL,
        is_official_primary=True,
        brief_description="Bank of England statistical database for UK monetary, financial, interest-rate, and exchange-rate time series.",
        detail_file="bank_of_england.md",
        coverage=["UK rates", "sterling", "monetary statistics", "banking", "exchange rates", "credit"],
        best_for=["UK macro-financial checks", "Bank of England series verification", "sterling and rates claims"],
        not_for=["US company facts", "US fiscal data"],
        required_inputs=["series_or_topic", "period"],
        keywords=["bank of england", "boe", "uk", "sterling", "bank rate", "monetary", "exchange rate"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="nasdaq_data_link",
        name="Nasdaq Data Link",
        provider_name="nasdaq_data_link",
        authority_tier=SourceTier.T3,
        license_tag=LicenseTag.THIRD_PARTY_RESTRICTED,
        is_official_primary=False,
        brief_description="Nasdaq Data Link API platform for free and premium financial and alternative datasets.",
        detail_file="nasdaq_data_link.md",
        coverage=["financial datasets", "alternative data", "market data", "economic data", "premium datasets"],
        best_for=["supplemental data discovery", "licensed platform datasets", "non-official data enrichment"],
        not_for=["primary official evidence when a direct regulator or agency API exists"],
        required_inputs=["dataset_code", "api_key_or_subscription"],
        keywords=["nasdaq data link", "quandl", "premium data", "alternative data", "dataset code"],
        adapter_status="planned",
        is_runtime_selectable=False,
    ),
    SourceCatalogEntry(
        source_id="historical_prices",
        name="Historical Price Series",
        provider_name="historical_prices",
        authority_tier=SourceTier.T3,
        license_tag=LicenseTag.THIRD_PARTY_RESTRICTED,
        is_official_primary=False,
        brief_description="Supplemental historical equity price source group for price, return, volatility, and drawdown claims.",
        detail_file="historical_prices.md",
        coverage=["daily stock prices", "returns", "volatility", "oscillation", "drawdown"],
        best_for=["price action and relative performance claims"],
        not_for=["reported fundamentals", "official filing facts"],
        required_inputs=["ticker", "date_window"],
        keywords=["price", "stock", "return", "volatility", "oscillating", "range-bound", "underperformed", "outperformed"],
    ),
    SourceCatalogEntry(
        source_id="company_fundamentals_vendor",
        name="Financial Data Vendor Fundamentals",
        provider_name="company_fundamentals_vendor",
        authority_tier=SourceTier.T3,
        license_tag=LicenseTag.THIRD_PARTY_RESTRICTED,
        is_official_primary=False,
        brief_description="Supplemental financial-data vendor group for company profiles, ratios, and basic fundamentals.",
        detail_file="company_fundamentals_vendor.md",
        coverage=["company profile", "income statement snippets", "financial ratios", "basic metrics"],
        best_for=["supplemental company context when official sources are insufficient"],
        not_for=["primary evidence for official reported facts"],
        required_inputs=["ticker"],
        keywords=["profile", "ratio", "market cap", "valuation", "overview"],
    ),
    SourceCatalogEntry(
        source_id="market_prices_vendor",
        name="Market Price Vendors",
        provider_name="market_prices_vendor",
        authority_tier=SourceTier.T3,
        license_tag=LicenseTag.THIRD_PARTY_RESTRICTED,
        is_official_primary=False,
        brief_description="Supplemental market-data vendor group for latest quotes and end-of-day price checks.",
        detail_file="market_prices_vendor.md",
        coverage=["latest EOD quote", "recent market prices"],
        best_for=["supplemental market price checks"],
        not_for=["primary official facts", "financial statement metrics"],
        required_inputs=["ticker"],
        keywords=["latest price", "eod", "quote", "market price"],
    ),
    SourceCatalogEntry(
        source_id="serper_web",
        name="Web Search",
        provider_name="serper_web",
        authority_tier=SourceTier.T4,
        license_tag=LicenseTag.UNKNOWN,
        is_official_primary=False,
        brief_description="Supplemental web search for discovery when official structured APIs cannot directly answer a claim.",
        detail_file="serper_web.md",
        coverage=["web pages", "news", "company IR pages", "supplemental discovery"],
        best_for=["finding secondary context or official page URLs when structured APIs are insufficient"],
        not_for=["primary evidence when a direct official API exists"],
        required_inputs=["query"],
        keywords=["news", "memo", "statement", "reported by", "source"],
    ),
]


def source_catalog(include_planned: bool = False) -> list[SourceCatalogEntry]:
    """Return source catalog entries, hiding planned adapters by default."""
    if include_planned:
        return SOURCE_CATALOG
    return [entry for entry in SOURCE_CATALOG if entry.is_runtime_selectable]


def source_catalog_dicts(include_planned: bool = False) -> list[dict[str, Any]]:
    return [entry.to_prompt_dict() for entry in source_catalog(include_planned=include_planned)]


def load_source_detail(source_id: str) -> str:
    """Load the local long-form source description for progressive disclosure."""
    entry = _catalog_by_id(include_planned=True).get(source_id)
    if not entry or not entry.detail_file:
        return ""
    path = _source_description_dir() / entry.detail_file
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def selected_source_details(source_ids: list[str]) -> list[dict[str, Any]]:
    """Return detailed descriptions only for selected sources."""
    details = []
    for source_id in dict.fromkeys(str(item) for item in source_ids):
        entry = _catalog_by_id().get(source_id)
        if not entry:
            continue
        details.append(
            {
                "source_id": entry.source_id,
                "name": entry.name,
                "detail_file": entry.detail_file,
                "detail_markdown": load_source_detail(entry.source_id),
            }
        )
    return details


def candidate_sources_for_claim(claim: str | AtomicClaim, top_k: int = 6) -> list[dict[str, Any]]:
    """Find likely source candidates from the source catalog."""
    return candidate_sources_for_claim_with_options(claim, top_k=top_k)


def candidate_sources_for_claim_with_options(
    claim: str | AtomicClaim,
    top_k: int = 6,
    include_planned: bool = False,
) -> list[dict[str, Any]]:
    """Find likely source candidates, optionally including planned-but-not-callable sources."""
    text = claim.text if isinstance(claim, AtomicClaim) else claim
    route_ids = set(route_sources(text)["routes"])
    scored = []
    for entry in source_catalog(include_planned=include_planned):
        score = _catalog_score(text, entry)
        has_relevance = score > 0
        if entry.source_id in route_ids or entry.provider_name in route_ids:
            score += 2.5
            has_relevance = True
        if has_relevance:
            scored.append((score, entry))
    if not scored:
        scored = [(0.2, entry) for entry in source_catalog(include_planned=include_planned) if entry.is_official_primary][:3]
    scored.sort(key=lambda item: (item[0], item[1].is_official_primary, _tier_rank(item[1].authority_tier)), reverse=True)
    return [
        {
            **entry.to_prompt_dict(),
            "candidate_score": round(score, 3),
        }
        for score, entry in scored[:top_k]
    ]


def select_sources_for_claims(
    claims: list[AtomicClaim] | str,
    config: ToolkitConfig | None = None,
    candidate_limit: int = 6,
    max_selected: int = 4,
    include_planned: bool = False,
) -> list[dict[str, Any]]:
    """Select sources for each claim through LLM choice plus policy validation."""
    atoms = decompose_claims(claims) if isinstance(claims, str) else claims
    return [
        select_sources_for_claim(
            claim=atom,
            config=config,
            candidate_limit=candidate_limit,
            max_selected=max_selected,
            include_planned=include_planned,
        )
        for atom in atoms
    ]


def select_sources_for_claim(
    claim: str | AtomicClaim,
    config: ToolkitConfig | None = None,
    candidate_limit: int = 6,
    max_selected: int = 4,
    include_planned: bool = False,
) -> dict[str, Any]:
    """Select sources with brief-first, details-for-selected progressive disclosure."""
    text = claim.text if isinstance(claim, AtomicClaim) else claim
    claim_id = claim.claim_id if isinstance(claim, AtomicClaim) else None
    candidates = candidate_sources_for_claim_with_options(text, top_k=candidate_limit, include_planned=include_planned)
    cfg = config or ToolkitConfig.from_env()
    raw_selection, method, notes = _llm_or_fallback_selection(text, candidates, cfg, stage="brief")
    initial = validate_source_selection(text, candidates, raw_selection, max_selected=max_selected)
    loaded_details = selected_source_details(initial["selected_sources"])
    detail_candidates = _detail_candidates(candidates, initial["selected_sources"])
    refined_selection, refine_method, refine_notes = _refine_selection_with_details(
        text,
        detail_candidates,
        _selection_with_validated_sources(raw_selection, initial["selected_sources"]),
        cfg,
    )
    validated = validate_source_selection(text, candidates, refined_selection, max_selected=max_selected)
    final_details = selected_source_details(validated["selected_sources"])
    method = _combined_method(method, refine_method)
    return {
        "claim_id": claim_id,
        "claim": text,
        "candidates": candidates,
        "disclosure_stages": {
            "stage_1": "brief_candidate_cards",
            "stage_1_includes_planned_sources": include_planned,
            "stage_1_candidate_count": len(candidates),
            "stage_1_selected_sources": initial["selected_sources"],
            "stage_2": "details_for_selected_sources",
            "stage_2_loaded_source_ids": [item["source_id"] for item in loaded_details],
            "stage_2_loaded_detail_files": [item["detail_file"] for item in loaded_details if item.get("detail_file")],
        },
        "selected_source_details": final_details,
        "selected_sources": validated["selected_sources"],
        "selected_provider_names": selected_provider_names(validated["selected_sources"]),
        "rationale": refined_selection.get("rationale", raw_selection.get("rationale", validated.get("rationale", ""))),
        "confidence": float(
            refined_selection.get(
                "confidence",
                refined_selection.get(
                    "confidence_0_to_1",
                    raw_selection.get("confidence", raw_selection.get("confidence_0_to_1", validated["confidence"])),
                ),
            )
        ),
        "needs_cross_check": bool(
            refined_selection.get(
                "needs_cross_check",
                raw_selection.get("needs_cross_check", len(validated["selected_sources"]) > 1),
            )
        ),
        "method": method,
        "policy_notes": notes + refine_notes + initial["policy_notes"] + validated["policy_notes"],
    }


def validate_source_selection(
    claim: str,
    candidates: list[dict[str, Any]],
    raw_selection: dict[str, Any],
    max_selected: int = 4,
) -> dict[str, Any]:
    """Keep selected sources inside candidate/catalog policy and official-source guardrails."""
    candidate_ids = [str(item["source_id"]) for item in candidates]
    by_id = {str(item["source_id"]): item for item in candidates}
    requested = raw_selection.get("selected_sources") or raw_selection.get("sources") or []
    if isinstance(requested, str):
        requested = [requested]
    selected = []
    policy_notes = []
    for source_id in requested:
        normalized = str(source_id)
        if normalized not in by_id:
            policy_notes.append(f"discarded_unknown_source:{normalized}")
            continue
        if normalized not in selected:
            selected.append(normalized)

    if not selected:
        selected = candidate_ids[: min(2, len(candidate_ids))]
        policy_notes.append("fallback_selected_top_candidates")

    official_candidates = [item for item in candidates if item.get("is_official_primary")]
    has_official_selected = any(by_id[source_id].get("is_official_primary") for source_id in selected)
    if _needs_official_primary(claim) and official_candidates and not has_official_selected:
        official_source = str(official_candidates[0]["source_id"])
        selected.insert(0, official_source)
        policy_notes.append(f"added_official_primary:{official_source}")

    selected = list(dict.fromkeys(selected))[:max_selected]
    return {
        "selected_sources": selected,
        "confidence": 0.65,
        "rationale": "Policy-validated catalog source selection.",
        "policy_notes": policy_notes,
    }


def selected_source_ids(selection_plan: list[dict[str, Any]]) -> list[str]:
    ids = []
    for selection in selection_plan:
        ids.extend(selection.get("selected_sources", []))
    return list(dict.fromkeys(str(item) for item in ids))


def selected_provider_names(source_ids: list[str]) -> list[str]:
    providers = []
    for source_id in source_ids:
        entry = _catalog_by_id().get(source_id)
        if entry:
            if entry.is_runtime_selectable:
                providers.append(entry.provider_name)
    return list(dict.fromkeys(providers))


def selected_provider_names_from_plan(selection_plan: list[dict[str, Any]]) -> list[str]:
    providers = []
    for selection in selection_plan:
        providers.extend(selection.get("selected_provider_names") or selected_provider_names(selection.get("selected_sources", [])))
    return list(dict.fromkeys(str(item) for item in providers))


def _llm_or_fallback_selection(
    claim: str,
    candidates: list[dict[str, Any]],
    config: ToolkitConfig,
    stage: str = "brief",
) -> tuple[dict[str, Any], str, list[str]]:
    provider = config.llm_provider.lower()
    try:
        if provider in {"auto", "openai"} and config.openai_api_key and config.openai_model:
            return _openai_select(claim, candidates, config, stage=stage), f"openai_{stage}", []
        if provider in {"auto", "anthropic"} and config.anthropic_api_key and config.anthropic_model:
            return _anthropic_select(claim, candidates, config, stage=stage), f"anthropic_{stage}", []
    except Exception as exc:
        fallback = _fallback_selection(claim, candidates)
        return fallback, "deterministic_fallback", [f"llm_source_selection_fallback:{exc}"]
    return _fallback_selection(claim, candidates), "deterministic_fallback", []


def _fallback_selection(claim: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [str(item["source_id"]) for item in candidates[:3]]
    return {
        "selected_sources": selected,
        "rationale": "Selected top source-catalog candidates by keyword coverage and source policy.",
        "confidence": 0.62,
        "needs_cross_check": len(selected) > 1,
    }


def _openai_select(
    claim: str,
    candidates: list[dict[str, Any]],
    config: ToolkitConfig,
    stage: str = "brief",
    previous_selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = {
        "model": config.openai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You select financial verification data sources. "
                    "Return only valid JSON. Select source_id values only from the provided candidates."
                ),
            },
            {"role": "user", "content": json.dumps(_selector_payload(claim, candidates, stage, previous_selection))},
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
    return _loads_json_object(raw["choices"][0]["message"]["content"])


def _anthropic_select(
    claim: str,
    candidates: list[dict[str, Any]],
    config: ToolkitConfig,
    stage: str = "brief",
    previous_selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = {
        "model": config.anthropic_model,
        "max_tokens": 500,
        "temperature": 0,
        "system": (
            "You select financial verification data sources. "
            "Return only valid JSON. Select source_id values only from the provided candidates."
        ),
        "messages": [
            {
                "role": "user",
                "content": "Return exactly one JSON object.\n\n"
                + json.dumps(_selector_payload(claim, candidates, stage, previous_selection)),
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
    return _loads_json_object(content)


def _refine_selection_with_details(
    claim: str,
    detail_candidates: list[dict[str, Any]],
    previous_selection: dict[str, Any],
    config: ToolkitConfig,
) -> tuple[dict[str, Any], str, list[str]]:
    if not detail_candidates:
        return previous_selection, "no_detail_refinement", []
    provider = config.llm_provider.lower()
    try:
        if provider in {"auto", "openai"} and config.openai_api_key and config.openai_model:
            refined = _openai_select(claim, detail_candidates, config, stage="detail_refine", previous_selection=previous_selection)
            return refined, "openai_detail_refine", []
        if provider in {"auto", "anthropic"} and config.anthropic_api_key and config.anthropic_model:
            refined = _anthropic_select(
                claim,
                detail_candidates,
                config,
                stage="detail_refine",
                previous_selection=previous_selection,
            )
            return refined, "anthropic_detail_refine", []
    except Exception as exc:
        return previous_selection, "detail_refinement_fallback", [f"llm_source_detail_refinement_fallback:{exc}"]
    return previous_selection, "detail_loaded_no_llm", []


def _selector_payload(
    claim: str,
    candidates: list[dict[str, Any]],
    stage: str = "brief",
    previous_selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    instructions = [
        "Select 1-4 source_id values from candidate_sources only.",
        "Prefer official primary sources for factual company, macro, fiscal, and entity claims.",
        "Use supplemental sources only when the claim requires market prices or official sources are insufficient.",
        "Do not select planned-only sources unless they are explicitly present in candidate_sources and needed for planning.",
        "Return JSON with selected_sources, rationale, confidence_0_to_1, and needs_cross_check.",
    ]
    if stage == "detail_refine":
        instructions.insert(
            0,
            "This is the second progressive-disclosure pass. You may keep or narrow the prior selection using the detailed descriptions only for those sources.",
        )
    return {
        "task": "source_selection",
        "stage": stage,
        "claim": claim,
        "candidate_sources": candidates,
        "previous_selection": previous_selection or {},
        "instructions": instructions,
    }


def _detail_candidates(candidates: list[dict[str, Any]], selected_sources: list[str]) -> list[dict[str, Any]]:
    candidate_ids = {str(item["source_id"]) for item in candidates}
    detail_cards = []
    for source_id in selected_sources:
        if source_id not in candidate_ids:
            continue
        entry = _catalog_by_id().get(source_id)
        if entry:
            detail_cards.append(entry.to_detail_prompt_dict())
    return detail_cards


def _selection_with_validated_sources(raw_selection: dict[str, Any], selected_sources: list[str]) -> dict[str, Any]:
    refined = dict(raw_selection)
    refined["selected_sources"] = selected_sources
    return refined


def _catalog_score(claim: str, entry: SourceCatalogEntry) -> float:
    text = claim.lower()
    score = 0.0
    for keyword in entry.keywords + entry.coverage + entry.best_for:
        normalized = keyword.lower()
        if normalized in text:
            score += 1.0
        else:
            words = [word for word in re.split(r"[^a-z0-9]+", normalized) if len(word) > 2]
            if words and any(word in text for word in words):
                score += 0.25
    if score > 0 and entry.is_official_primary and _needs_official_primary(claim):
        score += 0.35
    return score


def _needs_official_primary(claim: str) -> bool:
    lower = claim.lower()
    return bool(
        re.search(
            r"\b(revenue|sales|income|eps|cash flow|debt|assets|liabilities|margin|buyback|"
            r"repurchase|filed|filing|inflation|cpi|gdp|unemployment|federal debt|treasury|lei|legal entity)\b",
            lower,
        )
    )


def _tier_rank(tier: SourceTier) -> int:
    return {"T1": 5, "T2": 4, "T3": 3, "T4": 2, "T5": 1}.get(tier.value, 0)


def _catalog_by_id(include_planned: bool = True) -> dict[str, SourceCatalogEntry]:
    return {entry.source_id: entry for entry in source_catalog(include_planned=include_planned)}


def _source_description_dir() -> Path:
    return Path(__file__).with_name("source_descriptions")


def _combined_method(first_pass: str, second_pass: str) -> str:
    if not second_pass or second_pass == "detail_loaded_no_llm":
        return f"{first_pass}+detail_loaded"
    if second_pass == "no_detail_refinement":
        return first_pass
    return f"{first_pass}+{second_pass}"


def _loads_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    return json.loads(stripped)
