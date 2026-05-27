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

    def test_cli_demo_preset_marks_single_claim_output(self):
        argv = [
            "financial_credibility",
            "Apple revenue grew 6% year over year.",
            "--ticker",
            "AAPL",
            "--mode",
            "strict",
            "--demo-preset",
            "equity_supported",
            "--pretty",
        ]

        with patch("sys.argv", argv), contextlib.redirect_stdout(io.StringIO()) as output:
            main()

        payload = json.loads(output.getvalue())
        self.assertTrue(payload["demo_mode"])
        self.assertEqual(payload["demo_preset"], "equity_supported")
        self.assertEqual(payload["evidence_mode"], "prefetched")

    def test_cli_auto_report_extracts_entities_without_ticker(self):
        argv = [
            "financial_credibility",
            "Apple revenue grew 6% year over year while CPI rose.",
            "--auto-report",
            "--demo-preset",
            "equity_supported",
            "--pretty",
        ]

        with patch("sys.argv", argv), contextlib.redirect_stdout(io.StringIO()) as output:
            main()

        payload = json.loads(output.getvalue())
        self.assertTrue(payload["demo_mode"])
        self.assertIn("summary", payload)
        self.assertIn("coverage_summary", payload)


if __name__ == "__main__":
    unittest.main()
