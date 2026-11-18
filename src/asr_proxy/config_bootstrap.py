"""从 config-templates/ 拷贝生成运行时 configs/（缺失才拷，不覆盖）。"""

from __future__ import annotations

import shutil
from pathlib import Path

RUNTIME_FILES = ("proxy.json", "premium.json")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def templates_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "config-templates"


def runtime_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "configs"


def ensure_runtime_configs(
    *,
    root: Path | None = None,
    names: tuple[str, ...] = RUNTIME_FILES,
) -> Path:
    """确保运行时目录存在且缺文件时从模板拷入；返回运行时目录。"""
    base = root or repo_root()
    src_dir = templates_dir(base)
    dst_dir = runtime_dir(base)
    if not src_dir.is_dir():
        raise SystemExit(f"找不到配置模板目录：{src_dir}")
    dst_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        src = src_dir / name
        dst = dst_dir / name
        if dst.exists():
            continue
        if not src.is_file():
            raise SystemExit(f"找不到配置模板：{src}")
        shutil.copy2(src, dst)
    return dst_dir
