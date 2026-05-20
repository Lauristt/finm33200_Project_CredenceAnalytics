import unittest

from financial_credibility.argument import classify_argument_type
from financial_credibility.models import ArgumentType


class ArgumentClassifierTests(unittest.TestCase):
    def test_metric_fact_classification(self):
        result = classify_argument_type("Apple revenue grew 6% year over year in Q4.")
        self.assertEqual(result.argument_type, ArgumentType.METRIC_FACT)

    def test_forecast_classification(self):
        result = classify_argument_type("Nvidia revenue will grow 30% next year.")
        self.assertEqual(result.argument_type, ArgumentType.FORECAST)

    def test_opinion_classification(self):
        result = classify_argument_type("Tesla is overvalued relative to its moat.")
        self.assertEqual(result.argument_type, ArgumentType.OPINION_ANALYSIS)


if __name__ == "__main__":
    unittest.main()
