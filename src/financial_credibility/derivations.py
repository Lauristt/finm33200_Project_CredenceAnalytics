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
    if numeric_check.verdict == VerificationVerdict.NOT_APPLICABLE.value:
        return None
    return NumericDerivation(
        expression="numeric_verification",
        result=numeric_check.verdict,
        passed=numeric_check.verdict in {VerificationVerdict.VERIFIED.value, VerificationVerdict.PARTIALLY_VERIFIED.value},
        notes=[numeric_check.summary],
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
    prior, current = pairs[-1]
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
            "current": current_value,
            "prior_fact_id": prior.fact_id,
            "prior": prior_value,
        },
        result=round(result, 6),
        comparator=comparator,
        threshold=round(target, 6) if isinstance(target, float) else 0,
        passed=passed,
        tolerance=0.0,
        notes=["growth claim derived from canonical facts"],
    )


def _candidate_growth_pairs(facts: list[CanonicalFact]) -> list[tuple[CanonicalFact, CanonicalFact]]:
    pairs = []
    by_concept: dict[tuple[str, str], list[CanonicalFact]] = {}
    for fact in facts:
        kind = _period_kind(fact.report_period)
        if not kind:
            continue
        key = (str(fact.fact_name), kind)
        by_concept.setdefault(key, []).append(fact)
    for grouped in by_concept.values():
        ordered = sorted(grouped, key=lambda fact: (fact.filing_date or "", fact.report_period or ""))
        for prior, current in zip(ordered, ordered[1:]):
            if prior.report_period != current.report_period:
                pairs.append((prior, current))
    return pairs


def _has_duplicate_period_values(facts: list[CanonicalFact]) -> bool:
    seen: dict[tuple[str, str], set[float]] = {}
    for fact in facts:
        if not fact.fact_name or not fact.report_period or not isinstance(fact.value, (int, float)):
            continue
        key = (fact.fact_name, fact.report_period)
        seen.setdefault(key, set()).add(float(fact.value))
    return any(len(values) > 1 for values in seen.values())


def _period_kind(period: str | None) -> str | None:
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
    return bool(re.search(r"\b(grew|growth|increased|decreased|declined|higher|lower|year over year|yoy|同比)\b", claim, re.IGNORECASE))


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
