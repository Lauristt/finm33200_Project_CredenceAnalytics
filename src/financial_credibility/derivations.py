"""Replayable numeric derivations for common financial claim patterns."""

from __future__ import annotations

import re

from .models import CanonicalFact, NumericDerivation, VerificationCheck, VerificationVerdict
from .sources import extract_substantive_numbers


def derive_numeric_check(claim: str, facts: list[CanonicalFact], numeric_check: VerificationCheck) -> NumericDerivation | None:
    """Build a small replayable calculation when evidence supports one."""
    derived_metric = _derive_formula_metric(claim, facts)
    if derived_metric:
        return derived_metric
    is_growth_claim = _is_growth_claim(claim)
    if is_growth_claim:
        growth = _derive_growth(claim, facts)
        if growth:
            return growth
    fuzzy = _derive_fuzzy_match(numeric_check)
    if fuzzy:
        return fuzzy
    if is_growth_claim:
        return None
    # Level check: for macro/price claims with a stated numeric value,
    # compare the most recent matching fact directly against the claim.
    level_check = _derive_level_check(claim, facts)
    if level_check:
        return level_check
    if numeric_check.verdict in {
        VerificationVerdict.NOT_APPLICABLE.value,
        VerificationVerdict.INSUFFICIENT.value,
        VerificationVerdict.NOT_FOUND.value,
    }:
        return None
    return NumericDerivation(
        expression="numeric_verification",
        result=numeric_check.verdict,
        passed=numeric_check.verdict in {VerificationVerdict.VERIFIED.value, VerificationVerdict.PARTIALLY_VERIFIED.value},
        notes=[numeric_check.summary],
    )


def _derive_level_check(claim: str, facts: list[CanonicalFact]) -> NumericDerivation | None:
    """For price/rate level claims, check the most recent fact against the stated value."""
    from .sources import extract_substantive_numbers as _esn

    # Only run for claims with numeric values and macro-style facts.
    # Prefer numbers that appear adjacent to % or "basis points" as the claimed value.
    claimed_pct_matches = re.findall(
        r"([\d,]+(?:\.\d+)?)\s*(?:%|percent|basis\s+points?\b|bps\b|pp\b)", claim, re.I
    )
    claimed_plain = re.findall(r"(?<!\d)([\d,]+(?:\.\d+)?)(?!\d)", claim)

    def _parse_num(s: str) -> float | None:
        try:
            return float(s.replace(",", ""))
        except (ValueError, TypeError):
            return None

    # Build an ordered candidate list: % values first (most specific), then plain numbers
    candidates: list[float] = []
    for s in claimed_pct_matches:
        v = _parse_num(s)
        if v is not None and v != 0:
            candidates.append(v)
    for s in claimed_plain:
        v = _parse_num(s)
        if v is not None and v != 0 and v not in candidates:
            candidates.append(v)

    if not candidates:
        return None

    numeric_facts = [f for f in facts if isinstance(f.value, (int, float))]
    if not numeric_facts:
        return None

    # Use anchor date to pick the most relevant fact
    anchor = _extract_claim_anchor_date(claim)
    if anchor:
        numeric_facts.sort(key=lambda f: _period_days_from_anchor(f, anchor))
    else:
        numeric_facts.sort(key=lambda f: (f.report_period or ""), reverse=True)

    best_fact = numeric_facts[0]
    actual_value = float(best_fact.value)  # type: ignore[arg-type]

    # Pick the candidate closest in ratio to 1.0 (most dimensionally compatible)
    target: float | None = None
    best_ratio_dist = float("inf")
    for num in candidates:
        if num == 0:
            continue
        ratio = actual_value / num
        # Only consider numbers within 3 orders of magnitude of actual
        if not (0.001 <= abs(ratio) <= 1000):
            continue
        dist = abs(ratio - 1.0)
        if dist < best_ratio_dist:
            best_ratio_dist = dist
            target = num
    if target is None:
        return None

    # Tolerance: 10% for "approximately"/"around" claims; 5% otherwise
    is_approx = bool(re.search(r"\bapprox|around|roughly|about|approximately\b", claim, re.I))
    tolerance = 0.10 if is_approx else 0.05
    diff_pct = abs(actual_value - target) / max(abs(target), 1e-9)
    passed = diff_pct <= tolerance
    comparator = f"≈ {target} ± {int(tolerance*100)}%"

    return NumericDerivation(
        expression="level_check",
        inputs={
            "fact_id": best_fact.fact_id,
            "fact_period": best_fact.report_period or best_fact.observation_date,
            "actual": actual_value,
            "claimed": target,
            "diff_pct": round(diff_pct, 4),
            "tolerance": tolerance,
        },
        result=actual_value,
        comparator=comparator,
        threshold=target,
        tolerance=tolerance,
        passed=passed,
        notes=[
            f"Level check: actual {actual_value} vs claimed {target} "
            f"(diff {diff_pct*100:.1f}%, tol {tolerance*100:.0f}%)"
        ],
    )


def _derive_formula_metric(claim: str, facts: list[CanonicalFact]) -> NumericDerivation | None:
    lower = claim.lower()
    if _is_component_revenue_share_claim(lower):
        derivation = _derive_component_revenue_share(claim, facts)
        if derivation:
            return derivation
    if "gross margin" in lower:
        return _derive_ratio(
            claim,
            facts,
            expression="GrossProfit / Revenue",
            numerator_aliases=["GrossProfit"],
            denominator_aliases=_REVENUE_ALIASES,
            result_kind="ratio",
            notes=["derived gross margin from gross profit and revenue facts"],
        )
    if "operating margin" in lower:
        return _derive_ratio(
            claim,
            facts,
            expression="OperatingIncomeLoss / Revenue",
            numerator_aliases=["OperatingIncomeLoss"],
            denominator_aliases=_REVENUE_ALIASES,
            result_kind="ratio",
            notes=["derived operating margin from operating income and revenue facts"],
        )
    if "net margin" in lower:
        return _derive_ratio(
            claim,
            facts,
            expression="NetIncomeLoss / Revenue",
            numerator_aliases=["NetIncomeLoss"],
            denominator_aliases=_REVENUE_ALIASES,
            result_kind="ratio",
            notes=["derived net margin from net income and revenue facts"],
        )
    if "current ratio" in lower:
        return _derive_ratio(
            claim,
            facts,
            expression="AssetsCurrent / LiabilitiesCurrent",
            numerator_aliases=["AssetsCurrent"],
            denominator_aliases=["LiabilitiesCurrent"],
            result_kind="plain_ratio",
            notes=["derived current ratio from current assets and current liabilities"],
        )
    if "free cash flow" in lower or "fcf" in lower:
        return _derive_free_cash_flow(claim, facts)
    if "net debt" in lower:
        return _derive_net_debt(claim, facts)
    if re.search(r"\bdebt[- ]to[- ]assets\b|\bdebt/assets\b", lower):
        return _derive_debt_to_assets(claim, facts)
    return None


def _derive_growth(claim: str, facts: list[CanonicalFact]) -> NumericDerivation | None:
    numeric_facts = [
        fact
        for fact in facts
        if isinstance(fact.value, (int, float)) and fact.fact_name and _fact_matches_claim(fact.fact_name, claim)
    ]
    if len(numeric_facts) < 2:
        return None
    if _has_duplicate_period_values(numeric_facts):
        return None
    pairs = _candidate_growth_pairs(numeric_facts)
    if not pairs:
        return None

    # When the claim specifies year-over-year, prefer YoY pairs (~365 days).
    # When it specifies quarter-over-quarter, prefer QoQ pairs (~91 days).
    # Otherwise pick the pair whose computed growth is closest to the stated threshold.
    is_yoy = bool(re.search(r"year[- ]over[- ]year|yoy|同比", claim, re.IGNORECASE))
    is_qoq = bool(re.search(r"quarter[- ]over[- ]quarter|qoq|环比", claim, re.IGNORECASE))
    threshold = _claim_threshold(claim, "ratio")

    def _pair_gap_days(pair: tuple[CanonicalFact, CanonicalFact]) -> int:
        from datetime import date as _date
        def _pd(s: str | None) -> _date | None:
            try: return _date.fromisoformat((s or "")[:10])
            except ValueError: return None
        p, c = pair
        pd_ = _pd(p.report_period or p.observation_date)
        cd_ = _pd(c.report_period or c.observation_date)
        return (cd_ - pd_).days if pd_ and cd_ else 0

    def _current_period(pair: tuple[CanonicalFact, CanonicalFact]) -> str:
        return pair[1].report_period or pair[1].observation_date or ""

    # If the claim references a specific month ("January 2024", "Q2 2025", etc.),
    # anchor pair selection to that date so we pick prior→current rather than
    # the most recent data point.
    claim_anchor_date = _extract_claim_anchor_date(claim)

    if is_yoy:
        yoy_pairs = [p for p in pairs if 330 <= _pair_gap_days(p) <= 400]
        if yoy_pairs:
            if claim_anchor_date:
                # When the claim names a specific date, prefer pairs whose current
                # period is closest to that date (e.g. "January 2024" → Jan 2024).
                anchored = [
                    p for p in yoy_pairs
                    if _period_days_from_anchor(p[1], claim_anchor_date) <= 40
                ]
                pool = anchored if anchored else yoy_pairs
                pool.sort(key=lambda p: _period_days_from_anchor(p[1], claim_anchor_date))
            else:
                pool = yoy_pairs
                pool.sort(key=_current_period, reverse=True)  # most recent first
            yoy_pairs = pool
        pairs = yoy_pairs or pairs
    elif is_qoq:
        qoq_pairs = [p for p in pairs if 75 <= _pair_gap_days(p) <= 105]
        if qoq_pairs:
            if claim_anchor_date:
                anchored = [
                    p for p in qoq_pairs
                    if _period_days_from_anchor(p[1], claim_anchor_date) <= 40
                ]
                pool = anchored if anchored else qoq_pairs
                pool.sort(key=lambda p: _period_days_from_anchor(p[1], claim_anchor_date))
            else:
                pool = qoq_pairs
                pool.sort(key=_current_period, reverse=True)
            qoq_pairs = pool
        pairs = qoq_pairs or pairs
    elif threshold is not None:
        # Pick the pair whose computed growth is closest to the claimed threshold.
        def _growth(pair: tuple[CanonicalFact, CanonicalFact]) -> float:
            p, c = pair
            pv, cv = float(p.value), float(c.value)
            return (cv - pv) / abs(pv) if pv != 0 else float("inf")
        pairs = sorted(pairs, key=lambda pr: abs(_growth(pr) - threshold))
    else:
        pairs.sort(key=_current_period, reverse=True)  # default: most recent

    prior, current = pairs[0]
    prior_value = float(prior.value)
    current_value = float(current.value)
    if prior_value == 0:
        return None
    result = (current_value - prior_value) / abs(prior_value)
    expects_positive = _expects_positive_growth(claim)
    threshold = _claim_threshold(claim, "ratio")
    target = threshold
    comparator = None
    if threshold is not None:
        target = threshold if expects_positive else -abs(threshold)
        comparator = _claim_comparator(claim) or "~="
        if not expects_positive and comparator in {">=", "<="}:
            comparator = "<=" if comparator == ">=" else ">="
        passed = _compare_result(result, target, comparator, _ratio_tolerance(target))
    else:
        passed = result > 0 if expects_positive else result < 0
        comparator = "> 0" if expects_positive else "< 0"
    return NumericDerivation(
        expression="(current - prior) / abs(prior)",
        inputs={
            "current_fact_id": current.fact_id,
            "current_period": current.report_period or current.observation_date,
            "current": current_value,
            "prior_fact_id": prior.fact_id,
            "prior_period": prior.report_period or prior.observation_date,
            "prior": prior_value,
        },
        result=round(result, 6),
        comparator=comparator,
        threshold=round(target, 6) if isinstance(target, float) else 0,
        passed=passed,
        tolerance=round(_ratio_tolerance(target), 6),
        notes=[
            f"YoY/QoQ growth derived from SEC facts: "
            f"{current_value:,.0f} vs {prior_value:,.0f} = {result*100:.1f}%"
        ],
    )


def _candidate_growth_pairs(facts: list[CanonicalFact]) -> list[tuple[CanonicalFact, CanonicalFact]]:
    """Find (prior, current) pairs suitable for YoY/QoQ growth derivation.

    Groups facts by (concept, period_kind) where period_kind comes from the
    fact's raw metadata (reliable) or is inferred from the form type, then
    finds pairs whose report periods are ~1 year apart (330-400 days) for YoY
    or ~1 quarter apart (75-105 days) for QoQ.
    """
    from datetime import date as _date, timedelta as _td

    def _parse_date(s: str | None) -> _date | None:
        if not s:
            return None
        try:
            return _date.fromisoformat(s[:10])
        except ValueError:
            return None

    def _raw_period_kind(fact: CanonicalFact) -> str:
        raw = fact.raw or {}
        pk = str(raw.get("period_kind", "")).lower()
        if "month" in pk:
            return "monthly"
        if "quarter" in pk:
            return "quarter"
        if "year" in pk or "annual" in pk:
            return "annual"
        form = str(raw.get("form", "")).upper()
        if "10-Q" in form:
            return "quarter"
        if "10-K" in form or "20-F" in form:
            return "annual"
        # fall back to legacy Q1/Q2/FY marker scan on report_period
        upper = (fact.report_period or "").upper()
        for marker in ("Q1", "Q2", "Q3", "Q4"):
            if marker in upper:
                return "quarter"
        if "FY" in upper:
            return "annual"
        return "unknown"

    by_concept: dict[tuple[str, str], list[CanonicalFact]] = {}
    for fact in facts:
        kind = _raw_period_kind(fact)
        if kind == "unknown":
            continue
        key = (str(fact.fact_name), kind)
        by_concept.setdefault(key, []).append(fact)

    pairs: list[tuple[CanonicalFact, CanonicalFact]] = []
    for grouped in by_concept.values():
        ordered = sorted(
            grouped,
            key=lambda f: (f.report_period or "", f.filing_date or ""),
        )
        # Collect YoY (~365 day) and QoQ (~91 day) pairs independently.
        # We must NOT break on a QoQ hit when scanning for YoY pairs: for a
        # quarterly series [Q1-25, Q2-25, Q3-25, Q4-25, Q1-26] the first
        # candidate after Q1-25 is Q2-25 (91 days, QoQ) but Q1-26 (364 days,
        # YoY) is the pair we actually want for a YoY growth claim.
        yoy_seen: set[str] = set()   # prior fact_id already matched to a YoY current
        qoq_seen: set[str] = set()   # prior fact_id already matched to a QoQ current
        for i, prior in enumerate(ordered):
            prior_date = _parse_date(prior.report_period or prior.observation_date)
            if prior_date is None:
                continue
            # Scan all candidates up to the YoY window; pick the pair
            # whose gap is *closest to 365 days* rather than stopping at
            # the first hit. This matters for monthly data where 334-day
            # cross-month pairs beat the true same-month 366-day pair.
            best_yoy: "tuple | None" = None
            best_yoy_gap: int = 0
            for current in ordered[i + 1:]:
                current_date = _parse_date(current.report_period or current.observation_date)
                if current_date is None or current_date <= prior_date:
                    continue
                gap = (current_date - prior_date).days
                if gap > 400:
                    break  # beyond YoY window, nothing further will qualify
                if 330 <= gap <= 400 and prior.fact_id not in yoy_seen:
                    if best_yoy is None or abs(gap - 365) < abs(best_yoy_gap - 365):
                        best_yoy = (prior, current)
                        best_yoy_gap = gap
                if 75 <= gap <= 105 and prior.fact_id not in qoq_seen:
                    pairs.append((prior, current))
                    qoq_seen.add(prior.fact_id)
            if best_yoy is not None and prior.fact_id not in yoy_seen:
                pairs.append(best_yoy)
                yoy_seen.add(prior.fact_id)
    return pairs


def _has_duplicate_period_values(facts: list[CanonicalFact]) -> bool:
    """Return True only when the same concept+period+period_kind has conflicting values.

    SEC 10-K filings can report both an annual total and quarterly breakouts under the
    same end date (e.g. Revenues for 2018-08-30 appears as both fiscal-year and
    fiscal-quarter rows).  Including period_kind and form in the key prevents those
    legitimate dual-granularity rows from being treated as ambiguous duplicates.
    """
    seen: dict[tuple, set[float]] = {}
    for fact in facts:
        if not fact.fact_name or not fact.report_period or not isinstance(fact.value, (int, float)):
            continue
        raw = fact.raw or {}
        period_kind = str(raw.get("period_kind", "")).lower()
        form = str(raw.get("form", "")).upper()
        key = (fact.fact_name, fact.report_period, period_kind, form)
        seen.setdefault(key, set()).add(float(fact.value))
    return any(len(values) > 1 for values in seen.values())


_MONTH_MAP = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6,
    "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def _extract_claim_anchor_date(claim: str) -> "date | None":
    """Extract a specific month/year reference from a claim string."""
    from datetime import date as _date
    lower = claim.lower()
    # "January 2024" / "jan 2024"
    m = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december"
        r"|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(20\d{2})\b",
        lower,
    )
    if m:
        month = _MONTH_MAP.get(m.group(1), 1)
        year = int(m.group(2))
        try:
            return _date(year, month, 1)
        except ValueError:
            pass
    # "Q2 2025" / "Q2FY2025"
    q = re.search(r"\bq([1-4])\s*(?:fy\s*)?(20\d{2})\b", lower)
    if q:
        quarter = int(q.group(1))
        year = int(q.group(2))
        month = (quarter - 1) * 3 + 1
        try:
            return _date(year, month, 1)
        except ValueError:
            pass
    return None


def _period_days_from_anchor(fact: "CanonicalFact", anchor: "date") -> int:
    """Days between fact.report_period and the anchor date (absolute)."""
    from datetime import date as _date
    period_str = fact.report_period or fact.observation_date or ""
    try:
        fd = _date.fromisoformat(period_str[:10])
        return abs((fd - anchor).days)
    except (ValueError, AttributeError):
        return 9999


def _period_kind(period: str | None) -> str | None:
    """Legacy helper kept for callers outside _candidate_growth_pairs."""
    if not period:
        return None
    upper = period.upper()
    for marker in ("Q1", "Q2", "Q3", "Q4", "FY"):
        if marker in upper:
            return marker
    return None


def _derive_fuzzy_match(numeric_check: VerificationCheck) -> NumericDerivation | None:
    matched = []
    unmatched = []
    for issue in numeric_check.issues:
        match = re.search(r"matched\s+(?P<claim>.+?)\s+with\s+(?P<evidence>.+)", issue)
        if match:
            matched.append(f"{match.group('claim')} -> {match.group('evidence')}")
        miss = re.search(r"unmatched claim numbers:\s+(?P<values>.+)", issue)
        if miss:
            unmatched.extend([item.strip() for item in miss.group("values").split(",") if item.strip()])
    if matched or unmatched:
        return NumericDerivation(
            expression="numeric_match_summary",
            inputs={
                "matched_values": "; ".join(matched) or "none",
                "unmatched_values": ", ".join(unmatched) or "none",
            },
            result=not unmatched,
            comparator="all material claim numbers must be verified",
            passed=not unmatched and numeric_check.verdict == VerificationVerdict.VERIFIED.value,
            notes=[numeric_check.summary],
        )
    return None


_REVENUE_ALIASES = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"]
_DEBT_ALIASES = ["LongTermDebt", "LongTermDebtCurrent", "ShortTermBorrowings", "ShortTermDebt"]
_CASH_ALIASES = ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]


def _derive_ratio(
    claim: str,
    facts: list[CanonicalFact],
    expression: str,
    numerator_aliases: list[str],
    denominator_aliases: list[str],
    result_kind: str,
    notes: list[str],
) -> NumericDerivation | None:
    selected = _latest_complete_period(
        {
            "numerator": [fact for fact in facts if _fact_matches_aliases(fact, numerator_aliases)],
            "denominator": [fact for fact in facts if _fact_matches_aliases(fact, denominator_aliases)],
        }
    )
    if not selected:
        return None
    numerator = selected["numerator"]
    denominator = selected["denominator"]
    numerator_value = _fact_number(numerator)
    denominator_value = _fact_number(denominator)
    if numerator_value is None or denominator_value in {None, 0}:
        return None
    result = numerator_value / denominator_value
    threshold = _claim_threshold(claim, result_kind)
    comparator = _claim_comparator(claim) or ("~=" if threshold is not None else None)
    tolerance = _ratio_tolerance(threshold if threshold is not None else result)
    passed = _compare_result(result, threshold, comparator, tolerance) if threshold is not None else None
    return NumericDerivation(
        expression=expression,
        inputs={
            "numerator_fact_id": numerator.fact_id,
            "numerator_fact_name": str(numerator.fact_name or ""),
            "numerator": round(numerator_value, 6),
            "denominator_fact_id": denominator.fact_id,
            "denominator_fact_name": str(denominator.fact_name or ""),
            "denominator": round(denominator_value, 6),
            "period": _period_key(numerator),
        },
        result=round(result, 6),
        comparator=comparator,
        threshold=round(threshold, 6) if threshold is not None else None,
        passed=passed,
        tolerance=tolerance,
        notes=notes,
    )


def _derive_free_cash_flow(claim: str, facts: list[CanonicalFact]) -> NumericDerivation | None:
    selected = _latest_complete_period(
        {
            "operating_cash_flow": [
                fact for fact in facts if _fact_matches_aliases(fact, ["NetCashProvidedByUsedInOperatingActivities"])
            ],
            "capital_expenditures": [
                fact for fact in facts if _fact_matches_aliases(fact, ["PaymentsToAcquirePropertyPlantAndEquipment"])
            ],
        }
    )
    if not selected:
        return None
    cfo = selected["operating_cash_flow"]
    capex = selected["capital_expenditures"]
    cfo_value = _fact_number(cfo)
    capex_value = _fact_number(capex)
    if cfo_value is None or capex_value is None:
        return None
    result = cfo_value - abs(capex_value)
    threshold = _claim_threshold(claim, "amount")
    comparator = _claim_comparator(claim) or ("~=" if threshold is not None else None)
    tolerance = _amount_tolerance(threshold if threshold is not None else result)
    passed = _compare_result(result, threshold, comparator, tolerance) if threshold is not None else None
    return NumericDerivation(
        expression="NetCashProvidedByUsedInOperatingActivities - abs(PaymentsToAcquirePropertyPlantAndEquipment)",
        inputs={
            "operating_cash_flow_fact_id": cfo.fact_id,
            "operating_cash_flow": round(cfo_value, 6),
            "capital_expenditures_fact_id": capex.fact_id,
            "capital_expenditures": round(capex_value, 6),
            "period": _period_key(cfo),
        },
        result=round(result, 6),
        comparator=comparator,
        threshold=round(threshold, 6) if threshold is not None else None,
        passed=passed,
        tolerance=tolerance,
        notes=["derived free cash flow from operating cash flow less capital expenditures"],
    )


def _derive_net_debt(claim: str, facts: list[CanonicalFact]) -> NumericDerivation | None:
    debt_facts = [fact for fact in facts if _fact_matches_aliases(fact, _DEBT_ALIASES)]
    cash_facts = [fact for fact in facts if _fact_matches_aliases(fact, _CASH_ALIASES)]
    selected = _latest_period_with_groups({"debt": debt_facts, "cash": cash_facts})
    if not selected:
        return None
    debt_values = [_fact_number(fact) for fact in selected["debt"]]
    cash = _best_fact(selected["cash"])
    cash_value = _fact_number(cash)
    if any(value is None for value in debt_values) or cash_value is None:
        return None
    total_debt = sum(float(value) for value in debt_values if value is not None)
    result = total_debt - cash_value
    threshold = _claim_threshold(claim, "amount")
    comparator = _claim_comparator(claim) or ("~=" if threshold is not None else None)
    tolerance = _amount_tolerance(threshold if threshold is not None else result)
    passed = _compare_result(result, threshold, comparator, tolerance) if threshold is not None else None
    return NumericDerivation(
        expression="sum(Debt facts) - CashAndCashEquivalents",
        inputs={
            "debt_fact_ids": ",".join(fact.fact_id for fact in selected["debt"]),
            "total_debt": round(total_debt, 6),
            "cash_fact_id": cash.fact_id,
            "cash": round(cash_value, 6),
            "period": _period_key(cash),
        },
        result=round(result, 6),
        comparator=comparator,
        threshold=round(threshold, 6) if threshold is not None else None,
        passed=passed,
        tolerance=tolerance,
        notes=["derived net debt from debt facts less cash and cash equivalents"],
    )


def _derive_debt_to_assets(claim: str, facts: list[CanonicalFact]) -> NumericDerivation | None:
    selected = _latest_period_with_groups(
        {
            "debt": [fact for fact in facts if _fact_matches_aliases(fact, _DEBT_ALIASES)],
            "assets": [fact for fact in facts if _fact_matches_aliases(fact, ["Assets"])],
        }
    )
    if not selected:
        return None
    debt_values = [_fact_number(fact) for fact in selected["debt"]]
    assets = _best_fact(selected["assets"])
    assets_value = _fact_number(assets)
    if any(value is None for value in debt_values) or not assets_value:
        return None
    total_debt = sum(float(value) for value in debt_values if value is not None)
    result = total_debt / assets_value
    threshold = _claim_threshold(claim, "ratio")
    comparator = _claim_comparator(claim) or ("~=" if threshold is not None else None)
    tolerance = _ratio_tolerance(threshold if threshold is not None else result)
    passed = _compare_result(result, threshold, comparator, tolerance) if threshold is not None else None
    return NumericDerivation(
        expression="sum(Debt facts) / Assets",
        inputs={
            "debt_fact_ids": ",".join(fact.fact_id for fact in selected["debt"]),
            "total_debt": round(total_debt, 6),
            "assets_fact_id": assets.fact_id,
            "assets": round(assets_value, 6),
            "period": _period_key(assets),
        },
        result=round(result, 6),
        comparator=comparator,
        threshold=round(threshold, 6) if threshold is not None else None,
        passed=passed,
        tolerance=tolerance,
        notes=["derived debt-to-assets ratio from debt and assets facts"],
    )


def _derive_component_revenue_share(claim: str, facts: list[CanonicalFact]) -> NumericDerivation | None:
    total_revenue = [fact for fact in facts if _fact_matches_aliases(fact, _REVENUE_ALIASES)]
    component_revenue = [
        fact for fact in facts if _is_component_revenue_fact_for_claim(fact, claim) and not _fact_matches_aliases(fact, _REVENUE_ALIASES)
    ]
    selected = _latest_complete_period({"component": component_revenue, "total": total_revenue})
    if not selected:
        return None
    component = selected["component"]
    total = selected["total"]
    component_value = _fact_number(component)
    total_value = _fact_number(total)
    if component_value is None or total_value in {None, 0}:
        return None
    result = component_value / total_value
    threshold = _claim_threshold(claim, "ratio")
    comparator = _claim_comparator(claim) or ("~=" if threshold is not None else None)
    tolerance = _ratio_tolerance(threshold if threshold is not None else result)
    passed = _compare_result(result, threshold, comparator, tolerance) if threshold is not None else None
    return NumericDerivation(
        expression="ComponentRevenue / TotalRevenue",
        inputs={
            "component_fact_id": component.fact_id,
            "component_fact_name": str(component.fact_name or ""),
            "component": round(component_value, 6),
            "total_revenue_fact_id": total.fact_id,
            "total_revenue": round(total_value, 6),
            "period": _period_key(component),
        },
        result=round(result, 6),
        comparator=comparator,
        threshold=round(threshold, 6) if threshold is not None else None,
        passed=passed,
        tolerance=tolerance,
        notes=["derived revenue mix from component revenue divided by total revenue"],
    )


def _latest_complete_period(groups: dict[str, list[CanonicalFact]]) -> dict[str, CanonicalFact] | None:
    grouped = _facts_by_period(groups)
    complete_periods = [period for period, values in grouped.items() if all(values.get(role) for role in groups)]
    if not complete_periods:
        return None
    period = sorted(complete_periods, key=lambda item: _period_sort_key(item, grouped[item]), reverse=True)[0]
    return {role: _best_fact(grouped[period][role]) for role in groups}


def _latest_period_with_groups(groups: dict[str, list[CanonicalFact]]) -> dict[str, list[CanonicalFact]] | None:
    grouped = _facts_by_period(groups)
    complete_periods = [period for period, values in grouped.items() if all(values.get(role) for role in groups)]
    if not complete_periods:
        return None
    period = sorted(complete_periods, key=lambda item: _period_sort_key(item, grouped[item]), reverse=True)[0]
    return {role: grouped[period][role] for role in groups}


def _facts_by_period(groups: dict[str, list[CanonicalFact]]) -> dict[str, dict[str, list[CanonicalFact]]]:
    by_period: dict[str, dict[str, list[CanonicalFact]]] = {}
    for role, role_facts in groups.items():
        for fact in role_facts:
            if _fact_number(fact) is None:
                continue
            period = _period_key(fact)
            by_period.setdefault(period, {}).setdefault(role, []).append(fact)
    return by_period


def _period_sort_key(period: str, values: dict[str, list[CanonicalFact]]) -> tuple[str, str]:
    filing_dates = [fact.filing_date or "" for facts in values.values() for fact in facts]
    return (max(filing_dates, default=""), period)


def _period_key(fact: CanonicalFact) -> str:
    return fact.report_period or fact.observation_date or fact.filing_date or "unknown_period"


def _best_fact(facts: list[CanonicalFact]) -> CanonicalFact:
    return sorted(facts, key=lambda fact: (fact.parser_confidence, fact.filing_date or "", fact.fact_id), reverse=True)[0]


def _fact_number(fact: CanonicalFact | None) -> float | None:
    if not fact or not isinstance(fact.value, (int, float)):
        return None
    return float(fact.value)


def _fact_matches_aliases(fact: CanonicalFact, aliases: list[str]) -> bool:
    normalized = _normalize_fact_name(fact.fact_name)
    return any(normalized == _normalize_fact_name(alias) for alias in aliases)


def _is_component_revenue_share_claim(lower_claim: str) -> bool:
    return bool(
        ("revenue" in lower_claim or "sales" in lower_claim)
        and re.search(r"\b(percent|%|share|mix|portion|represented|accounted for|of total)\b", lower_claim)
    )


def _is_component_revenue_fact_for_claim(fact: CanonicalFact, claim: str) -> bool:
    fact_tokens = set(_tokenize_fact_name(fact.fact_name))
    if not ({"revenue", "sales"} & fact_tokens):
        return False
    claim_tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", claim.lower())
        if len(token) > 2
        and token
        not in {
            "the",
            "and",
            "for",
            "with",
            "from",
            "total",
            "revenue",
            "sales",
            "represented",
            "accounted",
            "latest",
            "quarter",
            "year",
            "fiscal",
            "reported",
        }
    }
    return bool(fact_tokens & claim_tokens)


def _normalize_fact_name(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _tokenize_fact_name(name: str | None) -> list[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name or "")
    return [token.lower() for token in re.split(r"[^A-Za-z0-9]+", spaced) if len(token) > 2]


def _claim_threshold(claim: str, result_kind: str) -> float | None:
    for raw in extract_substantive_numbers(claim):
        if _is_period_marker(raw):
            continue
        parsed = _parse_number(raw)
        if not parsed:
            continue
        value, number_kind = parsed
        if result_kind in {"ratio", "plain_ratio"}:
            if number_kind == "percent":
                return value / 100
            if number_kind == "bps":
                return value / 10_000
            if result_kind == "plain_ratio" and number_kind == "plain":
                return value
        if result_kind == "amount" and number_kind in {"amount", "plain"}:
            return value
    return None


def _claim_comparator(claim: str) -> str | None:
    lower = claim.lower()
    if re.search(r"\b(at least|more than|greater than|above|over|exceed(?:ed|s)?|higher than)\b|超过|高于|至少", lower):
        return ">="
    if re.search(r"\b(less than|below|under|lower than|no more than|at most)\b|低于|少于|不超过", lower):
        return "<="
    return None


def _compare_result(result: float, threshold: float | None, comparator: str | None, tolerance: float) -> bool | None:
    if threshold is None or comparator is None:
        return None
    if comparator == ">=":
        return result >= threshold - tolerance
    if comparator == "<=":
        return result <= threshold + tolerance
    return abs(result - threshold) <= tolerance


def _ratio_tolerance(value: float | None) -> float:
    scale = abs(value or 0)
    return max(0.005, scale * 0.012)


def _amount_tolerance(value: float | None) -> float:
    scale = max(abs(value or 0), 1.0)
    return max(1.0, scale * 0.012)


def _parse_number(value: str) -> tuple[float, str] | None:
    compact = re.sub(r"[\s,$,]", "", value.lower()).replace("percent", "%")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", compact)
    if not match:
        return None
    number = float(match.group(0))
    if "%" in compact:
        return number, "percent"
    if "bps" in compact:
        return number, "bps"
    if "trillion" in compact:
        return number * 1_000_000_000_000, "amount"
    if "billion" in compact or "bn" in compact:
        return number * 1_000_000_000, "amount"
    if "million" in compact or "mn" in compact:
        return number * 1_000_000, "amount"
    if "亿" in compact:
        return number * 100_000_000, "amount"
    if "万" in compact:
        return number * 10_000, "amount"
    if "$" in compact or "美元" in compact:
        return number, "amount"
    return number, "plain"


def _is_period_marker(value: str) -> bool:
    parsed = _parse_number(value)
    if not parsed or parsed[1] != "plain":
        return False
    number = int(parsed[0])
    return 1900 <= number <= 2100 or 1 <= number <= 4


def _is_growth_claim(claim: str) -> bool:
    return bool(re.search(
        r"\b(grew|growth|increased|decreased|declined|higher|lower|"
        r"year[- ]over[- ]year|yoy|qoq|quarter[- ]over[- ]quarter|同比|环比)\b",
        claim, re.IGNORECASE,
    ))


def _expects_positive_growth(claim: str) -> bool:
    return not bool(re.search(r"\b(decreased|declined|lower|fell|down|下降|减少)\b", claim, re.IGNORECASE))


def _fact_matches_claim(fact_name: str, claim: str) -> bool:
    lower_fact = fact_name.lower()
    lower_claim = claim.lower()
    if "revenue" in lower_claim or "sales" in lower_claim:
        return "revenue" in lower_fact or "sales" in lower_fact
    if "income" in lower_claim or "earnings" in lower_claim:
        return "income" in lower_fact or "earnings" in lower_fact
    if "cash flow" in lower_claim:
        return "cash" in lower_fact and "flow" in lower_fact
    if "debt" in lower_claim or "leverage" in lower_claim:
        return "debt" in lower_fact or "borrowings" in lower_fact
    return True
