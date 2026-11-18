"""本地兜底引擎探测：SenseVoice / Whisper 二选一；编辑态与生效态分开。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .proxy_config import LocalConfig, ProxyConfig, WhisperConfig

ENGINE_AUTO = "auto"
ENGINE_SENSEVOICE = "sensevoice"
ENGINE_WHISPER = "whisper"
ENGINE_OFF = "off"

SENSEVOICE_FILES = ("model.onnx", "tokens.json", "config.yaml")
INSTALL_HINT = "uv sync"


@dataclass(frozen=True)
class ResolvedLocal:
    engine: str
    model_dir: str
    skip_reason: str


def sensevoice_candidate_dirs(override: str = "") -> list[Path]:
    """候选三件套目录；覆盖路径优先。"""
    dirs: list[Path] = []
    if override and override.strip():
        dirs.append(Path(override.strip()).expanduser())

    home = Path.home()
    dirs.append(
        home
        / "Library"
        / "Application Support"
        / "Shandianshuo"
        / "workspace"
        / "models"
        / "sensevoice-small"
    )

    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        base = Path(appdata)
        dirs.append(
            base / "Shandianshuo" / "workspace" / "models" / "sensevoice-small"
        )
        dirs.append(
            base
            / "cn.shandianshuo.desktop"
            / "workspace"
            / "models"
            / "sensevoice-small"
        )
    return dirs


def is_sensevoice_bundle(model_dir: Path) -> bool:
    if not model_dir.is_dir():
        return False
    return all((model_dir / name).is_file() for name in SENSEVOICE_FILES)


def find_sensevoice_dir(
    override: str = "",
    *,
    allow_defaults: bool = True,
) -> Path | None:
    """查找三件套。override 非空时先查覆盖路径；allow_defaults=False 时不扫系统默认。"""
    if override and override.strip():
        candidate = Path(override.strip()).expanduser()
        if is_sensevoice_bundle(candidate):
            return candidate.resolve()
        if not allow_defaults:
            return None
    if not allow_defaults:
        return None
    for candidate in sensevoice_candidate_dirs(""):
        if is_sensevoice_bundle(candidate):
            return candidate.resolve()
    return None


def whisper_files_ready(whisper: WhisperConfig) -> tuple[bool, str]:
    if not whisper.bin.is_file():
        return False, f"whisper_bin_missing:{whisper.bin}"
    model_path = _whisper_model_path(whisper)
    if model_path is None or not model_path.is_file():
        return False, f"whisper_model_missing:{whisper.model}"
    return True, ""


def _whisper_model_path(whisper: WhisperConfig) -> Path | None:
    model_arg = whisper.model
    candidate = Path(model_arg).expanduser()
    if candidate.is_file():
        return candidate.resolve()
    short_name = model_arg
    if short_name.startswith("ggml-") and short_name.endswith(".bin"):
        short_name = short_name[len("ggml-") : -len(".bin")]
    elif short_name.endswith(".bin"):
        short_name = short_name[: -len(".bin")]
    path = whisper.models_dir / f"ggml-{short_name}.bin"
    return path if path.is_file() else None


def sensevoice_deps_available(
    *,
    find_spec: Callable[[str], Any] | None = None,
) -> bool:
    checker = find_spec
    if checker is None:
        import importlib.util

        checker = importlib.util.find_spec
    for name in ("onnxruntime", "numpy", "kaldi_native_fbank"):
        if checker(name) is None:
            return False
    return True


def resolve_local_engine(
    config: ProxyConfig,
    *,
    find_spec: Callable[[str], Any] | None = None,
) -> ResolvedLocal:
    intent = config.local.engine
    override = config.local.sensevoice_model_dir

    if intent == ENGINE_OFF:
        return ResolvedLocal(ENGINE_OFF, "", "engine_off")

    if intent == ENGINE_SENSEVOICE:
        return _resolve_sensevoice_only(override, find_spec=find_spec)

    if intent == ENGINE_WHISPER:
        return _resolve_whisper_only(config.whisper)

    # auto
    sense = find_sensevoice_dir(override)
    if sense is not None:
        if not sensevoice_deps_available(find_spec=find_spec):
            ready, reason = whisper_files_ready(config.whisper)
            if ready:
                return ResolvedLocal(
                    ENGINE_WHISPER,
                    "",
                    f"sensevoice_deps_missing_fallback_whisper;{INSTALL_HINT}",
                )
            return ResolvedLocal(
                ENGINE_OFF,
                str(sense),
                f"sensevoice_deps_missing;{INSTALL_HINT}",
            )
        return ResolvedLocal(ENGINE_SENSEVOICE, str(sense), "")

    ready, reason = whisper_files_ready(config.whisper)
    if ready:
        return ResolvedLocal(ENGINE_WHISPER, "", "")
    return ResolvedLocal(ENGINE_OFF, "", reason or "auto_no_local")


def _resolve_sensevoice_only(
    override: str,
    *,
    find_spec: Callable[[str], Any] | None,
) -> ResolvedLocal:
    # 显式 sensevoice：若用户写了 model_dir，只认这一处，避免「目录错了却捡到本机另一份」。
    allow_defaults = not bool(override and override.strip())
    sense = find_sensevoice_dir(override, allow_defaults=allow_defaults)
    if sense is None:
        return ResolvedLocal(ENGINE_OFF, "", "sensevoice_bundle_missing")
    if not sensevoice_deps_available(find_spec=find_spec):
        return ResolvedLocal(
            ENGINE_OFF,
            str(sense),
            f"sensevoice_deps_missing;{INSTALL_HINT}",
        )
    return ResolvedLocal(ENGINE_SENSEVOICE, str(sense), "")


def _resolve_whisper_only(whisper: WhisperConfig) -> ResolvedLocal:
    ready, reason = whisper_files_ready(whisper)
    if ready:
        return ResolvedLocal(ENGINE_WHISPER, "", "")
    return ResolvedLocal(ENGINE_OFF, "", reason or "whisper_unavailable")


def write_resolved_back(
    config_path: Path,
    local: LocalConfig,
    resolved: ResolvedLocal,
    *,
    read_text: Callable[[Path], str] | None = None,
    write_text: Callable[[Path, str], None] | None = None,
) -> None:
    """写回 last_resolved；空 model_dir 时填探测路径；不改用户 engine 意图。"""
    reader = read_text or (lambda p: p.read_text(encoding="utf-8"))
    writer = write_text or (
        lambda p, text: p.write_text(text, encoding="utf-8")
    )
    try:
        data = json.loads(reader(config_path))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return

    local_raw = data.get("local")
    if not isinstance(local_raw, dict):
        local_raw = {}
        data["local"] = local_raw

    local_raw["engine"] = local.engine
    sense_raw = local_raw.get("sensevoice")
    if not isinstance(sense_raw, dict):
        sense_raw = {}
        local_raw["sensevoice"] = sense_raw

    existing_dir = sense_raw.get("model_dir")
    if (
        (not isinstance(existing_dir, str) or not existing_dir.strip())
        and resolved.model_dir
    ):
        sense_raw["model_dir"] = resolved.model_dir
    elif "model_dir" not in sense_raw:
        sense_raw["model_dir"] = local.sensevoice_model_dir

    local_raw["last_resolved"] = {
        "engine": resolved.engine,
        "model_dir": resolved.model_dir,
        "skip_reason": resolved.skip_reason,
    }
    writer(config_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
