"""启动横幅：运行状态 + 闪电说自定义服务商。"""

from __future__ import annotations

import unittest

from asr_proxy.shandianshuo_config import AlignResult
from asr_proxy.startup_banner import StartupStatus, render_startup_banner


class StartupBannerTests(unittest.TestCase):
    def test_success_shows_provider_and_updated(self) -> None:
        text = render_startup_banner(
            StartupStatus(
                endpoint="http://127.0.0.1:18888/v1",
                premium_label="doubao · 12s",
                local_engine="sensevoice",
                align=AlignResult(
                    True,
                    "/Users/me/Library/Application Support/Shandianshuo/config.json",
                    "updated",
                ),
            )
        )
        self.assertIn("ASR Proxy", text)
        self.assertIn("http://127.0.0.1:18888/v1", text)
        self.assertIn("doubao", text)
        self.assertIn("sensevoice", text)
        self.assertIn("闪电说自定义服务商", text)
        self.assertIn("Chat 音频", text)
        self.assertIn("local", text)
        self.assertIn("medium", text)
        self.assertIn("已更新自定义服务商配置", text)
        self.assertIn("Shandianshuo/config.json", text)
        self.assertIn("刷新设置即可", text)
        self.assertNotIn("已对齐", text)
        self.assertNotIn("稳定 ID", text)
        self.assertNotIn("chat_audio_data_url", text)
        self.assertNotIn("不会每次", text)

    def test_created_wording(self) -> None:
        text = render_startup_banner(
            StartupStatus(
                endpoint="http://127.0.0.1:18888/v1",
                premium_label="未启用",
                local_engine="whisper",
                align=AlignResult(True, "/tmp/config.json", "created"),
            )
        )
        self.assertIn("已写入自定义服务商配置", text)
        self.assertIn("/tmp/config.json", text)
        self.assertNotIn("已对齐", text)

    def test_align_failure_still_shows_provider(self) -> None:
        text = render_startup_banner(
            StartupStatus(
                endpoint="http://127.0.0.1:18888/v1",
                premium_label="未启用",
                local_engine="off",
                local_detail="sensevoice_deps_missing;uv sync",
                align=AlignResult(
                    False,
                    "",
                    "skipped_ambiguous",
                    "已有其它 Chat 音频且对不上本代理",
                ),
                hint_uv_sync=True,
            )
        )
        self.assertIn("闪电说自定义服务商", text)
        self.assertIn("Chat 音频", text)
        self.assertIn("Base URL", text)
        self.assertIn("local", text)
        self.assertIn("medium", text)
        self.assertIn("未写入：已有其它 Chat 音频且对不上本代理", text)
        self.assertIn("uv sync", text)
        self.assertIn("sensevoice_deps_missing", text)
        self.assertNotIn("已对齐", text)
        self.assertNotIn("稳定 ID", text)
        self.assertNotIn("chat_audio_data_url", text)


if __name__ == "__main__":
    unittest.main()
