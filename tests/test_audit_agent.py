import unittest

from financial_credibility.audit_agent import audit_verification_chain, review_tool_surface


class AuditAgentTests(unittest.TestCase):
    def test_evidence_verifier_catches_missing_references(self):
        report = {
            "runs": [
                {
                    "ticker": "AAPL",
                    "evidence": [{"url": "https://example.com/source"}],
                    "canonical_facts": [{"fact_id": "fact_present"}],
                    "atomic_claims": [
                        {
                            "atomic_claim": {"claim_id": "claim_1", "text": "Apple revenue grew."},
                            "verdict": "supported",
                            "evidence_urls": ["https://example.com/missing"],
                            "canonical_fact_ids": ["fact_missing"],
                            "confidence_components": {"final_confidence": 0.9},
                        }
                    ],
                }
            ]
        }

        audit = audit_verification_chain(report_payload=report)
        summaries = [finding.summary for finding in audit.findings]

        self.assertTrue(any("evidence URLs" in summary for summary in summaries))
        self.assertTrue(any("canonical facts" in summary for summary in summaries))

    def test_computation_verifier_catches_wrong_growth(self):
        report = {
            "runs": [
                {
                    "ticker": "AAPL",
                    "evidence": [],
                    "canonical_facts": [],
                    "atomic_claims": [
                        {
                            "atomic_claim": {"claim_id": "claim_1", "text": "Revenue grew 10%."},
                            "verdict": "verified",
                            "numeric_derivation": {
                                "expression": "(current - prior) / abs(prior)",
                                "inputs": {"current": 110, "prior": 100},
                                "result": 0.3,
                                "tolerance": 0.001,
                            },
                            "confidence_components": {"final_confidence": 0.8},
                        }
                    ],
                }
            ]
        }

        audit = audit_verification_chain(report_payload=report)

        self.assertIn("computation", {finding.category for finding in audit.findings})
        self.assertEqual(audit.verdict, "fail")

    def test_tool_use_verifier_catches_wrong_order(self):
        report = {"runs": [{"ticker": "AAPL", "evidence": [], "canonical_facts": [], "atomic_claims": []}]}
        agent_trace = {
            "run_id": "trace_1",
            "instructions_hash": "abc",
            "tool_profile": "agent_core",
            "tool_calls": [
                {"call_id": "1", "tool_name": "verify_atomic_claim", "arguments": {}, "status": "ok"},
                {"call_id": "2", "tool_name": "retrieve_evidence", "arguments": {}, "status": "ok"},
            ],
        }

        audit = audit_verification_chain(report_payload=report, agent_trace=agent_trace)

        self.assertTrue(any(finding.category == "tool_use" for finding in audit.findings))

    def test_constraint_and_reasoning_verifiers_flag_risky_positive_claim(self):
        report = {
            "report_markdown": "This system verifies claims and does not provide investment advice.",
            "runs": [
                {
                    "ticker": "AAPL",
                    "evidence": [{"url": "https://example.com/blog", "is_official_primary": False}],
                    "metadata": {"source_selection": [{"claim_id": "claim_1", "selected_sources": ["market_blog"]}]},
                    "canonical_facts": [],
                    "atomic_claims": [
                        {
                            "atomic_claim": {"claim_id": "claim_1", "text": "Apple revenue grew due to demand."},
                            "verdict": "supported",
                            "evidence_urls": ["https://example.com/blog"],
                            "confidence_components": {"final_confidence": 0.4},
                            "human_review_required": False,
                        }
                    ],
                }
            ],
        }

        audit = audit_verification_chain(report_payload=report)
        categories = {finding.category for finding in audit.findings}

        self.assertIn("constraint", categories)
        self.assertIn("reasoning", categories)

    def test_common_sense_flags_unrelated_eps_source_for_supply_claim(self):
        report = {
            "runs": [
                {
                    "ticker": "NVDA",
                    "evidence": [
                        {
                            "url": "https://data.sec.gov/example",
                            "title": "SEC Company Facts for NVDA",
                            "text": "Basic EPS: 2.4 USD/shares for fiscal quarter ended Apr 26, 2026",
                            "domain": "data.sec.gov",
                            "source_tier": "T1",
                            "published_at": "2026-05-20",
                            "is_official_primary": True,
                        }
                    ],
                    "canonical_facts": [],
                    "atomic_claims": [
                        {
                            "atomic_claim": {
                                "claim_id": "claim_16",
                                "text": "Nvidia supply rose to $119 billion in the fiscal first quarter.",
                            },
                            "verdict": "partially_supported",
                            "evidence_urls": ["https://data.sec.gov/example"],
                            "confidence_components": {"final_confidence": 0.76},
                            "human_review_required": True,
                        }
                    ],
                }
            ]
        }

        audit = audit_verification_chain(report_payload=report)

        self.assertTrue(any(finding.category == "source_alignment" for finding in audit.findings))
        self.assertTrue(any("topically unrelated" in finding.summary for finding in audit.findings))

    def test_common_sense_reports_no_displayable_source_gap(self):
        report = {
            "runs": [
                {
                    "ticker": "NVDA",
                    "evidence": [],
                    "canonical_facts": [],
                    "metadata": {
                        "source_selection": [
                            {
                                "claim_id": "claim_3",
                                "selected_sources": [],
                                "policy_notes": ["no_matching_source_candidates"],
                            }
                        ]
                    },
                    "atomic_claims": [
                        {
                            "atomic_claim": {
                                "claim_id": "claim_3",
                                "text": "Nvidia supply rose to $119 billion in the fiscal first quarter.",
                            },
                            "verdict": "insufficient",
                            "evidence_urls": [],
                            "canonical_fact_ids": [],
                            "issues": ["no_evidence"],
                            "confidence_components": {"final_confidence": 0.15},
                            "human_review_required": True,
                        }
                    ],
                }
            ]
        }

        audit = audit_verification_chain(report_payload=report)

        self.assertTrue(any(finding.category == "coverage" for finding in audit.findings))
        self.assertTrue(any("No displayable source" in finding.summary for finding in audit.findings))
        self.assertTrue(all(finding.severity == "minor" for finding in audit.findings if finding.category == "coverage"))

    def test_common_sense_allows_price_history_for_equity_price_claim(self):
        report = {
            "runs": [
                {
                    "ticker": "QCOM",
                    "evidence": [
                        {
                            "url": "https://stooq.com/q/d/l/?s=qcom.us",
                            "title": "QCOM historical prices",
                            "text": "QCOM historical daily close prices: latest_daily_return_pct -6.0%; previous_daily_return_pct 8.0%",
                            "domain": "stooq.com",
                            "source_tier": "T3",
                            "published_at": "2026-05-20",
                        }
                    ],
                    "canonical_facts": [],
                    "atomic_claims": [
                        {
                            "atomic_claim": {
                                "claim_id": "claim_2",
                                "text": "Qualcomm fell 6% after sharp gains on Tuesday.",
                            },
                            "verdict": "supported",
                            "evidence_urls": ["https://stooq.com/q/d/l/?s=qcom.us"],
                            "confidence_components": {"final_confidence": 0.86},
                        }
                    ],
                }
            ]
        }

        audit = audit_verification_chain(report_payload=report)

        self.assertFalse(any(finding.category == "source_alignment" for finding in audit.findings))

    def test_common_sense_prefers_exact_url_over_colliding_evidence_key(self):
        report = {
            "runs": [
                {
                    "ticker": "MSFT",
                    "evidence": [
                        {
                            "url": "https://www.microsoft.com/en-us/investor/earnings/FY-2026-Q3/press-release-webcast",
                            "title": "Microsoft Cloud and AI Strength Fuels Third Quarter Results",
                            "text": "Operating income was $38.4 billion, up 20%.",
                            "domain": "microsoft.com",
                            "source_tier": "T2",
                            "published_at": None,
                            "is_official_primary": True,
                        },
                        {
                            "url": "https://www.microsoft.com/en-us/investor/default",
                            "title": "Home page - Microsoft",
                            "text": "Know the next earnings release date.",
                            "domain": "microsoft.com",
                            "source_tier": "T2",
                            "published_at": None,
                            "is_official_primary": True,
                        },
                    ],
                    "canonical_facts": [],
                    "atomic_claims": [
                        {
                            "atomic_claim": {"claim_id": "claim_2", "text": "Operating income was $38.4 billion, up 20%."},
                            "verdict": "supported",
                            "evidence_urls": [
                                "https://www.microsoft.com/en-us/investor/earnings/FY-2026-Q3/press-release-webcast"
                            ],
                            "evidence_keys": ["T2:microsoft.com:undated"],
                            "numeric_derivation": {
                                "expression": "numeric_match_summary",
                                "inputs": {"matched_values": "$38.4 billion -> $38.4 billion; 20% -> 20%"},
                                "result": True,
                                "passed": True,
                            },
                            "confidence_components": {"final_confidence": 0.86},
                        }
                    ],
                }
            ]
        }

        audit = audit_verification_chain(report_payload=report)

        self.assertFalse(any(finding.category == "source_alignment" for finding in audit.findings))

    def test_common_sense_ignores_generic_document_locator_facts(self):
        report = {
            "runs": [
                {
                    "ticker": "GOOGL",
                    "evidence": [
                        {
                            "url": "https://s206.q4cdn.com/example.pdf",
                            "title": "Alphabet Q1 2026 earnings release",
                            "text": "Total operating income was $39.696 billion.",
                            "domain": "s206.q4cdn.com",
                            "source_tier": "T2",
                            "published_at": "2026-04-29",
                        }
                    ],
                    "canonical_facts": [
                        {
                            "fact_id": "fact_doc",
                            "fact_name": "Alphabet Q1 2026 earnings release",
                            "value": "2026",
                            "unit": None,
                            "currency": None,
                        }
                    ],
                    "atomic_claims": [
                        {
                            "atomic_claim": {"claim_id": "claim_3", "text": "Total operating income was $39.696 billion."},
                            "verdict": "supported",
                            "evidence_urls": ["https://s206.q4cdn.com/example.pdf"],
                            "canonical_fact_ids": ["fact_doc"],
                            "numeric_derivation": {
                                "expression": "numeric_match_summary",
                                "inputs": {"matched_values": "$39.696 billion -> $39.696 billion"},
                                "result": True,
                                "passed": True,
                            },
                            "confidence_components": {"final_confidence": 0.82},
                        }
                    ],
                }
            ]
        }

        audit = audit_verification_chain(report_payload=report)

        self.assertFalse(any(finding.category == "source_alignment" for finding in audit.findings))

    def test_review_tool_surface_reports_profile(self):
        result = review_tool_surface("agent_core")

        self.assertEqual(result["profile"], "agent_core")
        self.assertGreater(result["tool_count"], 1)


if __name__ == "__main__":
    unittest.main()
