"""对齐闪电说本机 config.json 中的 Chat 音频自定义服务商（尽力而为）。"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

PROTOCOL = "chat_audio_data_url"
DEFAULT_MODEL = "medium"
DEFAULT_API_KEY = "local"
DEFAULT_NAME = "ASR Proxy 本地转写"
# 稳定 ID：启动时只找/改这一条，避免每次新建 custom_providers 项。
OUR_PROVIDER_ID = "custom_asr_provider_asr_proxy_local"


@dataclass(frozen=True)
class AlignResult:
    ok: bool
    path: str
    action: str
    detail: str = ""


def candidate_config_paths() -> list[Path]:
    paths: list[Path] = []
    home = Path.home()
    paths.append(home / "Library" / "Application Support" / "Shandianshuo" / "config.json")
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        base = Path(appdata)
        paths.append(base / "Shandianshuo" / "config.json")
        paths.append(base / "cn.shandianshuo.desktop" / "config.json")
    return paths


def find_config_path() -> Path | None:
    for path in candidate_config_paths():
        if path.is_file():
            return path
    return None


def align_custom_provider(
    endpoint: str,
    *,
    config_path: Path | None = None,
    model: str = DEFAULT_MODEL,
    read_text: Callable[[Path], str] | None = None,
    write_bytes: Callable[[Path, bytes], None] | None = None,
) -> AlignResult:
    """对齐或新建 chat_audio_data_url 项；保留已有 api_key。"""
    path = config_path or find_config_path()
    if path is None:
        return AlignResult(False, "", "missing", "找不到闪电说 config.json")

    reader = read_text or (lambda p: p.read_text(encoding="utf-8"))
    try:
        data = json.loads(reader(path))
    except (OSError, json.JSONDecodeError) as exc:
        return AlignResult(False, str(path), "read_error", str(exc))
    if not isinstance(data, dict):
        return AlignResult(False, str(path), "invalid", "根节点不是对象")

    asr = data.get("asr")
    if asr is None:
        asr = {}
        data["asr"] = asr
    if not isinstance(asr, dict):
        return AlignResult(False, str(path), "invalid", "asr 不是对象")

    providers = asr.get("custom_providers")
    if providers is None:
        providers = []
        asr["custom_providers"] = providers
    if not isinstance(providers, list):
        return AlignResult(False, str(path), "invalid", "custom_providers 不是数组")

    ours = [
        item
        for item in providers
        if isinstance(item, dict) and item.get("id") == OUR_PROVIDER_ID
    ]
    if len(ours) > 1:
        return AlignResult(
            False,
            str(path),
            "ambiguous",
            "存在多条本代理条目，拒绝改写",
        )

    created = False
    stable_ours = False
    if len(ours) == 1:
        target = ours[0]
        stable_ours = True
    else:
        # 没有稳定 ID 时：仅当「恰好一条」Chat 音频且 endpoint 已是本代理时，只对齐字段并保留原 id。
        # 零条时可新建稳定 ID 那一条。多条或对不上 → 不改、不新建。
        chat_audio = [
            item
            for item in providers
            if isinstance(item, dict) and item.get("protocol") == PROTOCOL
        ]
        claimed = [
            item
            for item in chat_audio
            if str(item.get("endpoint", "")).rstrip("/") == endpoint.rstrip("/")
        ]
        if len(claimed) == 1:
            target = claimed[0]
        elif len(chat_audio) == 0:
            created = True
            stable_ours = True
            target = {
                "id": OUR_PROVIDER_ID,
                "name": DEFAULT_NAME,
                "enabled": True,
                "protocol": PROTOCOL,
                "endpoint": endpoint,
                "api_key": DEFAULT_API_KEY,
                "model": model,
                "models": [model],
            }
            providers.append(target)
        else:
            return AlignResult(
                False,
                str(path),
                "skipped_ambiguous",
                "已有其它 Chat 音频且对不上本代理",
            )

    if stable_ours and created:
        target["id"] = OUR_PROVIDER_ID
        target["name"] = DEFAULT_NAME
    elif stable_ours:
        target["id"] = OUR_PROVIDER_ID
        if not target.get("name"):
            target["name"] = DEFAULT_NAME
    # 认领已有条目时不改 id，避免打断 asr.provider。

    target["enabled"] = True
    target["protocol"] = PROTOCOL
    target["endpoint"] = endpoint
    if not isinstance(target.get("api_key"), str) or not str(target["api_key"]).strip():
        target["api_key"] = DEFAULT_API_KEY
    if not isinstance(target.get("model"), str) or not str(target["model"]).strip():
        target["model"] = model
    models = target.get("models")
    if not isinstance(models, list) or not models:
        target["models"] = [target.get("model") or model]

    # 不强制改 asr.provider；只对齐唯一可识别条目的 endpoint。
    payload = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        _atomic_write(path, payload, write_bytes=write_bytes)
    except OSError as exc:
        return AlignResult(False, str(path), "write_error", str(exc))

    return AlignResult(
        True,
        str(path),
        "created" if created else "updated",
        f"id={target.get('id')}",
    )


def _atomic_write(
    path: Path,
    payload: bytes,
    *,
    write_bytes: Callable[[Path, bytes], None] | None,
) -> None:
    if write_bytes is not None:
        write_bytes(path, payload)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
