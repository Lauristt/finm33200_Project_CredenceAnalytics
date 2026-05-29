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

    def test_company_ir_source_is_issuer_primary(self):
        result = assess_source("https://www.microsoft.com/en-us/investor/earnings/FY-2026-Q3/press-release-webcast")
        self.assertEqual(result.source_type, SourceType.COMPANY_IR)
        self.assertEqual(result.source_tier, SourceTier.T2)
        self.assertTrue(result.is_official_primary)

    def test_company_investor_relations_pdf_is_issuer_primary(self):
        result = assess_source(
            "https://www.jpmorganchase.com/content/dam/jpmc/jpmorgan-chase-and-co/"
            "investor-relations/documents/quarterly-earnings/2026/1st-quarter/example.pdf"
        )
        self.assertEqual(result.source_type, SourceType.COMPANY_IR)
        self.assertTrue(result.is_official_primary)

    def test_media_repost_with_investor_slug_is_not_issuer_primary(self):
        stocktitan = assess_source(
            "https://www.stocktitan.net/news/MSFT/"
            "microsoft-earnings-press-release-available-on-investor-relations-rn9bi49aqird.html"
        )
        prnewswire = assess_source(
            "https://www.prnewswire.com/news-releases/"
            "microsoft-earnings-press-release-available-on-investor-relations-website-302757900.html"
        )

        self.assertFalse(stocktitan.is_official_primary)
        self.assertFalse(prnewswire.is_official_primary)

    def test_numeric_consistency_matches_percent(self):
        score, _ = score_numeric_consistency(
            "Apple revenue grew 6% year over year.",
            "Apple reported quarterly revenue up 6 percent year over year.",
        )
        self.assertGreaterEqual(score, 0.9)


if __name__ == "__main__":
    unittest.main()
