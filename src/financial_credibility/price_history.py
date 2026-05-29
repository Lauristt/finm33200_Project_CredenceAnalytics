"""Historical price helpers for price-pattern claims."""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from io import StringIO
from statistics import stdev


@dataclass(frozen=True)
class PricePoint:
    """One daily OHLCV observation."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int | None = None


@dataclass(frozen=True)
class PriceHistorySummary:
    """Compact time-series summary intended for downstream LLM verification."""

    observations: int
    start_date: str
    end_date: str
    start_close: float
    previous_close: float | None
    end_close: float
    min_close: float
    max_close: float
    latest_daily_point_change: float | None
    latest_daily_abs_point_change: float | None
    latest_daily_return_pct: float
    latest_daily_abs_return_pct: float
    previous_daily_return_pct: float | None
    previous_daily_abs_return_pct: float | None
    total_point_change: float
    total_return_pct: float
    range_pct: float
    annualized_volatility_pct: float
    up_days: int
    down_days: int
    daily_direction_changes: int
    daily_direction_change_ratio: float
    monthly_points: int
    monthly_direction_changes: int
    monthly_direction_change_ratio: float
    oscillation_signal: str


@dataclass(frozen=True)
class PriceWindow:
    """Date window inferred for a price-history claim."""

    start: date
    end: date
    lookback_months: int
    label: str
    source: str


PRICE_HISTORY_ASSET_CLASSES = {
    "single_name_equity",
    "fund_etf",
    "equity_index",
    "volatility_index",
    "equity_index_future",
}


def needs_historical_price_data(claim: str, asset_classes: list[str] | tuple[str, ...] | set[str] | None = None) -> bool:
    """Return True when a claim needs a market price time series."""
    lower = claim.lower()
    normalized_assets = {str(item).strip().lower() for item in (asset_classes or []) if item}
    if normalized_assets and not (normalized_assets & PRICE_HISTORY_ASSET_CLASSES):
        return False
    has_pattern = bool(
        re.search(
            r"\b(oscillat\w*|fluctuat\w*|volatile|volatility|range[- ]?bound|"
            r"choppy|sideways|swing\w*|trend\w*|drawdown|rally|sell[- ]?off)\b",
            lower,
        )
        or bool(re.search(r"\b(record[- ]high|closing high|record closing high|closed at|hit record)\b", lower))
    )
    has_price_action_move = bool(
        re.search(
            r"\b(fell|falls|falling|dropped|drops|declined|declines|lost|loses|slid|slipped|slips|"
            r"tumbled|plunged|rose|rises|gained|gains|jumped|surged|rallied|"
            r"advanced|climbed|added|adds|moved|moves|up|down)\b",
            lower,
        )
        or bool(re.search(r"\bis\s+up\b|\bis\s+down\b|\bwas\s+up\b|\bwas\s+down\b", lower))
    )
    has_fundamental_metric = bool(
        re.search(
            r"\b(revenue|sales|income|eps|earnings|margin|cash flow|ebitda|free cash flow|"
            r"debt|assets|liabilities|bookings|shipments|guidance|supply|inventory|"
            r"stockpiles|open interest|positioning)\b",
            lower,
        )
    )
    has_move_magnitude = bool(re.search(r"[-+]?\d+(?:\.\d+)?\s*(?:%|percent\b)", lower))
    has_day_context = bool(
        re.search(
            r"\b(monday|tuesday|wednesday|thursday|friday|today|yesterday|session|"
            r"trading day|after hours|premarket)\b",
            lower,
        )
    )
    has_price_context = bool(
        re.search(r"\b(stock|share|shares|price|close|closed|closing|trading|chart|technical|futures?|markets?)\b", lower)
    )
    bare_fundamental_change = bool(
        re.match(r"^\s*(?:up|down|higher|lower)\s+[-+]?\d+(?:\.\d+)?\s*(?:%|percent\b)", lower)
        and re.search(r"\b(year earlier|year over year|yoy|sequential|from a year|previous quarter)\b", lower)
        and not has_price_context
    )
    has_lookback_context = bool(
        re.search(r"\b(last|past|previous|trailing|these|recent|for the|this)\b.*\b(day|days|week|weeks|month|months|year|years)\b", lower)
        or re.search(r"\b\d+\s*(d|day|days|w|week|weeks|mo|month|months|y|year|years)\b", lower)
        or re.search(r"\b(ytd|year[- ]to[- ]date|recently|recent gains?|sharp gains?)\b", lower)
    )
    if has_pattern and (has_price_context or has_lookback_context):
        return True
    non_price_metric_blocks = has_fundamental_metric and not has_price_context
    if bare_fundamental_change:
        return False
    return has_price_action_move and not non_price_metric_blocks and (has_price_context or has_move_magnitude)


def infer_price_window(claim: str, as_of: date) -> PriceWindow:
    """Infer the retrieval window for a price/return claim."""
    lower = claim.lower()
    explicit = _explicit_relative_window(lower, as_of)
    if explicit:
        return explicit
    lookback_months = parse_lookback_months(claim)
    start = as_of - timedelta(days=max(31, int(lookback_months * 31)))
    return PriceWindow(
        start=start,
        end=as_of,
        lookback_months=lookback_months,
        label=f"approximately {lookback_months} month(s)",
        source="lookback_months",
    )


def parse_lookback_months(claim: str, default: int = 10) -> int:
    """Parse a lookback window from a claim, expressed approximately in months."""
    lower = claim.lower()
    patterns = [
        (r"\b(\d+)\s*(?:mo|month|months)\b", 1.0),
        (r"\b(\d+)\s*(?:w|week|weeks)\b", 1.0 / 4.345),
        (r"\b(\d+)\s*(?:d|day|days)\b", 1.0 / 30.5),
        (r"\b(\d+)\s*(?:y|year|years)\b", 12.0),
    ]
    for pattern, multiplier in patterns:
        match = re.search(pattern, lower)
        if match:
            months = max(1, round(int(match.group(1)) * multiplier))
            return min(months, 60)
    if re.search(r"\b(ytd|year[- ]to[- ]date|for the year|this year)\b", lower):
        return 12
    if re.search(r"\bthis week\b", lower):
        return 1
    if re.search(r"\bthis month\b", lower):
        return 1
    if re.search(r"\brecent months\b|\bin recent months\b", lower):
        return 3
    if re.search(r"\brecently\b|\brecent gains?\b|\bsharp gains?\b", lower):
        return 1
    if needs_historical_price_data(claim) and re.search(
        r"\b(fell|falls|dropped|rose|gained|jumped|surged|rallied|climbed|added|adds|slipped|lost|"
        r"monday|tuesday|wednesday|thursday|friday|today|yesterday|session)\b",
        lower,
    ):
        return 1
    return default


def _explicit_relative_window(lower: str, as_of: date) -> PriceWindow | None:
    if re.search(r"\b(ytd|year[- ]to[- ]date|for the year|this year)\b", lower):
        return PriceWindow(
            start=date(as_of.year, 1, 1),
            end=as_of,
            lookback_months=max(1, as_of.month),
            label="year to date",
            source="ytd_context",
        )
    if re.search(r"\bthis week\b", lower):
        start = as_of - timedelta(days=as_of.weekday())
        return PriceWindow(start=start, end=as_of, lookback_months=1, label="this week", source="this_week_context")
    if re.search(r"\bthis month\b", lower):
        start = date(as_of.year, as_of.month, 1)
        return PriceWindow(start=start, end=as_of, lookback_months=1, label="this month", source="this_month_context")
    match = re.search(r"\b(?:last|past|previous|trailing)\s+(\d+)\s*(day|days|week|weeks|month|months|year|years)\b", lower)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        days = _window_days(amount, unit)
        months = max(1, round(days / 31))
        return PriceWindow(
            start=as_of - timedelta(days=days),
            end=as_of,
            lookback_months=min(months, 60),
            label=f"last {amount} {unit}",
            source="explicit_lookback_context",
        )
    if re.search(r"\brecent months\b|\bin recent months\b", lower):
        return PriceWindow(
            start=as_of - timedelta(days=93),
            end=as_of,
            lookback_months=3,
            label="recent months",
            source="approximate_recent_months_context",
        )
    if re.search(r"\brecently\b|\brecent gains?\b|\bsharp gains?\b", lower):
        return PriceWindow(
            start=as_of - timedelta(days=31),
            end=as_of,
            lookback_months=1,
            label="recent short window",
            source="approximate_recent_context",
        )
    if re.search(r"\b(monday|tuesday|wednesday|thursday|friday|today|yesterday|session|trading day)\b", lower):
        return PriceWindow(
            start=as_of - timedelta(days=7),
            end=as_of,
            lookback_months=1,
            label="single trading session context",
            source="single_session_context",
        )
    return None


def _window_days(amount: int, unit: str) -> int:
    if unit.startswith("day"):
        return max(1, amount)
    if unit.startswith("week"):
        return max(7, amount * 7)
    if unit.startswith("month"):
        return max(31, amount * 31)
    return max(365, amount * 365)


def parse_stooq_price_csv(text: str) -> list[PricePoint]:
    """Parse Stooq daily historical CSV into sorted price points."""
    points: list[PricePoint] = []
    for row in csv.DictReader(StringIO(text)):
        try:
            close_raw = row.get("Close")
            if close_raw in {None, "", "N/D"}:
                continue
            volume_raw = row.get("Volume")
            points.append(
                PricePoint(
                    date=date.fromisoformat(str(row["Date"])),
                    open=float(row.get("Open") or close_raw),
                    high=float(row.get("High") or close_raw),
                    low=float(row.get("Low") or close_raw),
                    close=float(close_raw),
                    volume=int(volume_raw) if volume_raw not in {None, "", "N/D"} else None,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(points, key=lambda item: item.date)


def summarize_price_history(points: list[PricePoint]) -> PriceHistorySummary | None:
    """Summarize daily prices into volatility, range, and direction-change signals."""
    if len(points) < 2:
        return None

    closes = [point.close for point in points]
    returns = [
        (current / previous) - 1.0
        for previous, current in zip(closes, closes[1:])
        if previous > 0
    ]
    signs = [_return_sign(value) for value in returns]
    nonzero_signs = [sign for sign in signs if sign != 0]

    monthly_closes = _month_end_closes(points)
    monthly_returns = [
        (current / previous) - 1.0
        for previous, current in zip(monthly_closes, monthly_closes[1:])
        if previous > 0
    ]
    monthly_signs = [_return_sign(value, threshold=0.01) for value in monthly_returns]
    monthly_nonzero_signs = [sign for sign in monthly_signs if sign != 0]

    start_close = closes[0]
    end_close = closes[-1]
    previous_close = closes[-2] if len(closes) >= 2 else None
    latest_daily_point_change = (end_close - previous_close) if previous_close is not None else None
    latest_daily_return_pct = returns[-1] * 100 if returns else 0.0
    previous_daily_return_pct = returns[-2] * 100 if len(returns) >= 2 else None
    min_close = min(closes)
    max_close = max(closes)
    total_point_change = end_close - start_close
    total_return_pct = ((end_close / start_close) - 1.0) * 100 if start_close else 0.0
    range_pct = ((max_close - min_close) / start_close) * 100 if start_close else 0.0
    annualized_volatility_pct = stdev(returns) * math.sqrt(252) * 100 if len(returns) > 1 else 0.0
    daily_direction_changes = _direction_changes(nonzero_signs)
    monthly_direction_changes = _direction_changes(monthly_nonzero_signs)

    return PriceHistorySummary(
        observations=len(points),
        start_date=points[0].date.isoformat(),
        end_date=points[-1].date.isoformat(),
        start_close=round(start_close, 4),
        previous_close=round(previous_close, 4) if previous_close is not None else None,
        end_close=round(end_close, 4),
        min_close=round(min_close, 4),
        max_close=round(max_close, 4),
        latest_daily_point_change=round(latest_daily_point_change, 4) if latest_daily_point_change is not None else None,
        latest_daily_abs_point_change=round(abs(latest_daily_point_change), 4) if latest_daily_point_change is not None else None,
        latest_daily_return_pct=round(latest_daily_return_pct, 2),
        latest_daily_abs_return_pct=round(abs(latest_daily_return_pct), 2),
        previous_daily_return_pct=round(previous_daily_return_pct, 2) if previous_daily_return_pct is not None else None,
        previous_daily_abs_return_pct=round(abs(previous_daily_return_pct), 2) if previous_daily_return_pct is not None else None,
        total_point_change=round(total_point_change, 4),
        total_return_pct=round(total_return_pct, 2),
        range_pct=round(range_pct, 2),
        annualized_volatility_pct=round(annualized_volatility_pct, 2),
        up_days=sum(1 for value in returns if value > 0),
        down_days=sum(1 for value in returns if value < 0),
        daily_direction_changes=daily_direction_changes,
        daily_direction_change_ratio=round(daily_direction_changes / max(1, len(nonzero_signs) - 1), 3),
        monthly_points=len(monthly_closes),
        monthly_direction_changes=monthly_direction_changes,
        monthly_direction_change_ratio=round(monthly_direction_changes / max(1, len(monthly_nonzero_signs) - 1), 3),
        oscillation_signal=_oscillation_signal(
            range_pct=range_pct,
            total_return_pct=total_return_pct,
            monthly_direction_changes=monthly_direction_changes,
            monthly_points=len(monthly_closes),
        ),
    )


def format_price_history_summary(ticker: str, lookback_months: int, summary: PriceHistorySummary) -> str:
    """Format the summary as dense evidence text for the verification judge."""
    return (
        f"{ticker.upper()} historical daily close prices over approximately {lookback_months} months: "
        f"observations {summary.observations}; period {summary.start_date} to {summary.end_date}; "
        f"start_close {summary.start_close}; end_close {summary.end_close}; "
        f"min_close {summary.min_close}; max_close {summary.max_close}; "
        f"latest_daily_calculation previous_close {_format_optional_number(summary.previous_close)} "
        f"to end_close {summary.end_close}; "
        f"latest_daily_point_change {_format_optional_number(summary.latest_daily_point_change)}; "
        f"latest_daily_abs_point_change {_format_optional_number(summary.latest_daily_abs_point_change)}; "
        f"latest_daily_return_pct {summary.latest_daily_return_pct}% from close-to-close calculation; "
        f"latest_daily_abs_return_pct {summary.latest_daily_abs_return_pct}%; "
        f"previous_daily_return_pct {_format_optional_pct(summary.previous_daily_return_pct)}; "
        f"previous_daily_abs_return_pct {_format_optional_pct(summary.previous_daily_abs_return_pct)}; "
        f"total_point_change {summary.total_point_change}; "
        f"total_return_pct {summary.total_return_pct}%; range_pct {summary.range_pct}%; "
        f"annualized_volatility_pct {summary.annualized_volatility_pct}; "
        f"up_days {summary.up_days}; down_days {summary.down_days}; "
        f"daily_direction_changes {summary.daily_direction_changes}; "
        f"daily_direction_change_ratio {summary.daily_direction_change_ratio}; "
        f"monthly_points {summary.monthly_points}; "
        f"monthly_direction_changes {summary.monthly_direction_changes}; "
        f"monthly_direction_change_ratio {summary.monthly_direction_change_ratio}; "
        f"oscillation_signal {summary.oscillation_signal}."
    )


def _format_optional_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value}%"


def _format_optional_number(value: float | None) -> str:
    return "n/a" if value is None else str(value)


def _month_end_closes(points: list[PricePoint]) -> list[float]:
    month_end: dict[str, float] = {}
    for point in points:
        month_end[point.date.strftime("%Y-%m")] = point.close
    return [month_end[key] for key in sorted(month_end)]


def _direction_changes(signs: list[int]) -> int:
    return sum(1 for previous, current in zip(signs, signs[1:]) if previous != current)


def _return_sign(value: float, threshold: float = 0.001) -> int:
    if value > threshold:
        return 1
    if value < -threshold:
        return -1
    return 0


def _oscillation_signal(
    range_pct: float,
    total_return_pct: float,
    monthly_direction_changes: int,
    monthly_points: int,
) -> str:
    enough_months = monthly_points >= 5
    range_dominates_trend = range_pct >= max(15.0, abs(total_return_pct) * 1.4)
    if enough_months and monthly_direction_changes >= 3 and range_dominates_trend:
        return "strong"
    if enough_months and monthly_direction_changes >= 2 and range_pct >= 12.0:
        return "moderate"
    return "weak"
