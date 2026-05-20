"""Source authority, recency, and numeric consistency scoring utilities."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from urllib.parse import urlparse

from .models import SourceAssessment, SourceTier, SourceType, clamp


DOMAIN_AUTHORITY: list[tuple[str, SourceType, SourceTier, float, str]] = [
    ("sec.gov", SourceType.SEC_FILING, SourceTier.T1, 1.00, "SEC filing/regulatory source"),
    ("data.sec.gov", SourceType.SEC_FILING, SourceTier.T1, 1.00, "SEC structured data"),
    ("nasdaq.com", SourceType.REGULATOR_EXCHANGE, SourceTier.T2, 0.82, "exchange/data source"),
    ("nyse.com", SourceType.REGULATOR_EXCHANGE, SourceTier.T2, 0.86, "exchange source"),
    ("reuters.com", SourceType.FINANCIAL_MEDIA, SourceTier.T3, 0.85, "major financial media"),
    ("bloomberg.com", SourceType.FINANCIAL_MEDIA, SourceTier.T3, 0.84, "major financial media"),
    ("wsj.com", SourceType.FINANCIAL_MEDIA, SourceTier.T3, 0.82, "major financial media"),
    ("ft.com", SourceType.FINANCIAL_MEDIA, SourceTier.T3, 0.80, "major financial media"),
    ("cnbc.com", SourceType.FINANCIAL_MEDIA, SourceTier.T3, 0.72, "financial media"),
    ("marketwatch.com", SourceType.FINANCIAL_MEDIA, SourceTier.T3, 0.66, "financial media"),
    ("finance.yahoo.com", SourceType.DATA_VENDOR, SourceTier.T3, 0.65, "market data/news aggregator"),
    ("query1.finance.yahoo.com", SourceType.DATA_VENDOR, SourceTier.T4, 0.42, "unofficial Yahoo chart endpoint"),
    ("alphavantage.co", SourceType.DATA_VENDOR, SourceTier.T3, 0.68, "financial data API"),
    ("finnhub.io", SourceType.DATA_VENDOR, SourceTier.T3, 0.66, "financial data API"),
    ("financialmodelingprep.com", SourceType.DATA_VENDOR, SourceTier.T3, 0.68, "financial data API"),
    ("api.stlouisfed.org", SourceType.REGULATOR_EXCHANGE, SourceTier.T2, 0.88, "Federal Reserve economic data API"),
    ("fred.stlouisfed.org", SourceType.REGULATOR_EXCHANGE, SourceTier.T2, 0.88, "Federal Reserve economic data"),
    ("marketstack.com", SourceType.DATA_VENDOR, SourceTier.T3, 0.62, "market data API"),
    ("api.tiingo.com", SourceType.DATA_VENDOR, SourceTier.T3, 0.70, "market data API"),
    ("stooq.com", SourceType.DATA_VENDOR, SourceTier.T4, 0.50, "free market data source"),
    ("morningstar.com", SourceType.DATA_VENDOR, SourceTier.T3, 0.76, "financial data vendor"),
    ("barrons.com", SourceType.FINANCIAL_MEDIA, SourceTier.T3, 0.78, "financial media"),
    ("seekingalpha.com", SourceType.BLOG_NEWSLETTER, SourceTier.T4, 0.55, "mixed contributor analysis"),
    ("fool.com", SourceType.BLOG_NEWSLETTER, SourceTier.T4, 0.52, "retail investor analysis"),
    ("substack.com", SourceType.BLOG_NEWSLETTER, SourceTier.T4, 0.42, "newsletter source"),
    ("reddit.com", SourceType.SOCIAL_FORUM, SourceTier.T5, 0.22, "social/forum source"),
    ("x.com", SourceType.SOCIAL_FORUM, SourceTier.T5, 0.18, "social source"),
    ("twitter.com", SourceType.SOCIAL_FORUM, SourceTier.T5, 0.18, "social source"),
    ("stocktwits.com", SourceType.SOCIAL_FORUM, SourceTier.T5, 0.20, "social trading forum"),
]


def canonical_domain(url: str) -> str:
    """Normalize a URL or host into a comparable domain."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or parsed.path).lower().split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def assess_source(url: str, title: str = "") -> SourceAssessment:
    """Classify source type/tier and assign a conservative authority score."""
    domain = canonical_domain(url)
    lower_url = url.lower()
    lower_title = title.lower()

    for pattern, source_type, tier, score, reason in DOMAIN_AUTHORITY:
        if domain == pattern or domain.endswith(f".{pattern}"):
            return SourceAssessment(source_type, tier, score, domain, [reason])

    if re.search(r"\b(investor|investors|ir|newsroom|press-release|press_release)\b", lower_url):
        return SourceAssessment(
            SourceType.COMPANY_IR,
            SourceTier.T2,
            0.86,
            domain,
            ["company investor-relations or official press page pattern"],
        )

    if "press release" in lower_title or "earnings release" in lower_title:
        return SourceAssessment(
            SourceType.COMPANY_IR,
            SourceTier.T2,
            0.80,
            domain,
            ["official-style release title pattern"],
        )

    return SourceAssessment(
        SourceType.UNKNOWN,
        SourceTier.T4,
        0.40,
        domain,
        ["unknown source; conservative default"],
    )


def score_recency(published_at: str | None, as_of_date: str | None = None) -> tuple[float, list[str]]:
    """Score recency with exponential decay relative to `as_of_date`."""
    if not published_at:
        return 0.45, ["missing publication date"]

    parsed = parse_date(published_at)
    if parsed is None:
        return 0.40, ["unparseable publication date"]

    as_of = parse_date(as_of_date) if as_of_date else date.today()
    if as_of is None:
        as_of = date.today()

    days = (as_of - parsed).days
    if days < 0:
        return 0.10, ["publication date is after as_of_date"]

    score = math.exp(-days / 365.0)
    return round(clamp(score, 0.15, 0.98), 3), [f"{days} days old"]


def parse_date(value: str | None) -> date | None:
    """Parse the date formats commonly returned by search/data providers."""
    if not value:
        return None
    cleaned = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(cleaned[:32], fmt).date()
        except ValueError:
            pass
    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", cleaned)
    if match:
        year, month, day = map(int, match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


NUMBER_RE = re.compile(
    r"[-+]?\$?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|percent|bps|billion|million|trillion|bn|mn)?",
    re.IGNORECASE,
)


def extract_numbers(text: str) -> list[str]:
    """Extract simple financial numeric strings from text."""
    values = []
    for match in NUMBER_RE.finditer(text):
        value = re.sub(r"\s+", " ", match.group(0).strip().lower())
        if value:
            values.append(value)
    return values


def score_numeric_consistency(claim: str, evidence_text: str) -> tuple[float, list[str]]:
    """Score whether claim numbers appear in the evidence text."""
    claim_numbers = extract_numbers(claim)
    if not claim_numbers:
        return 0.60, ["claim has no explicit numeric value"]

    evidence_numbers = extract_numbers(evidence_text)
    if not evidence_numbers:
        return 0.35, ["evidence has no explicit numeric value"]

    normalized_evidence = {_normalize_number(value) for value in evidence_numbers}
    matches = [
        value
        for value in claim_numbers
        if _normalize_number(value) in normalized_evidence
    ]
    if len(matches) == len(claim_numbers):
        return 0.95, [f"matched numeric values: {', '.join(matches)}"]
    if matches:
        return 0.72, [f"partially matched numeric values: {', '.join(matches)}"]
    return 0.25, ["claim numbers were not found in evidence"]


def _normalize_number(value: str) -> str:
    """Normalize punctuation and percent wording for rough equality checks."""
    return re.sub(r"[\s,$]", "", value.lower()).replace("percent", "%")
