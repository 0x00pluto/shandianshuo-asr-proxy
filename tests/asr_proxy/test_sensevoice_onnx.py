import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from asr_proxy.sensevoice_onnx import apply_lfr, decode_tokens


class SenseVoiceOnnxUnitTests(unittest.TestCase):
    def test_decode_strips_special_tokens(self):
        tokens = ["<unk>", "你", "好", "<|zh|>", "▁world"]
        text = decode_tokens([1, 2, 3, 4], tokens)
        self.assertEqual(text, "你好 world")

    def test_apply_lfr_shape(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed")
        frames = np.arange(12 * 80, dtype=np.float32).reshape(12, 80)
        out = apply_lfr(frames, lfr_m=7, lfr_n=6)
        self.assertEqual(out.shape[1], 7 * 80)
        self.assertGreaterEqual(out.shape[0], 1)


if __name__ == "__main__":
    unittest.main()
