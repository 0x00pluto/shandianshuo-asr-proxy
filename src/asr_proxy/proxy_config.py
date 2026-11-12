"""读取 configs/proxy.json：对外端口、主机与 whisper 路径/超时。

whisper 内部端口固定为 port+1，不单独配置。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

REQUIRED_TOP = ("bind_host", "port", "whisper")
REQUIRED_WHISPER = (
    "root",
    "bin",
    "models_dir",
    "model",
    "language",
    "ready_timeout_sec",
    "inference_timeout_sec",
)


@dataclass(frozen=True)
class WhisperConfig:
    root: Path
    bin: Path
    models_dir: Path
    model: str
    language: str
    ready_timeout_sec: float
    inference_timeout_sec: float


@dataclass(frozen=True)
class ProxyConfig:
    bind_host: str
    port: int
    whisper: WhisperConfig

    @property
    def internal_port(self) -> int:
        return self.port + 1


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "configs" / "proxy.json"


def load_proxy_config(
    config_path: Path | None = None,
    *,
    read_text: Callable[[Path], str] | None = None,
) -> ProxyConfig:
    path = config_path or default_config_path()
    reader = read_text or (lambda p: p.read_text(encoding="utf-8"))
    try:
        raw = reader(path)
    except FileNotFoundError as exc:
        raise SystemExit(f"找不到代理配置：{path}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"代理配置不是合法 JSON：{path}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"代理配置根节点必须是对象：{path}")

    missing = [name for name in REQUIRED_TOP if name not in data]
    if missing:
        raise SystemExit(f"代理配置缺少字段 {', '.join(missing)}：{path}")

    bind_host = data["bind_host"]
    port = data["port"]
    whisper_raw = data["whisper"]
    if not isinstance(bind_host, str) or not bind_host.strip():
        raise SystemExit(f"bind_host 必须是非空字符串：{path}")
    if not isinstance(port, int) or isinstance(port, bool) or not (1 <= port <= 65534):
        raise SystemExit(f"port 必须是 1..65534 的整数：{path}")
    if not isinstance(whisper_raw, dict):
        raise SystemExit(f"whisper 必须是对象：{path}")

    whisper_missing = [name for name in REQUIRED_WHISPER if name not in whisper_raw]
    if whisper_missing:
        raise SystemExit(
            f"whisper 缺少字段 {', '.join(whisper_missing)}：{path}"
        )

    root = _as_path(whisper_raw["root"], "whisper.root", path)
    bin_rel = _as_nonempty_str(whisper_raw["bin"], "whisper.bin", path)
    models_rel = _as_nonempty_str(whisper_raw["models_dir"], "whisper.models_dir", path)
    model = _as_nonempty_str(whisper_raw["model"], "whisper.model", path)
    language = _as_nonempty_str(whisper_raw["language"], "whisper.language", path)
    ready = _as_positive_number(
        whisper_raw["ready_timeout_sec"], "whisper.ready_timeout_sec", path
    )
    inference = _as_positive_number(
        whisper_raw["inference_timeout_sec"], "whisper.inference_timeout_sec", path
    )

    bin_path = _resolve_under_root(root, bin_rel)
    models_dir = _resolve_under_root(root, models_rel)

    return ProxyConfig(
        bind_host=bind_host.strip(),
        port=port,
        whisper=WhisperConfig(
            root=root,
            bin=bin_path,
            models_dir=models_dir,
            model=model,
            language=language,
            ready_timeout_sec=ready,
            inference_timeout_sec=inference,
        ),
    )


def _as_nonempty_str(value: Any, label: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"{label} 必须是非空字符串：{path}")
    return value.strip()


def _as_path(value: Any, label: str, path: Path) -> Path:
    text = _as_nonempty_str(value, label, path)
    return Path(text).expanduser()


def _as_positive_number(value: Any, label: str, path: Path) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise SystemExit(f"{label} 必须是正数：{path}")
    return float(value)


def _resolve_under_root(root: Path, relative_or_abs: str) -> Path:
    candidate = Path(relative_or_abs).expanduser()
    if candidate.is_absolute():
        return candidate
    return (root / candidate).resolve()
