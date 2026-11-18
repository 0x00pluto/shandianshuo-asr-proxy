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
        self.assertIsNotNone(result.premium_ms)
        self.assertGreaterEqual(result.premium_ms, 0)

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
            raise PremiumFailure(
                "timeout",
                "timed out",
                stage="recv",
                diag={"stage": "recv", "peer": "1.2.3.4", "err": "timed out"},
            )

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
        self.assertIsNotNone(result.premium_ms)
        self.assertIsNotNone(result.local_ms)
        self.assertIsNotNone(result.premium_diag)
        self.assertEqual(result.premium_diag.get("stage"), "recv")
        self.assertEqual(result.premium_diag.get("peer"), "1.2.3.4")

    def test_premium_tuple_diag_on_success(self):
        def local(_wav, _lang):
            return "local-text"

        def premium(_wav, _lang):
            return "premium-text", {
                "stage": "done",
                "peer": "9.9.9.9",
                "connect_ms": 12.5,
                "recognize_ms": 80.0,
            }

        result = run_dual(
            b"RIFF",
            "zh",
            local_transcribe=local,
            premium_transcribe=premium,
            premium_provider="doubao",
        )
        self.assertEqual(result.outcome, DualOutcome.PREMIUM_CHOSEN)
        self.assertEqual(result.text, "premium-text")
        self.assertEqual(result.premium_diag.get("stage"), "done")
        self.assertEqual(result.premium_diag.get("peer"), "9.9.9.9")

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
        self.assertIsNone(result.premium_ms)
        self.assertIsNotNone(result.local_ms)


if __name__ == "__main__":
    unittest.main()
