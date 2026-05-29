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

    def test_forecast_related_claims_are_strictly_non_fact_checkable(self):
        examples = [
            "Nvidia forecast quarterly revenue above estimates.",
            "Management guidance implies revenue could accelerate into 2027.",
            "Analysts expect Intel margins will recover next year.",
            "The consensus target assumes stronger AI demand through 2028.",
        ]
        for text in examples:
            with self.subTest(text=text):
                result = classify_argument_type(text)
                self.assertEqual(result.argument_type, ArgumentType.FORECAST)

    def test_opinion_classification(self):
        result = classify_argument_type("Tesla is overvalued relative to its moat.")
        self.assertEqual(result.argument_type, ArgumentType.OPINION_ANALYSIS)

    def test_opinion_related_claims_are_strictly_non_fact_checkable(self):
        examples = [
            "Intel has a weak AI moat versus competing silicon.",
            "The narrative is shifting toward inference workloads.",
            "Nvidia looks attractive after the pullback.",
            "The AI buildout durability remains the key investor question.",
            '"Nvidia delivered another beat, but at this point that is essentially priced in as it keeps beating quarter after quarter," said eMarketer analyst Jacob Bourne.',
            (
                "May 20 (Reuters) - Nvidia CEO Jensen Huang on Wednesday aimed to assure investors "
                "that the world's most valuable company can keep up its blockbuster growth with the help of a broad base of customers."
            ),
            "Management sought to reassure investors it can sustain growth.",
            "Huang discussed with investors how Nvidia can maintain growth.",
            "Dollar Tree, Snowflake, and Hormel Foods were among the companies highlighted after earnings.",
        ]
        for text in examples:
            with self.subTest(text=text):
                result = classify_argument_type(text)
                self.assertEqual(result.argument_type, ArgumentType.OPINION_ANALYSIS)

    def test_discussion_question_is_not_fact_checkable(self):
        result = classify_argument_type(
            "The lingering question is whether it can convince investors the AI buildout has durability into 2027 and 2028."
        )

        self.assertEqual(result.argument_type, ArgumentType.OPINION_ANALYSIS)
        self.assertIn("discussion framing", result.signals)


if __name__ == "__main__":
    unittest.main()
