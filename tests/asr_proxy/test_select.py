import threading
import time
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from asr_proxy.select import DualOutcome, PremiumFailure, run_dual


class SelectTests(unittest.TestCase):
    def test_premium_success_returns_premium_text(self):
        started = {"local": False, "premium": False}
        both_started = threading.Barrier(2)

        def local(_wav, _lang):
            started["local"] = True
            both_started.wait(timeout=2)
            time.sleep(0.05)
            return "local-text"

        def premium(_wav, _lang):
            started["premium"] = True
            both_started.wait(timeout=2)
            return "premium-text"

        result = run_dual(
            b"RIFF",
            "zh",
            local_transcribe=local,
            premium_transcribe=premium,
            premium_provider="doubao",
        )
        self.assertTrue(started["local"])
        self.assertTrue(started["premium"])
        self.assertEqual(result.outcome, DualOutcome.PREMIUM_CHOSEN)
        self.assertEqual(result.text, "premium-text")

    def test_empty_premium_text_is_kept(self):
        def local(_wav, _lang):
            return "should-not-use"

        def premium(_wav, _lang):
            return ""

        result = run_dual(
            b"RIFF",
            "zh",
            local_transcribe=local,
            premium_transcribe=premium,
            premium_provider="doubao",
        )
        self.assertEqual(result.outcome, DualOutcome.PREMIUM_CHOSEN)
        self.assertEqual(result.text, "")

    def test_local_finishes_first_still_waits_for_premium(self):
        order = []

        def local(_wav, _lang):
            order.append("local-start")
            time.sleep(0.02)
            order.append("local-done")
            return "local-text"

        def premium(_wav, _lang):
            order.append("premium-start")
            time.sleep(0.08)
            order.append("premium-done")
            return "premium-text"

        result = run_dual(
            b"RIFF",
            "zh",
            local_transcribe=local,
            premium_transcribe=premium,
            premium_provider="doubao",
        )
        self.assertEqual(result.outcome, DualOutcome.PREMIUM_CHOSEN)
        self.assertEqual(result.text, "premium-text")
        self.assertIn("local-done", order)
        self.assertLess(order.index("local-done"), order.index("premium-done"))

    def test_premium_timeout_falls_back_to_local(self):
        def local(_wav, _lang):
            time.sleep(0.02)
            return "local-text"

        def premium(_wav, _lang):
            raise PremiumFailure("timeout", "timed out")

        result = run_dual(
            b"RIFF",
            "zh",
            local_transcribe=local,
            premium_transcribe=premium,
            premium_provider="doubao",
        )
        self.assertEqual(result.outcome, DualOutcome.LOCAL_CHOSEN)
        self.assertEqual(result.text, "local-text")
        self.assertEqual(result.failure_kind, "timeout")

    def test_premium_auth_falls_back_to_local(self):
        def local(_wav, _lang):
            return "local-text"

        def premium(_wav, _lang):
            raise PremiumFailure("auth", "401")

        result = run_dual(
            b"RIFF",
            "zh",
            local_transcribe=local,
            premium_transcribe=premium,
            premium_provider="doubao",
        )
        self.assertEqual(result.outcome, DualOutcome.LOCAL_CHOSEN)
        self.assertEqual(result.failure_kind, "auth")

    def test_both_fail(self):
        def local(_wav, _lang):
            raise RuntimeError("local down")

        def premium(_wav, _lang):
            raise PremiumFailure("network", "offline")

        result = run_dual(
            b"RIFF",
            "zh",
            local_transcribe=local,
            premium_transcribe=premium,
            premium_provider="doubao",
        )
        self.assertEqual(result.outcome, DualOutcome.FAILED)
        self.assertEqual(result.failure_kind, "network")

    def test_skipped_premium_uses_local(self):
        def local(_wav, _lang):
            return "local-only"

        result = run_dual(
            b"RIFF",
            "zh",
            local_transcribe=local,
            premium_transcribe=None,
        )
        self.assertEqual(result.outcome, DualOutcome.LOCAL_CHOSEN)
        self.assertEqual(result.text, "local-only")
        self.assertIsNone(result.provider)


if __name__ == "__main__":
    unittest.main()
