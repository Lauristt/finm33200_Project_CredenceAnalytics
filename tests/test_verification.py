import unittest

from financial_credibility.models import (
    ArgumentType,
    Evidence,
    SourceTier,
    SourceType,
    VerificationCheck,
)
from financial_credibility.verification import verify_logic_claim, verify_numeric_claim


class CapturingJudge:
    def __init__(self):
        self.first_url = None

    def judge_logic_claim(self, claim, evidence, argument_type):
        self.first_url = evidence[0].url
        return VerificationCheck(
            check_type="logic_check",
            verdict="supported",
            confidence=0.8,
            summary="ok",
            evidence_urls=[item.url for item in evidence],
            method="test",
        )


class VerificationTests(unittest.TestCase):
    def test_logic_judge_gets_high_numeric_evidence_first(self):
        low_match = Evidence(
            url="https://example.com/general",
            title="General source",
            text="A general article.",
            source_type=SourceType.FINANCIAL_MEDIA,
            source_tier=SourceTier.T3,
            domain="example.com",
            source_authority=0.8,
            relevance_score=0.7,
            numeric_consistency_score=0.1,
            support_score=0.7,
        )
        numeric_match = Evidence(
            url="https://example.com/income-statement",
            title="Income statement",
            text="Revenue 416161000000 in 2025.",
            source_type=SourceType.DATA_VENDOR,
            source_tier=SourceTier.T3,
            domain="example.com",
            source_authority=0.6,
            relevance_score=0.5,
            numeric_consistency_score=0.95,
            support_score=0.5,
        )
        judge = CapturingJudge()

        verify_logic_claim(
            "Apple reported revenue of 416161000000 in fiscal 2025.",
            [low_match, numeric_match],
            ArgumentType.METRIC_FACT,
            judge,
        )

        self.assertEqual(judge.first_url, "https://example.com/income-statement")

    def test_logic_judge_gets_historical_price_evidence_first(self):
        historical = Evidence(
            url="https://example.com/history",
            title="FMP 10-month historical prices for NVDA",
            text="historical daily close prices; oscillation_signal moderate.",
            source_type=SourceType.DATA_VENDOR,
            source_tier=SourceTier.T3,
            domain="example.com",
            numeric_consistency_score=0.1,
            support_score=0.1,
        )
        general = Evidence(
            url="https://example.com/profile",
            title="Company profile",
            text="Current price snapshot.",
            source_type=SourceType.DATA_VENDOR,
            source_tier=SourceTier.T3,
            domain="example.com",
            numeric_consistency_score=0.9,
            support_score=0.9,
        )
        judge = CapturingJudge()

        verify_logic_claim(
            "Nvidia's stock price seems like oscillating these months (10 months).",
            [general, historical],
            ArgumentType.OPINION_ANALYSIS,
            judge,
        )

        self.assertEqual(judge.first_url, "https://example.com/history")

    def test_numeric_check_ignores_lookback_duration(self):
        evidence = [
            Evidence(
                url="https://example.com/history",
                title="Historical prices",
                text="Daily prices over approximately 10 months.",
                source_type=SourceType.DATA_VENDOR,
                source_tier=SourceTier.T4,
                domain="example.com",
            )
        ]

        check = verify_numeric_claim(
            "Nvidia's stock price seems like oscillating these months (10 months).",
            evidence,
        )

        self.assertEqual(check.verdict, "not_applicable")

    def test_numeric_check_requires_all_material_numbers_to_match(self):
        evidence = [
            Evidence(
                url="https://data.sec.gov/example",
                title="SEC Company Facts for NVDA",
                text="Revenues (USD) 2027 Q1: 81,615,000,000 filed 2026-05-20 form 10-Q.",
                source_type=SourceType.SEC_FILING,
                source_tier=SourceTier.T1,
                domain="data.sec.gov",
            )
        ]

        check = verify_numeric_claim(
            "In fiscal 2027 Q1, NVIDIA reported total revenue of $81.6 billion, up 85% year over year.",
            evidence,
        )

        self.assertEqual(check.verdict, "partially_verified")
        self.assertTrue(any("matched $81.6 billion" in issue for issue in check.issues))
        self.assertIn("unmatched claim numbers: 85%", check.issues)
        self.assertFalse(any(issue.startswith("matched 1 with") for issue in check.issues))
        self.assertFalse(any(issue.startswith("matched 2027 with") for issue in check.issues))

    def test_numeric_check_does_not_let_guidance_number_veto_reported_fact(self):
        evidence = [
            Evidence(
                url="https://www.sec.gov/example",
                title="Company filing",
                text="Apple reported quarterly revenue of $102.5 billion.",
                source_type=SourceType.SEC_FILING,
                source_tier=SourceTier.T1,
                domain="sec.gov",
            )
        ]

        check = verify_numeric_claim(
            "Apple reported quarterly revenue of $102.5 billion and expects next-quarter revenue of $110 billion.",
            evidence,
        )

        self.assertEqual(check.verdict, "verified")
        self.assertTrue(any("matched $102.5 billion" in issue for issue in check.issues))
        self.assertTrue(any("contextual forward-looking numbers" in issue for issue in check.issues))

    def test_numeric_check_ignores_reporting_date_day_number(self):
        evidence = [
            Evidence(
                url="https://www.microsoft.com/en-us/investor/example",
                title="Microsoft FY26 Q3 earnings release",
                text="Revenue was $82.9 billion and increased 18% year over year for the quarter ended March 31, 2026.",
                source_type=SourceType.COMPANY_IR,
                source_tier=SourceTier.T2,
                domain="microsoft.com",
            )
        ]

        check = verify_numeric_claim(
            "Microsoft reported fiscal third-quarter revenue of $82.9 billion for the quarter ended March 31, 2026, up 18% year over year.",
            evidence,
        )

        self.assertEqual(check.verdict, "verified")
        self.assertTrue(any("matched $82.9 billion" in issue for issue in check.issues))
        self.assertTrue(any("matched 18%" in issue for issue in check.issues))
        self.assertFalse(any("31" in issue for issue in check.issues))

    def test_numeric_check_keeps_eps_decimal_values(self):
        evidence = [
            Evidence(
                url="https://investor.nvidia.com/example",
                title="NVIDIA quarterly results",
                text="GAAP diluted EPS was $2.39, and non-GAAP diluted EPS was $1.87.",
                source_type=SourceType.COMPANY_IR,
                source_tier=SourceTier.T2,
                domain="investor.nvidia.com",
            )
        ]

        gaap = verify_numeric_claim("GAAP diluted EPS was $2.39.", evidence)
        non_gaap = verify_numeric_claim("non-GAAP diluted EPS was $1.87.", evidence)

        self.assertEqual(gaap.verdict, "verified")
        self.assertEqual(non_gaap.verdict, "verified")
        self.assertTrue(any("matched $2.39" in issue for issue in gaap.issues))
        self.assertTrue(any("matched $1.87" in issue for issue in non_gaap.issues))

    def test_numeric_check_matches_chinese_hundred_million_amounts(self):
        evidence = [
            Evidence(
                url="https://data.sec.gov/example",
                title="SEC Company Facts for NVDA",
                text="Revenues (USD) 2027 Q1: 81,615,000,000; revenue was up 85 percent year over year.",
                source_type=SourceType.SEC_FILING,
                source_tier=SourceTier.T1,
                domain="data.sec.gov",
            )
        ]

        check = verify_numeric_claim(
            "在 2027 财年第一季度，NVIDIA 报告总收入为 816 亿美元，同比增长 85%。",
            evidence,
        )

        self.assertEqual(check.verdict, "verified")
        self.assertTrue(any("matched 816 亿美元" in issue for issue in check.issues))
        self.assertTrue(any("matched 85%" in issue for issue in check.issues))

    def test_numeric_check_ignores_index_name_number_and_matches_computed_return(self):
        evidence = [
            Evidence(
                url="https://financialmodelingprep.com/example",
                title="FMP historical prices for S&P 500 Index",
                text=(
                    "S&P 500 Index historical daily close prices; "
                    "latest_daily_calculation previous_close 7473.46 to end_close 7519.12; "
                    "latest_daily_point_change 45.66; latest_daily_return_pct 0.61%."
                ),
                source_type=SourceType.DATA_VENDOR,
                source_tier=SourceTier.T3,
                domain="financialmodelingprep.com",
            )
        ]

        check = verify_numeric_claim(
            "The S&P 500 added 0.6% Tuesday after trading resumed following Monday's holiday.",
            evidence,
        )

        self.assertEqual(check.verdict, "verified")
        self.assertTrue(any("matched 0.6%" in issue for issue in check.issues))
        self.assertFalse(any("matched 500" in issue for issue in check.issues))

    def test_numeric_check_matches_index_point_return_and_close_claim(self):
        evidence = [
            Evidence(
                url="https://financialmodelingprep.com/example",
                title="FMP historical prices for S&P 500 Index",
                text=(
                    "S&P 500 Index historical daily close prices; "
                    "latest_daily_calculation previous_close 7473.47 to end_close 7519.12; "
                    "latest_daily_point_change 45.65; latest_daily_return_pct 0.61%."
                ),
                source_type=SourceType.DATA_VENDOR,
                source_tier=SourceTier.T3,
                domain="financialmodelingprep.com",
            )
        ]

        check = verify_numeric_claim(
            "The S&P 500 rose 45.65 points, or 0.6%, to 7,519.12.",
            evidence,
        )

        self.assertEqual(check.verdict, "verified")
        self.assertFalse(any("matched 500" in issue for issue in check.issues))
        self.assertTrue(any("matched 45.65" in issue for issue in check.issues))
        self.assertTrue(any("matched 0.6%" in issue for issue in check.issues))
        self.assertTrue(any("matched 7,519.12" in issue for issue in check.issues))


if __name__ == "__main__":
    unittest.main()
