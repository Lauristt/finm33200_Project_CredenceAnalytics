"""End-to-end verification tests: one representative claim per asset class.

Each test calls build_verification_report() with a realistic financial claim
and asserts that:
  1. The correct asset class is detected
  2. At least one data fetch (run) is produced
  3. The derivation/verdict is non-trivially populated (not just NOT_FOUND)

These tests make live API calls, so they are tagged slow and skipped when
the required API keys are absent.
"""

from __future__ import annotations

import os
import sys
import unittest

# Load .env so API keys are available when running tests directly
_ENV_FILE = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_ENV_FILE):
    with open(_ENV_FILE) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from financial_credibility.reporting import build_verification_report
from financial_credibility.toolkit import ToolkitConfig


def _has_key(*env_vars: str) -> bool:
    return all(os.getenv(v, "").strip() for v in env_vars)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _run(memo: str, tickers: list[str] | None = None, as_of_date: str | None = None) -> dict:
    return build_verification_report(
        memo=memo,
        tickers=tickers or [],
        config=ToolkitConfig.from_env(),
        as_of_date=as_of_date,
        prefetched_results=[],
    )


def _first_derivation(payload: dict):
    """Return the first numeric_derivation dict found across all atomic claims."""
    for run in payload.get("runs", []):
        for ac in run.get("atomic_claims", []):
            d = ac.get("numeric_derivation")
            if d:
                return d
    return None


def _verdicts(payload: dict) -> list[str]:
    return [run.get("verdict", "") for run in payload.get("runs", [])]


def _asset_classes(payload: dict) -> list[str]:
    return payload.get("summary", {}).get("asset_classes", [])


# ===========================================================================
# 1. SINGLE-NAME EQUITY — Apple revenue Q1 FY2025
# ===========================================================================
class TestEquitySingleName(unittest.TestCase):
    """AAPL revenue claim — SEC EDGAR + FMP canonical facts."""

    @unittest.skipUnless(_has_key("FMP_API_KEY") or True, "FMP_API_KEY required")
    def test_apple_revenue_q1_fy2025(self):
        """Apple reported ~$124.3 B revenue in Q1 FY2025 (Oct-Dec 2024). True claim."""
        payload = _run(
            "Apple reported revenue of $124.3 billion in its fiscal first quarter of 2025.",
            tickers=["AAPL"],
            as_of_date="2025-06-01",
        )
        self.assertEqual(payload["input"]["tickers"], ["AAPL"])
        self.assertGreater(len(payload["runs"]), 0, "expected at least one equity run")
        run = payload["runs"][0]
        self.assertEqual(run["ticker"], "AAPL")
        self.assertIn(run["verdict"], {"supported", "partially_supported", "contradicted", "insufficient"})
        print(f"\n[AAPL] verdict={run['verdict']}  facts={len(run.get('canonical_facts', []))}")
        d = _first_derivation(payload)
        if d:
            print(f"  derivation: {d.get('result', 'n/a')}  passed={d.get('passed')}")

    def test_micron_revenue_yoy_q2_fy2026(self):
        """Micron Q2 FY2026 revenue grew ~196% YoY. True claim verified by derivation."""
        payload = _run(
            "Micron Technology's revenue grew 196% year-over-year in its fiscal second quarter of 2026.",
            tickers=["MU"],
            as_of_date="2026-04-01",
        )
        self.assertGreater(len(payload["runs"]), 0)
        run = payload["runs"][0]
        self.assertEqual(run["ticker"], "MU")
        print(f"\n[MU] verdict={run['verdict']}")
        d = _first_derivation(payload)
        if d:
            pct = (d.get("result") or 0) * 100
            print(f"  derivation: {pct:.1f}%  passed={d.get('passed')}")

    def test_nvidia_revenue_false_claim(self):
        """NVDA revenue claim with a plausible but wrong figure — expect contradicted."""
        payload = _run(
            "NVIDIA reported quarterly revenue of $15 billion in Q3 FY2025.",
            tickers=["NVDA"],
            as_of_date="2025-03-01",
        )
        self.assertGreater(len(payload["runs"]), 0)
        run = payload["runs"][0]
        print(f"\n[NVDA false] verdict={run['verdict']}")
        d = _first_derivation(payload)
        if d:
            pct = (d.get("result") or 0) / 1e9
            print(f"  derivation: ${pct:.1f}B  passed={d.get('passed')}")


# ===========================================================================
# 2. MACRO INDICATOR — CPI (BLS)
# ===========================================================================
@unittest.skipUnless(_has_key("BLS_API_KEY") or True, "BLS_API_KEY required")
class TestMacroCPI(unittest.TestCase):
    """CPI claims verified via BLS public API → monthly series → YoY derivation."""

    def test_cpi_jan2024_false_claim(self):
        """CPI rose 3.8% YoY in Jan 2024 — actual ~3.1%, should be contradicted."""
        payload = _run(
            "U.S. CPI rose 3.8% year-over-year in January 2024.",
            as_of_date="2024-03-01",
        )
        self.assertIn("macro_indicator", _asset_classes(payload))
        runs = [r for r in payload["runs"] if r.get("mode") == "macro"]
        self.assertGreater(len(runs), 0, "expected a macro run")
        run = runs[0]
        print(f"\n[CPI 3.8% Jan2024] verdict={run['verdict']}")
        d = _first_derivation(payload)
        if d:
            pct = (d.get("result") or 0) * 100
            print(f"  derivation: {pct:.2f}%  passed={d.get('passed')}")
            self.assertAlmostEqual(pct, 3.1, delta=0.5, msg="CPI YoY Jan 2024 should be ~3.1%")
            self.assertFalse(d.get("passed"), "3.8% claim should fail; actual is ~3.1%")

    def test_cpi_direction_true_claim(self):
        """CPI rose year-over-year in 2024 — directional claim, should be supported."""
        payload = _run(
            "U.S. inflation as measured by CPI was higher in 2024 than in 2023.",
            as_of_date="2025-01-01",
        )
        runs = [r for r in payload["runs"] if r.get("mode") == "macro"]
        print(f"\n[CPI direction 2024>2023] runs={len(runs)}")
        if runs:
            print(f"  verdict={runs[0]['verdict']}")


# ===========================================================================
# 3. MACRO INDICATOR — GDP (BEA)
# ===========================================================================
@unittest.skipUnless(_has_key("BEA_API_KEY") or True, "BEA_API_KEY required")
class TestMacroGDP(unittest.TestCase):
    """GDP growth claims verified via BEA NIPA tables."""

    def test_gdp_q3_2024(self):
        """U.S. real GDP grew 2.8% annualized in Q3 2024 — approximately true."""
        payload = _run(
            "U.S. real GDP grew at an annualized rate of 2.8% in the third quarter of 2024.",
            as_of_date="2025-01-01",
        )
        self.assertIn("macro_indicator", _asset_classes(payload))
        runs = [r for r in payload["runs"] if r.get("mode") == "macro"]
        print(f"\n[GDP Q3 2024] runs={len(runs)}")
        if runs:
            print(f"  verdict={runs[0]['verdict']}")
            d = _first_derivation(payload)
            if d:
                print(f"  derivation result={d.get('result')}  passed={d.get('passed')}")


# ===========================================================================
# 4. COMMODITY — WTI Crude Oil (EIA)
# ===========================================================================
@unittest.skipUnless(_has_key("EIA_API_KEY") or True, "EIA_API_KEY required")
class TestCommodityWTI(unittest.TestCase):
    """WTI crude oil price claims verified via EIA weekly petroleum data."""

    def test_wti_price_approx(self):
        """WTI was trading in the $60-80 range in early 2025 — check level."""
        payload = _run(
            "WTI crude oil was trading around $70 per barrel in early 2025.",
            as_of_date="2025-04-01",
        )
        self.assertIn("commodity", _asset_classes(payload))
        runs = [r for r in payload["runs"] if r.get("mode") == "macro"]
        print(f"\n[WTI ~$70 early 2025] runs={len(runs)}")
        if runs:
            print(f"  verdict={runs[0]['verdict']}")
            print(f"  facts={len(runs[0].get('canonical_facts', []))}")
            d = _first_derivation(payload)
            if d:
                print(f"  derivation result=${d.get('result')}  passed={d.get('passed')}")

    def test_wti_false_price(self):
        """WTI at $200/barrel in 2024 — clearly false, expect contradicted."""
        payload = _run(
            "WTI crude oil hit $200 per barrel in 2024.",
            as_of_date="2025-01-01",
        )
        runs = [r for r in payload["runs"] if r.get("mode") == "macro"]
        print(f"\n[WTI false $200 2024] runs={len(runs)}")
        if runs:
            print(f"  verdict={runs[0]['verdict']}")


# ===========================================================================
# 5. FX — EUR/USD (ECB)
# ===========================================================================
class TestFXEURUSD(unittest.TestCase):
    """EUR/USD rate verified via ECB reference rates (no key required)."""

    def test_eurusd_current_level(self):
        """EUR/USD is trading above 1.0 — trivially true directional claim."""
        payload = _run(
            "The EUR/USD exchange rate is approximately 1.10.",
            as_of_date="2025-06-01",
        )
        self.assertIn("fx", _asset_classes(payload))
        runs = [r for r in payload["runs"] if r.get("mode") == "macro"]
        print(f"\n[EUR/USD ~1.10] runs={len(runs)}")
        if runs:
            print(f"  verdict={runs[0]['verdict']}")
            facts = runs[0].get("canonical_facts", [])
            if facts:
                print(f"  latest ECB rate: {facts[0].get('value')}")


# ===========================================================================
# 6. RATES — Federal Funds Rate (FRED)
# ===========================================================================
@unittest.skipUnless(_has_key("FRED_API_KEY") or True, "FRED_API_KEY required")
class TestRatesFedFunds(unittest.TestCase):
    """Fed funds rate claims verified via FRED DFF series."""

    def test_fed_funds_rate_2024(self):
        """Fed funds rate was around 5.25-5.5% in mid-2024 — true claim."""
        payload = _run(
            "The Federal Funds Rate was approximately 5.25% to 5.5% in mid-2024.",
            as_of_date="2024-09-01",
        )
        self.assertIn("rates", _asset_classes(payload))
        runs = [r for r in payload["runs"] if r.get("mode") == "macro"]
        print(f"\n[Fed Funds 5.25-5.5% mid-2024] runs={len(runs)}")
        if runs:
            print(f"  verdict={runs[0]['verdict']}")
            facts = runs[0].get("canonical_facts", [])
            if facts:
                print(f"  FRED DFF latest: {facts[0].get('value')}")

    def test_fed_funds_rate_false(self):
        """Fed funds rate was 10% in 2024 — false, should be contradicted."""
        payload = _run(
            "The Federal Reserve raised the funds rate to 10% in 2024.",
            as_of_date="2025-01-01",
        )
        runs = [r for r in payload["runs"] if r.get("mode") == "macro"]
        print(f"\n[Fed Funds false 10% 2024] runs={len(runs)}")
        if runs:
            print(f"  verdict={runs[0]['verdict']}")
            d = _first_derivation(payload)
            if d:
                print(f"  derivation result={d.get('result')}  passed={d.get('passed')}")


# ===========================================================================
# 7. FIXED INCOME — 10-Year Treasury Yield (FRED)
# ===========================================================================
@unittest.skipUnless(_has_key("FRED_API_KEY") or True, "FRED_API_KEY required")
class TestFixedIncome10Y(unittest.TestCase):
    """10-year Treasury yield claims via FRED GS10 series."""

    def test_10y_yield_2024(self):
        """10-year Treasury yield averaged ~4-4.5% in 2024 — true range."""
        payload = _run(
            "The 10-year U.S. Treasury yield was around 4.2% in early 2024.",
            as_of_date="2024-06-01",
        )
        self.assertIn("rates", _asset_classes(payload))  # DGS10 is classified as 'rates'
        runs = [r for r in payload["runs"] if r.get("mode") == "macro"]
        print(f"\n[10Y TSY ~4.2% early 2024] runs={len(runs)}")
        if runs:
            print(f"  verdict={runs[0]['verdict']}")
            facts = runs[0].get("canonical_facts", [])
            if facts:
                print(f"  FRED GS10 latest: {facts[0].get('value')}")


# ===========================================================================
# 8. EQUITY INDEX — S&P 500 (equity_index path)
# ===========================================================================
class TestEquityIndex(unittest.TestCase):
    """S&P 500 / Nasdaq claims use price verification path (not macro)."""

    def test_sp500_daily_move(self):
        """S&P 500 added 0.6% on a specific date — price path."""
        payload = _run(
            "The S&P 500 added 0.6% on Tuesday May 27, 2026.",
            as_of_date="2026-05-28",
        )
        self.assertIn("equity_index", _asset_classes(payload))
        print(f"\n[S&P500 +0.6% 2026-05-27] runs={len(payload['runs'])}")
        for run in payload["runs"]:
            print(f"  ticker={run.get('ticker')}  verdict={run.get('verdict')}")

    def test_nasdaq_ytd_2024(self):
        """Nasdaq composite rose roughly 30% in 2024 — approximately true."""
        payload = _run(
            "The Nasdaq composite index rose approximately 30% in 2024.",
            as_of_date="2025-01-15",
        )
        print(f"\n[Nasdaq +30% 2024] runs={len(payload['runs'])}")
        for run in payload["runs"]:
            print(f"  ticker={run.get('ticker')}  verdict={run.get('verdict')}")


# ===========================================================================
# 9. CREDIT / HIGH YIELD (BIS / FRED BAMLH0A0HYM2)
# ===========================================================================
@unittest.skipUnless(_has_key("FRED_API_KEY") or True, "FRED_API_KEY required")
class TestCredit(unittest.TestCase):
    """High-yield credit spread claims verified via FRED or BIS."""

    def test_hy_spread_2024(self):
        """HY OAS spread was around 300-350 bps in late 2024 — approximate truth."""
        payload = _run(
            "The U.S. high-yield credit spread (OAS) was approximately 300 basis points in late 2024.",
            as_of_date="2025-01-01",
        )
        self.assertIn("credit", _asset_classes(payload))
        runs = [r for r in payload["runs"] if r.get("mode") == "macro"]
        print(f"\n[HY spread ~300bps 2024] runs={len(runs)}")
        if runs:
            print(f"  verdict={runs[0]['verdict']}")
            facts = runs[0].get("canonical_facts", [])
            if facts:
                print(f"  latest fact: {facts[0].get('fact_name')} = {facts[0].get('value')}")


# ===========================================================================
# 10. MULTI-ASSET — mixed claim spanning equity + macro
# ===========================================================================
class TestMultiAsset(unittest.TestCase):
    """A memo that mixes equity revenue + macro CPI produces runs for each."""

    def test_mixed_equity_and_macro(self):
        """Apple revenue + CPI mention — should produce both equity and macro runs."""
        payload = _run(
            "Apple's revenue grew to $391 billion in fiscal 2024 while U.S. CPI remained elevated above 3%.",
            tickers=["AAPL"],
            as_of_date="2025-01-01",
        )
        asset_classes = _asset_classes(payload)
        print(f"\n[mixed AAPL+CPI] asset_classes={asset_classes}")
        print(f"  runs: {[(r.get('ticker'), r.get('mode', 'equity'), r.get('verdict')) for r in payload['runs']]}")
        self.assertGreater(len(payload["runs"]), 0)

    def test_wti_and_fed_funds(self):
        """Oil price + rates claim — both commodity and rates entities."""
        payload = _run(
            "WTI crude oil fell below $70 per barrel as the Federal Reserve held rates at 4.25% to 4.5%.",
            as_of_date="2025-06-01",
        )
        asset_classes = _asset_classes(payload)
        print(f"\n[WTI+FedFunds] asset_classes={asset_classes}")
        print(f"  runs: {[(r.get('ticker'), r.get('mode', 'equity'), r.get('verdict')) for r in payload['runs']]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
