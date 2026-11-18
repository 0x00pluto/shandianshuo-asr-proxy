import json
import tempfile
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from asr_proxy.local_engine import (
    ENGINE_OFF,
    ENGINE_SENSEVOICE,
    ENGINE_WHISPER,
    resolve_local_engine,
    write_resolved_back,
)
from asr_proxy.proxy_config import (
    LocalConfig,
    LoggingConfig,
    ProxyConfig,
    WhisperConfig,
)


def _cfg(
    *,
    engine: str = "auto",
    model_dir: str = "",
    whisper_bin: Path | None = None,
    whisper_model: Path | None = None,
) -> ProxyConfig:
    root = Path(tempfile.mkdtemp())
    bin_path = whisper_bin or (root / "missing-bin")
    models_dir = root / "models"
    models_dir.mkdir(exist_ok=True)
    model_name = "medium"
    if whisper_model is not None:
        whisper_model.parent.mkdir(parents=True, exist_ok=True)
        whisper_model.write_bytes(b"x")
        models_dir = whisper_model.parent
        model_name = whisper_model.name.replace("ggml-", "").replace(".bin", "")
    return ProxyConfig(
        bind_host="127.0.0.1",
        port=18888,
        whisper=WhisperConfig(
            root=root,
            bin=bin_path,
            models_dir=models_dir,
            model=model_name,
            language="zh",
            ready_timeout_sec=1,
            inference_timeout_sec=1,
        ),
        logging=LoggingConfig(Path("temp/logs"), "asr-proxy.log", 1000, 1),
        local=LocalConfig(engine, model_dir, "off", "", ""),
        config_path=root / "proxy.json",
    )


class LocalEngineTests(unittest.TestCase):
    def test_auto_prefers_sensevoice_bundle(self):
        bundle = Path(tempfile.mkdtemp()) / "sensevoice-small"
        bundle.mkdir()
        for name in ("model.onnx", "tokens.json", "config.yaml"):
            (bundle / name).write_text("x", encoding="utf-8")
        cfg = _cfg(engine="auto", model_dir=str(bundle))
        resolved = resolve_local_engine(
            cfg, find_spec=lambda name: object()
        )
        self.assertEqual(resolved.engine, ENGINE_SENSEVOICE)
        self.assertEqual(resolved.model_dir, str(bundle.resolve()))

    def test_auto_falls_to_whisper(self):
        root = Path(tempfile.mkdtemp())
        bin_path = root / "whisper-server"
        bin_path.write_text("x", encoding="utf-8")
        model = root / "models" / "ggml-medium.bin"
        cfg = _cfg(engine="auto", whisper_bin=bin_path, whisper_model=model)
        resolved = resolve_local_engine(cfg, find_spec=lambda _n: None)
        self.assertEqual(resolved.engine, ENGINE_WHISPER)

    def test_explicit_sensevoice_missing_does_not_switch(self):
        cfg = _cfg(engine="sensevoice", model_dir="/no/such/dir")
        resolved = resolve_local_engine(cfg, find_spec=lambda _n: object())
        self.assertEqual(resolved.engine, ENGINE_OFF)
        self.assertIn("sensevoice_bundle_missing", resolved.skip_reason)

    def test_write_back_keeps_engine_auto(self):
        path = Path(tempfile.mkdtemp()) / "proxy.json"
        payload = {
            "bind_host": "127.0.0.1",
            "port": 18888,
            "local": {
                "engine": "auto",
                "sensevoice": {"model_dir": ""},
                "last_resolved": {"engine": "off", "model_dir": "", "skip_reason": ""},
            },
            "whisper": {
                "root": "/tmp",
                "bin": "b",
                "models_dir": "m",
                "model": "medium",
                "language": "zh",
                "ready_timeout_sec": 1,
                "inference_timeout_sec": 1,
            },
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        local = LocalConfig("auto", "", "off", "", "")
        from asr_proxy.local_engine import ResolvedLocal

        write_resolved_back(
            path,
            local,
            ResolvedLocal(ENGINE_SENSEVOICE, "/tmp/sv", ""),
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["local"]["engine"], "auto")
        self.assertEqual(data["local"]["sensevoice"]["model_dir"], "/tmp/sv")
        self.assertEqual(data["local"]["last_resolved"]["engine"], ENGINE_SENSEVOICE)


if __name__ == "__main__":
    unittest.main()
