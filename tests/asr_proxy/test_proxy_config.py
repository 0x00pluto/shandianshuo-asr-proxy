import json
import tempfile
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from asr_proxy.proxy_config import load_proxy_config


def _write_config(payload: dict) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    )
    with handle:
        json.dump(payload, handle)
    return Path(handle.name)


class ProxyConfigTests(unittest.TestCase):
    def test_load_default_shape(self):
        path = REPO_ROOT / "configs" / "proxy.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        config = load_proxy_config(path)
        self.assertEqual(config.bind_host, raw["bind_host"])
        self.assertEqual(config.port, raw["port"])
        self.assertEqual(config.port, 18888)
        self.assertEqual(config.internal_port, raw["port"] + 1)
        self.assertEqual(config.whisper.model, raw["whisper"]["model"])
        self.assertEqual(config.whisper.language, raw["whisper"]["language"])
        self.assertEqual(
            config.whisper.ready_timeout_sec,
            float(raw["whisper"]["ready_timeout_sec"]),
        )
        self.assertTrue(str(config.whisper.bin).endswith("whisper-server"))
        self.assertEqual(config.local.engine, raw["local"]["engine"])
        self.assertEqual(config.local.engine, "auto")

    def test_missing_field_fails(self):
        path = _write_config({"bind_host": "127.0.0.1", "port": 8080})
        with self.assertRaises(SystemExit) as ctx:
            load_proxy_config(path)
        self.assertIn("whisper", str(ctx.exception))

    def test_invalid_port_fails(self):
        path = _write_config(
            {
                "bind_host": "127.0.0.1",
                "port": 65535,
                "whisper": {
                    "root": "/tmp",
                    "bin": "bin",
                    "models_dir": "models",
                    "model": "medium",
                    "language": "zh",
                    "ready_timeout_sec": 1,
                    "inference_timeout_sec": 1,
                },
            }
        )
        with self.assertRaises(SystemExit) as ctx:
            load_proxy_config(path)
        self.assertIn("port", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
