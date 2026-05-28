import unittest

from financial_credibility.config import ToolkitConfig
from financial_credibility.multi_tool_agent import MultiToolAgentRunner
from financial_credibility.reporting import build_verification_report


PREFETCHED_SEC = [
    {
        "title": "SEC Company Facts for AAPL",
        "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        "snippet": "Revenues (USD) 2025 Q4: 102500000000 filed 2025-10-31 form 10-K",
        "published_at": "2025-10-31",
        "source": "SEC EDGAR",
        "raw": {"provider": "sec_company_facts", "cik": 320193},
    }
]


class MultiToolAgentTests(unittest.TestCase):
    def test_no_key_fallback_records_multi_tool_trace_and_audit(self):
        payload = MultiToolAgentRunner(ToolkitConfig()).run(
            memo="Apple revenue grew 6% year over year.",
            tickers=["AAPL"],
            as_of_date="2025-11-01",
            prefetched_results=PREFETCHED_SEC,
            audit=True,
        )

        calls = payload["agent_trace"]["tool_calls"]
        tool_names = {call["tool_name"] for call in calls}

        self.assertEqual(payload["agent_trace"]["termination_reason"], "no_provider_fallback")
        self.assertGreaterEqual(len(tool_names), 3)
        self.assertIn("select_sources", tool_names)
        self.assertIn("retrieve_evidence", tool_names)
        self.assertIn("audit_report", payload)
        self.assertIn("Multi-Tool Agent Trace", payload["report_markdown"])
        self.assertIn("Audit Report", payload["report_markdown"])

    def test_no_key_fallback_stops_at_max_steps(self):
        payload = MultiToolAgentRunner(ToolkitConfig()).run(
            memo="Apple revenue grew 6% year over year.",
            tickers=["AAPL"],
            as_of_date="2025-11-01",
            max_steps=2,
            prefetched_results=PREFETCHED_SEC,
            audit=False,
        )

        self.assertEqual(payload["agent_trace"]["termination_reason"], "max_steps")
        self.assertEqual(len(payload["agent_trace"]["tool_calls"]), 2)

    def test_no_key_fallback_respects_one_shot_profile(self):
        payload = MultiToolAgentRunner(ToolkitConfig()).run(
            memo="Apple revenue grew 6% year over year.",
            tickers=["AAPL"],
            as_of_date="2025-11-01",
            tool_profile="one_shot",
            prefetched_results=PREFETCHED_SEC,
            audit=False,
        )

        self.assertEqual(
            [call["tool_name"] for call in payload["agent_trace"]["tool_calls"]],
            ["build_evidence_pack"],
        )

    def test_no_key_fallback_skips_retrieval_for_opinion_or_forecast(self):
        payload = MultiToolAgentRunner(ToolkitConfig()).run(
            memo="The lingering question is whether Intel can convince investors its AI buildout has durability into 2027.",
            tickers=["INTC"],
            as_of_date="2026-05-27",
            prefetched_results=PREFETCHED_SEC,
            audit=False,
        )

        tool_names = [call["tool_name"] for call in payload["agent_trace"]["tool_calls"]]
        self.assertIn("decompose_claims", tool_names)
        self.assertNotIn("select_sources", tool_names)
        self.assertNotIn("retrieve_evidence", tool_names)
        self.assertNotIn("verify_atomic_claim", tool_names)

    def test_agent_prompt_mentions_vague_non_falsifiable_commentary(self):
        payload = MultiToolAgentRunner(ToolkitConfig()).run(
            memo='"Nvidia delivered another beat, but that is essentially priced in," said an analyst.',
            tickers=["NVDA"],
            as_of_date="2026-05-27",
            prefetched_results=PREFETCHED_SEC,
            audit=False,
        )

        self.assertIn("priced in", " ".join(payload["agent_trace"]["notes"]))
        self.assertNotIn("retrieve_evidence", [call["tool_name"] for call in payload["agent_trace"]["tool_calls"]])

    def test_agent_skips_investor_reassurance_framing(self):
        payload = MultiToolAgentRunner(ToolkitConfig()).run(
            memo=(
                "May 20 (Reuters) - Nvidia CEO Jensen Huang on Wednesday aimed to assure investors "
                "that the world's most valuable company can keep up its blockbuster growth with the help of a broad base of customers."
            ),
            tickers=["NVDA"],
            as_of_date="2026-05-27",
            prefetched_results=PREFETCHED_SEC,
            audit=False,
        )

        tool_names = [call["tool_name"] for call in payload["agent_trace"]["tool_calls"]]
        self.assertIn("decompose_claims", tool_names)
        self.assertNotIn("retrieve_evidence", tool_names)
        self.assertNotIn("verify_atomic_claim", tool_names)

    def test_report_mode_multi_tool_routes_to_runner(self):
        payload = build_verification_report(
            memo="Apple revenue grew 6% year over year.",
            tickers=["AAPL"],
            config=ToolkitConfig(),
            as_of_date="2025-11-01",
            mode="multi_tool",
            prefetched_results=PREFETCHED_SEC,
            audit=True,
        )

        self.assertEqual(payload["input"]["mode"], "multi_tool")
        self.assertIn("agent_trace", payload)
        self.assertEqual(payload["agent_trace"]["tool_profile"], "agent_core")


if __name__ == "__main__":
    unittest.main()
