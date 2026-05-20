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


if __name__ == "__main__":
    unittest.main()
