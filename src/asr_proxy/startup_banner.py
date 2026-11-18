"""启动状态摘要：Rich Panel；运行状态 + 闪电说自定义服务商。"""

from __future__ import annotations

import io
from dataclasses import dataclass

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .local_engine import INSTALL_HINT
from .shandianshuo_config import DEFAULT_API_KEY, DEFAULT_MODEL, AlignResult


@dataclass(frozen=True)
class StartupStatus:
    endpoint: str
    premium_label: str
    local_engine: str
    local_detail: str = ""
    align: AlignResult | None = None
    hint_uv_sync: bool = False


def _kv_table() -> Table:
    table = Table(show_header=False, box=None, padding=(0, 1), expand=False)
    table.add_column(style="bold dim", no_wrap=True)
    table.add_column(overflow="fold")
    return table


def _runtime_table(status: StartupStatus) -> Table:
    table = _kv_table()
    table.add_row("对外", Text(status.endpoint, style="bold cyan"))

    premium_style = "green" if status.premium_label != "未启用" else "yellow"
    table.add_row("高级模型", Text(status.premium_label, style=premium_style))

    detail = status.local_detail.split(";", 1)[0].strip() if status.local_detail else ""
    local_text = status.local_engine if not detail else f"{status.local_engine} · {detail}"
    local_style = "yellow" if status.local_engine == "off" else "green"
    table.add_row("本地", Text(local_text, style=local_style))
    return table


def _provider_table(status: StartupStatus) -> Table:
    table = _kv_table()
    table.add_row("接入", "Chat 音频")
    table.add_row("Base URL", Text(status.endpoint, style="cyan"))
    table.add_row("API Key", DEFAULT_API_KEY)
    table.add_row("模型", DEFAULT_MODEL)

    align = status.align
    if align is None:
        table.add_row("配置", Text("—", style="dim"))
    elif align.ok:
        if align.action == "created":
            summary = "已写入自定义服务商配置"
        else:
            summary = "已更新自定义服务商配置"
        table.add_row("配置", Text(summary, style="green"))
        if align.path:
            table.add_row("", Text(align.path, style="dim"))
        table.add_row("", Text("闪电说里刷新设置即可", style="dim"))
    else:
        reason = align.detail or align.action or "未写入"
        table.add_row("配置", Text(f"未写入：{reason}", style="red"))
        if align.path:
            table.add_row("", Text(align.path, style="dim"))
    return table


def build_startup_panel(status: StartupStatus) -> Panel:
    body: list = [
        _runtime_table(status),
        Text(""),
        Text("闪电说自定义服务商（Chat 音频）", style="bold"),
        _provider_table(status),
    ]
    if status.hint_uv_sync:
        body.append(Text(f"依赖：{INSTALL_HINT}", style="yellow"))

    return Panel.fit(
        Group(*body),
        title="ASR Proxy",
        border_style="bright_blue",
        padding=(0, 1),
    )


def render_startup_banner(status: StartupStatus, *, console: Console | None = None) -> str:
    """渲染摘要文本（不往真实终端刷屏）。"""
    if console is None:
        console = Console(
            record=True,
            force_terminal=True,
            width=88,
            file=io.StringIO(),
        )
    console.print(build_startup_panel(status))
    return console.export_text()


def print_startup_banner(status: StartupStatus) -> None:
    Console().print(build_startup_panel(status))
