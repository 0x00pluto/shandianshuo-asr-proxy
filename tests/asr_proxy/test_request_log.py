import struct
import tempfile
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from asr_proxy.proxy_config import LoggingConfig
from asr_proxy.request_log import (
    estimate_wav_seconds,
    format_asr_summary,
    format_local_done,
    format_premium_diag,
    setup_request_logging,
)
from asr_proxy.select import DualOutcome, DualResult


def _minimal_wav(*, seconds: float = 1.0, rate: int = 16000) -> bytes:
    frames = int(rate * seconds)
    data = b"\x00\x00" * frames
    byte_rate = rate * 2
    fmt = struct.pack(
        "<HHIIHH",
        1,
        1,
        rate,
        byte_rate,
        2,
        16,
    )
    return (
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVEfmt "
        + struct.pack("<I", 16)
        + fmt
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )


class RequestLogTests(unittest.TestCase):
    def test_estimate_wav_seconds(self):
        wav = _minimal_wav(seconds=2.0)
        sec = estimate_wav_seconds(wav)
        self.assertIsNotNone(sec)
        self.assertAlmostEqual(sec, 2.0, places=1)

    def test_format_premium_chosen(self):
        result = DualResult(
            outcome=DualOutcome.PREMIUM_CHOSEN,
            text="你好",
            provider="doubao",
            premium_ms=120.5,
            local_ms=None,
        )
        line = format_asr_summary(
            req_id="abcd1234",
            result=result,
            wav_bytes=1000,
            wav_sec=1.5,
        )
        self.assertIn("chosen=doubao", line)
        self.assertIn("local_engine=-", line)
        self.assertIn("premium_ms=120.5", line)
        self.assertIn("premium_chars=2", line)
        self.assertIn("local_ms=-", line)
        self.assertIn("reply_chars=2", line)
        self.assertNotIn("你好", line)

    def test_format_local_done(self):
        line = format_local_done(
            req_id="abcd1234",
            local_result={"ok": True, "text": "本地", "ms": 800.0},
            local_engine="sensevoice",
        )
        self.assertIn("local_engine=sensevoice", line)
        self.assertIn("event=local_done", line)
        self.assertIn("local_ms=800", line)
        self.assertIn("local_chars=2", line)

    def test_format_premium_diag_failure(self):
        line = format_premium_diag(
            req_id="abcd1234",
            diag={
                "stage": "tls",
                "peer": "1.2.3.4",
                "dns_ms": 3.2,
                "connect_ms": None,
                "recognize_ms": None,
                "request_id": "req-uuid",
                "connect_id": "conn-uuid",
                "err": "TLS 握手失败：timeout\n detail",
            },
        )
        self.assertIn("event=premium_diag", line)
        self.assertIn("stage=tls", line)
        self.assertIn("peer=1.2.3.4", line)
        self.assertIn("dns_ms=3.2", line)
        self.assertIn("connect_ms=-", line)
        self.assertIn("request_id=req-uuid", line)
        self.assertIn("err=TLS 握手失败：timeout detail", line)
        self.assertNotIn("\n", line.split("err=", 1)[1])

    def test_format_premium_diag_success(self):
        line = format_premium_diag(
            req_id="abcd1234",
            diag={
                "stage": "done",
                "peer": "5.6.7.8",
                "dns_ms": 1.0,
                "connect_ms": 40.0,
                "recognize_ms": 200.0,
                "request_id": "r",
                "connect_id": "c",
                "err": None,
            },
        )
        self.assertIn("stage=done", line)
        self.assertIn("connect_ms=40", line)
        self.assertIn("recognize_ms=200", line)
        self.assertIn("err=-", line)

    def test_setup_rotating_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = LoggingConfig(
                dir=Path(tmp) / "logs",
                file="asr-proxy.log",
                max_bytes=1024,
                backup_count=2,
            )
            path = setup_request_logging(cfg, REPO_ROOT)
            self.assertTrue(path.is_file() or path.parent.is_dir())
            self.assertEqual(path.name, "asr-proxy.log")


if __name__ == "__main__":
    unittest.main()
