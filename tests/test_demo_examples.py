import csv
import json
import unittest
from pathlib import Path

from financial_credibility.config import ToolkitConfig
from financial_credibility.reporting import build_verification_report


ROOT = Path(__file__).resolve().parents[1]


class DemoExampleTests(unittest.TestCase):
    def test_demo_prefetched_json_files_are_valid(self):
        for path in (ROOT / "examples").glob("demo_*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(payload, list)

    def test_demo_batch_csv_has_required_columns(self):
        path = ROOT / "examples" / "demo_batch_input.csv"
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            self.assertIn("claim", reader.fieldnames)
            self.assertIn("ticker", reader.fieldnames)

    def test_demo_equity_supported_can_build_report(self):
        prefetched = json.loads((ROOT / "examples" / "demo_equity_supported.json").read_text(encoding="utf-8"))
        payload = build_verification_report(
            memo="Apple revenue grew 6% year over year.",
            tickers=["AAPL"],
            config=ToolkitConfig(),
            as_of_date="2025-11-01",
            prefetched_results=prefetched,
        )

        self.assertIn("Verification Coverage", payload["report_markdown"])
        self.assertIn("Evidence Provenance", payload["report_markdown"])


if __name__ == "__main__":
    unittest.main()
