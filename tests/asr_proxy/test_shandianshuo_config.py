import json
import tempfile
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from asr_proxy.shandianshuo_config import (
    OUR_PROVIDER_ID,
    PROTOCOL,
    align_custom_provider,
)


class ShandianshuoConfigTests(unittest.TestCase):
    def test_create_once_then_update_same_id(self):
        path = Path(tempfile.mkdtemp()) / "config.json"
        path.write_text(json.dumps({"asr": {"custom_providers": []}}), encoding="utf-8")
        endpoint = "http://127.0.0.1:18888/v1"
        first = align_custom_provider(endpoint, config_path=path)
        self.assertTrue(first.ok)
        self.assertEqual(first.action, "created")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["asr"]["custom_providers"]), 1)
        self.assertEqual(data["asr"]["custom_providers"][0]["id"], OUR_PROVIDER_ID)

        second = align_custom_provider(
            "http://127.0.0.1:18888/v1", config_path=path
        )
        self.assertTrue(second.ok)
        self.assertEqual(second.action, "updated")
        data2 = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(data2["asr"]["custom_providers"]), 1)
        self.assertEqual(
            data2["asr"]["custom_providers"][0]["endpoint"], endpoint
        )

    def test_preserve_existing_api_key(self):
        path = Path(tempfile.mkdtemp()) / "config.json"
        path.write_text(
            json.dumps(
                {
                    "asr": {
                        "custom_providers": [
                            {
                                "id": OUR_PROVIDER_ID,
                                "protocol": PROTOCOL,
                                "endpoint": "http://127.0.0.1:1/v1",
                                "api_key": "keep-me",
                                "model": "medium",
                                "models": ["medium"],
                                "enabled": False,
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        result = align_custom_provider(
            "http://127.0.0.1:18888/v1", config_path=path
        )
        self.assertTrue(result.ok)
        item = json.loads(path.read_text(encoding="utf-8"))["asr"][
            "custom_providers"
        ][0]
        self.assertEqual(item["api_key"], "keep-me")
        self.assertEqual(item["endpoint"], "http://127.0.0.1:18888/v1")
        self.assertTrue(item["enabled"])

    def test_skip_when_other_chat_audio_exists(self):
        path = Path(tempfile.mkdtemp()) / "config.json"
        path.write_text(
            json.dumps(
                {
                    "asr": {
                        "custom_providers": [
                            {
                                "id": "someone_else",
                                "protocol": PROTOCOL,
                                "endpoint": "http://127.0.0.1:9999/v1",
                                "api_key": "x",
                                "model": "medium",
                                "models": ["medium"],
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        result = align_custom_provider(
            "http://127.0.0.1:18888/v1", config_path=path
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.action, "skipped_ambiguous")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["asr"]["custom_providers"]), 1)
        self.assertEqual(data["asr"]["custom_providers"][0]["id"], "someone_else")

    def test_claim_matching_endpoint_keeps_original_id(self):
        path = Path(tempfile.mkdtemp()) / "config.json"
        path.write_text(
            json.dumps(
                {
                    "asr": {
                        "provider": "custom_asr_provider_1791884088904",
                        "custom_providers": [
                            {
                                "id": "custom_asr_provider_1791884088904",
                                "protocol": PROTOCOL,
                                "endpoint": "http://127.0.0.1:18888/v1",
                                "api_key": "keep",
                                "model": "medium",
                                "models": ["medium"],
                                "enabled": True,
                            }
                        ],
                    }
                }
            ),
            encoding="utf-8",
        )
        result = align_custom_provider(
            "http://127.0.0.1:18888/v1", config_path=path
        )
        self.assertTrue(result.ok)
        data = json.loads(path.read_text(encoding="utf-8"))
        item = data["asr"]["custom_providers"][0]
        self.assertEqual(item["id"], "custom_asr_provider_1791884088904")
        self.assertEqual(data["asr"]["provider"], "custom_asr_provider_1791884088904")
        self.assertEqual(item["api_key"], "keep")


if __name__ == "__main__":
    unittest.main()
