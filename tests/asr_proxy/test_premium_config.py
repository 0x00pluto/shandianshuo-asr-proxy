import json
import tempfile
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from asr_proxy.premium_config import (
    PremiumProvider,
    load_premium_list,
    select_active_premium,
)


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


class PremiumConfigTests(unittest.TestCase):
    def test_load_default_shape(self):
        path = REPO_ROOT / "configs" / "premium.json"
        providers = load_premium_list(path)
        self.assertEqual(len(providers), 1)
        self.assertEqual(providers[0].id, "doubao")
        self.assertEqual(providers[0].api_key_env, "DOUBAO_ASR_API_KEY")
        self.assertEqual(providers[0].timeout_sec, 12.0)

    def test_missing_file_fails(self):
        missing = REPO_ROOT / "configs" / "premium.missing-for-test.json"
        with self.assertRaises(SystemExit) as ctx:
            load_premium_list(missing)
        self.assertIn(str(missing), str(ctx.exception))

    def test_missing_field_fails(self):
        path = _write_config(
            {
                "premium": [
                    {
                        "id": "doubao",
                        "endpoint": "wss://example",
                        "resource_id": "rid",
                        "api_key_env": "DOUBAO_ASR_API_KEY",
                    }
                ]
            }
        )
        with self.assertRaises(SystemExit):
            load_premium_list(path)

    def test_select_first_implemented_with_key(self):
        providers = [
            PremiumProvider(
                id="unknown",
                endpoint="wss://a",
                resource_id="r",
                api_key_env="A_KEY",
                timeout_sec=1,
            ),
            PremiumProvider(
                id="doubao",
                endpoint="wss://b",
                resource_id="r2",
                api_key_env="DOUBAO_ASR_API_KEY",
                timeout_sec=12,
            ),
            PremiumProvider(
                id="doubao",
                endpoint="wss://c",
                resource_id="r3",
                api_key_env="OTHER_KEY",
                timeout_sec=8,
            ),
        ]
        active = select_active_premium(
            providers,
            {"DOUBAO_ASR_API_KEY": "secret", "OTHER_KEY": "later"},
        )
        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.provider.endpoint, "wss://b")
        self.assertEqual(active.api_key, "secret")

    def test_missing_key_returns_none(self):
        providers = [
            PremiumProvider(
                id="doubao",
                endpoint="wss://b",
                resource_id="r2",
                api_key_env="DOUBAO_ASR_API_KEY",
                timeout_sec=12,
            )
        ]
        self.assertIsNone(select_active_premium(providers, {}))


if __name__ == "__main__":
    unittest.main()
