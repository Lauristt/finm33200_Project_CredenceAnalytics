import unittest

from financial_credibility import FinancialCredibilityToolkit
from financial_credibility.config import ToolkitConfig
from financial_credibility.models import CredibilityLabel, Verdict


class ToolkitTests(unittest.TestCase):
    def test_build_evidence_pack_with_prefetched_results(self):
        toolkit = FinancialCredibilityToolkit(ToolkitConfig())
        pack = toolkit.build_evidence_pack(
            claim="Apple revenue grew 6% year over year in the latest quarter.",
            ticker="AAPL",
            as_of_date="2025-11-01",
            prefetched_results=[
                {
                    "title": "Apple reports fourth quarter results",
                    "url": "https://www.apple.com/newsroom/2025/10/apple-reports-fourth-quarter-results/",
                    "snippet": "Apple reported quarterly revenue of $102.5 billion, up 6 percent year over year.",
                    "published_at": "2025-10-30",
                },
                {
                    "title": "Apple Form 10-K",
                    "url": "https://www.sec.gov/Archives/edgar/data/320193/example/aapl-20250927.htm",
                    "snippet": "Apple reported quarterly revenue up 6 percent year over year in the filing.",
                    "published_at": "2025-10-31",
                },
            ],
        )

        self.assertIn(pack.verdict, {Verdict.SUPPORTED, Verdict.MIXED})
        self.assertIn(
            pack.credibility_label,
            {
                CredibilityLabel.MEDIUM,
                CredibilityLabel.HIGH,
                CredibilityLabel.VERY_HIGH,
            },
        )
        self.assertGreater(pack.credibility_score, 0.55)
        self.assertEqual(len(pack.evidence), 2)
        self.assertIsNotNone(pack.numeric_check)
        self.assertIsNotNone(pack.logic_check)
        self.assertIsNotNone(pack.source_check)
        self.assertIsNotNone(pack.overall_conclusion)
        self.assertEqual(pack.numeric_check.verdict, "verified")
        self.assertIn(pack.overall_conclusion.overall_label, {"High", "Very High", "Medium"})


if __name__ == "__main__":
    unittest.main()
