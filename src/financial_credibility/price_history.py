"""Historical price helpers for price-pattern claims."""

from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from datetime import date
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
    end_close: float
    min_close: float
    max_close: float
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


def needs_historical_price_data(claim: str) -> bool:
    """Return True when a claim needs a price time series instead of fundamentals."""
    lower = claim.lower()
    has_pattern = bool(
        re.search(
            r"\b(oscillat\w*|fluctuat\w*|volatile|volatility|range[- ]?bound|"
            r"choppy|sideways|swing\w*|trend\w*|drawdown|rally|sell[- ]?off)\b",
            lower,
        )
    )
    has_price_context = bool(
        re.search(r"\b(stock|share|shares|price|close|closing|trading|chart|technical)\b", lower)
    )
    has_lookback_context = bool(
        re.search(r"\b(last|past|previous|trailing|these|recent)\b.*\b(day|days|week|weeks|month|months|year|years)\b", lower)
        or re.search(r"\b\d+\s*(d|day|days|w|week|weeks|mo|month|months|y|year|years)\b", lower)
    )
    return has_pattern and (has_price_context or has_lookback_context)


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
    if "year to date" in lower or "ytd" in lower:
        return 12
    return default


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
    min_close = min(closes)
    max_close = max(closes)
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
        end_close=round(end_close, 4),
        min_close=round(min_close, 4),
        max_close=round(max_close, 4),
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
        f"total_return_pct {summary.total_return_pct}; range_pct {summary.range_pct}; "
        f"annualized_volatility_pct {summary.annualized_volatility_pct}; "
        f"up_days {summary.up_days}; down_days {summary.down_days}; "
        f"daily_direction_changes {summary.daily_direction_changes}; "
        f"daily_direction_change_ratio {summary.daily_direction_change_ratio}; "
        f"monthly_points {summary.monthly_points}; "
        f"monthly_direction_changes {summary.monthly_direction_changes}; "
        f"monthly_direction_change_ratio {summary.monthly_direction_change_ratio}; "
        f"oscillation_signal {summary.oscillation_signal}."
    )


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
