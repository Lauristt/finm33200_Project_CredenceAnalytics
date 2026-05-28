import unittest

from financial_credibility.explanations import (
    build_claim_explanation,
    explain_review_reason,
    explain_review_reasons,
)


class ExplanationTests(unittest.TestCase):
    def test_human_review_reason_has_user_facing_explanation(self):
        explanation = explain_review_reason("low_retrieval_sufficiency")

        self.assertEqual(explanation["code"], "low_retrieval_sufficiency")
        self.assertIn("Limited evidence", explanation["title"])
        self.assertIn("recommended_action", explanation)

    def test_unknown_human_review_reason_falls_back_gracefully(self):
        explanation = explain_review_reason("new_reason")

        self.assertEqual(explanation["code"], "new_reason")
        self.assertIn("Human review", explanation["title"])

    def test_review_reason_list_is_deduped(self):
        explanations = explain_review_reasons(["low_retrieval_sufficiency", "low_retrieval_sufficiency"])

        self.assertEqual(len(explanations), 1)

    def test_claim_explanation_includes_verdict_and_main_evidence(self):
        result = {
            "atomic_claim": {"claim_id": "claim_1", "text": "Apple revenue grew."},
            "verdict": "supported",
            "evidence_urls": ["https://data.sec.gov/example"],
            "confidence_components": {"final_confidence": 0.82},
        }
        evidence = {
            "https://data.sec.gov/example": {
                "title": "SEC Company Facts for AAPL",
                "url": "https://data.sec.gov/example",
                "source_tier": "T1",
                "is_official_primary": True,
            }
        }

        explanation = build_claim_explanation(result, evidence)

        self.assertEqual(explanation["claim_id"], "claim_1")
        self.assertEqual(explanation["verdict"], "supported")
        self.assertIn("SEC Company Facts", explanation["summary"])
        self.assertIn("official primary", explanation["source_summary"])

    def test_claim_explanation_handles_no_evidence(self):
        result = {
            "atomic_claim": {"claim_id": "claim_1", "text": "Apple revenue grew."},
            "verdict": "insufficient",
            "evidence_urls": [],
        }

        explanation = build_claim_explanation(result, {})

        self.assertIn("No direct evidence", explanation["source_summary"])
        self.assertIn("No claim-linked evidence was available.", explanation["caveats"])

    def test_claim_explanation_filters_internal_provider_errors(self):
        result = {
            "atomic_claim": {"claim_id": "claim_1", "text": "Apple revenue grew."},
            "verdict": "partially_supported",
            "evidence_urls": ["https://data.sec.gov/example"],
            "issues": [
                "ticker_only_entity_resolution",
                "openai fallback: HTTP Error 400: Bad Request",
                "llm_judge_unavailable",
            ],
        }
        evidence = {
            "https://data.sec.gov/example": {
                "title": "SEC Company Facts for AAPL",
                "url": "https://data.sec.gov/example",
            }
        }

        explanation = build_claim_explanation(result, evidence)

        self.assertIn("Entity resolution is based mainly on the ticker symbol.", explanation["caveats"])
        self.assertFalse(any("HTTP Error" in item for item in explanation["caveats"]))
        self.assertFalse(any("fallback" in item for item in explanation["caveats"]))
        self.assertFalse(any("llm_judge_unavailable" in item for item in explanation["caveats"]))


if __name__ == "__main__":
    unittest.main()
