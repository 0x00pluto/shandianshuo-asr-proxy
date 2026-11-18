"""config-templates → configs 首次拷贝。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from asr_proxy.config_bootstrap import ensure_runtime_configs


class ConfigBootstrapTests(unittest.TestCase):
    def test_copies_missing_from_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            templates = root / "config-templates"
            templates.mkdir()
            (templates / "proxy.json").write_text('{"ok":1}\n', encoding="utf-8")
            (templates / "premium.json").write_text('{"premium":[]}\n', encoding="utf-8")

            runtime = ensure_runtime_configs(root=root)
            self.assertEqual(runtime, root / "configs")
            self.assertTrue((runtime / "proxy.json").is_file())
            self.assertTrue((runtime / "premium.json").is_file())
            self.assertEqual(
                json.loads((runtime / "proxy.json").read_text(encoding="utf-8")),
                {"ok": 1},
            )

    def test_does_not_overwrite_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            templates = root / "config-templates"
            runtime = root / "configs"
            templates.mkdir()
            runtime.mkdir()
            (templates / "proxy.json").write_text('{"from":"template"}\n', encoding="utf-8")
            (templates / "premium.json").write_text('{"premium":[]}\n', encoding="utf-8")
            (runtime / "proxy.json").write_text('{"from":"runtime"}\n', encoding="utf-8")

            ensure_runtime_configs(root=root)
            self.assertEqual(
                json.loads((runtime / "proxy.json").read_text(encoding="utf-8")),
                {"from": "runtime"},
            )
            self.assertTrue((runtime / "premium.json").is_file())

    def test_missing_template_dir_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as ctx:
                ensure_runtime_configs(root=Path(tmp))
            self.assertIn("config-templates", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
