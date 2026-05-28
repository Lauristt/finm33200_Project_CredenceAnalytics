import unittest

from financial_credibility.time_context import infer_time_context


class TimeContextTests(unittest.TestCase):
    def test_explicit_event_date_wins_over_publication_date(self):
        context = infer_time_context(
            "How major US stock indexes fared Tuesday 5/26/2026. Published 05/27/2026, 04:26 PM."
        )

        self.assertEqual(context.effective_as_of_date, "2026-05-26")
        self.assertEqual(context.event_date, "2026-05-26")
        self.assertEqual(context.publication_date, "2026-05-27")
        self.assertEqual(context.source, "explicit_event_date")

    def test_weekday_resolves_against_anchor_date(self):
        context = infer_time_context("The S&P 500 added 0.6% Tuesday.", anchor_date="2026-05-27")

        self.assertEqual(context.effective_as_of_date, "2026-05-26")
        self.assertEqual(context.source, "relative_context_date")

    def test_first_weekday_mention_wins_when_multiple_weekdays_appear(self):
        context = infer_time_context(
            "The S&P 500 added 0.6% Tuesday after trading resumed following Monday's holiday.",
            anchor_date="2026-05-27",
        )

        self.assertEqual(context.effective_as_of_date, "2026-05-26")
        self.assertEqual(context.source, "relative_context_date")

    def test_publication_date_is_fallback_when_no_event_date_exists(self):
        context = infer_time_context("Published 05/20/2026, 04:26 PM. Nvidia revenue rose.")

        self.assertEqual(context.effective_as_of_date, "2026-05-20")
        self.assertEqual(context.publication_date, "2026-05-20")
        self.assertEqual(context.source, "publication_date")

    def test_month_day_without_year_uses_anchor_year(self):
        context = infer_time_context("May 20 (Reuters) - Nvidia shares rose.", anchor_date="2026-05-27")

        self.assertEqual(context.effective_as_of_date, "2026-05-20")
        self.assertEqual(context.source, "explicit_event_date")

    def test_user_as_of_date_wins_when_supplied(self):
        context = infer_time_context("The S&P 500 rose on 05/26/2026.", as_of_date="2026-05-28")

        self.assertEqual(context.effective_as_of_date, "2026-05-28")
        self.assertEqual(context.event_date, "2026-05-26")
        self.assertEqual(context.source, "user_as_of_date")


if __name__ == "__main__":
    unittest.main()
