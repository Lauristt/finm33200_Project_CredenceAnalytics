import unittest

from financial_credibility.config import ToolkitConfig
from financial_credibility.errors import UserFacingError, error_payload
from financial_credibility.reporting import build_verification_report


class ErrorTests(unittest.TestCase):
    def test_no_entity_error_has_user_facing_message(self):
        with self.assertRaises(UserFacingError) as ctx:
            build_verification_report(
                memo="This sentence has no financial entity.",
                tickers=[],
                config=ToolkitConfig(),
            )

        self.assertEqual(ctx.exception.code, "no_financial_entity_detected")
        self.assertIn("supported financial asset", ctx.exception.hint)

    def test_webapp_returns_structured_error_payload(self):
        payload = error_payload(UserFacingError("bad_input", "Bad input.", "Fix the input."))

        self.assertEqual(payload["error"]["code"], "bad_input")
        self.assertEqual(payload["error"]["message"], "Bad input.")
        self.assertEqual(payload["error"]["hint"], "Fix the input.")


if __name__ == "__main__":
    unittest.main()
