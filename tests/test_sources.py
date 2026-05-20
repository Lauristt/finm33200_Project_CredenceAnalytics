import unittest

from financial_credibility.models import SourceTier, SourceType
from financial_credibility.sources import assess_source, score_numeric_consistency


class SourceScoringTests(unittest.TestCase):
    def test_sec_source_scores_as_t1(self):
        result = assess_source("https://www.sec.gov/Archives/edgar/data/example")
        self.assertEqual(result.source_type, SourceType.SEC_FILING)
        self.assertEqual(result.source_tier, SourceTier.T1)
        self.assertGreaterEqual(result.authority_score, 0.95)

    def test_reddit_source_scores_low(self):
        result = assess_source("https://www.reddit.com/r/stocks/comments/example")
        self.assertEqual(result.source_type, SourceType.SOCIAL_FORUM)
        self.assertLess(result.authority_score, 0.3)

    def test_numeric_consistency_matches_percent(self):
        score, _ = score_numeric_consistency(
            "Apple revenue grew 6% year over year.",
            "Apple reported quarterly revenue up 6 percent year over year.",
        )
        self.assertGreaterEqual(score, 0.9)


if __name__ == "__main__":
    unittest.main()
