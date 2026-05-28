import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from financial_credibility.cli import main


class CliTests(unittest.TestCase):
    def test_cli_writes_audit_trace_json(self):
        prefetched = [
            {
                "title": "SEC Company Facts for AAPL",
                "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                "snippet": "Revenues (USD) 2025 Q4: 102500000000 filed 2025-10-31 form 10-K",
                "published_at": "2025-10-31",
                "source": "SEC EDGAR",
                "raw": {"provider": "sec_company_facts", "cik": 320193},
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            prefetched_path = Path(tmp) / "prefetched.json"
            audit_path = Path(tmp) / "audit.json"
            prefetched_path.write_text(json.dumps(prefetched), encoding="utf-8")
            argv = [
                "financial_credibility",
                "Apple revenue grew 6% year over year.",
                "--ticker",
                "AAPL",
                "--mode",
                "strict",
                "--prefetched-json",
                str(prefetched_path),
                "--audit-out",
                str(audit_path),
            ]

            fake_result = {"summary": {"total": 1, "succeeded": 1, "failed": 0}, "results": [], "errors": []}
            with (
                patch("sys.argv", argv),
                patch("financial_credibility.cli.run_batch", return_value=fake_result),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                main()

            audit = json.loads(audit_path.read_text(encoding="utf-8"))

        self.assertIn("trace_id", audit)
        self.assertIn("events", audit)

    def test_cli_batch_output_contains_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch_path = Path(tmp) / "batch.csv"
            output_path = Path(tmp) / "batch.json"
            batch_path.write_text(
                "claim,ticker,mode\nApple revenue grew.,AAPL,strict\n",
                encoding="utf-8",
            )
            argv = [
                "financial_credibility",
                "--batch-input",
                str(batch_path),
                "--batch-output",
                str(output_path),
                "--mode",
                "strict",
            ]

            with patch("sys.argv", argv), contextlib.redirect_stdout(io.StringIO()):
                main()

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertIn("summary", payload)
        self.assertEqual(payload["summary"]["total"], 1)

    def test_cli_multi_tool_writes_agent_trace(self):
        prefetched = [
            {
                "title": "SEC Company Facts for AAPL",
                "url": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                "snippet": "Revenues (USD) 2025 Q4: 102500000000 filed 2025-10-31 form 10-K",
                "published_at": "2025-10-31",
                "source": "SEC EDGAR",
                "raw": {"provider": "sec_company_facts", "cik": 320193},
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            prefetched_path = Path(tmp) / "prefetched.json"
            trace_path = Path(tmp) / "agent_trace.json"
            prefetched_path.write_text(json.dumps(prefetched), encoding="utf-8")
            argv = [
                "financial_credibility",
                "Apple revenue grew 6% year over year.",
                "--ticker",
                "AAPL",
                "--mode",
                "multi-tool",
                "--prefetched-json",
                str(prefetched_path),
                "--agent-trace-out",
                str(trace_path),
            ]

            with patch("sys.argv", argv), contextlib.redirect_stdout(io.StringIO()) as stdout:
                main()

            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            payload = json.loads(stdout.getvalue())

        self.assertEqual(trace["tool_profile"], "agent_core")
        self.assertIn("agent_trace", payload)
        self.assertEqual(payload["input"]["mode"], "multi_tool")


if __name__ == "__main__":
    unittest.main()
