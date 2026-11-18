"""转写请求结构化日志：控制台 + 可轮转文件。"""

from __future__ import annotations

import logging
import struct
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .proxy_config import LoggingConfig
from .select import DualOutcome, DualResult

LOGGER_NAME = "asr_proxy.request"


def setup_request_logging(config: LoggingConfig, repo_root: Path) -> Path:
    """配置轮转文件日志，返回日志文件绝对路径。"""
    log_dir = config.dir
    if not log_dir.is_absolute():
        log_dir = (repo_root / log_dir).resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / config.file

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    handler = RotatingFileHandler(
        log_path,
        maxBytes=config.max_bytes,
        backupCount=config.backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)
    return log_path


def new_request_id() -> str:
    return uuid.uuid4().hex[:8]


def estimate_wav_seconds(wav: bytes) -> float | None:
    """从标准 PCM WAV 头估算时长；失败返回 None。"""
    if len(wav) < 44:
        return None
    if not (wav.startswith(b"RIFF") and wav[8:12] == b"WAVE"):
        return None
    # 找 fmt 与 data chunk
    offset = 12
    channels = None
    sample_rate = None
    bits = None
    data_size = None
    while offset + 8 <= len(wav):
        chunk_id = wav[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", wav, offset + 4)[0]
        data_start = offset + 8
        if chunk_id == b"fmt " and chunk_size >= 16 and data_start + 16 <= len(wav):
            channels = struct.unpack_from("<H", wav, data_start + 2)[0]
            sample_rate = struct.unpack_from("<I", wav, data_start + 4)[0]
            bits = struct.unpack_from("<H", wav, data_start + 14)[0]
        elif chunk_id == b"data":
            data_size = chunk_size
            break
        offset = data_start + chunk_size + (chunk_size & 1)
    if not channels or not sample_rate or not bits or data_size is None:
        return None
    bytes_per_sec = sample_rate * channels * (bits // 8)
    if bytes_per_sec <= 0:
        return None
    return round(data_size / bytes_per_sec, 2)


def format_asr_summary(
    *,
    req_id: str,
    result: DualResult,
    wav_bytes: int,
    wav_sec: float | None,
    local_engine: str | None = None,
) -> str:
    chosen = _chosen_label(result)
    premium_chars = _premium_chars(result)
    local_chars = len(result.local_text) if result.local_text is not None else None
    if result.outcome is DualOutcome.LOCAL_CHOSEN and local_chars is None:
        local_chars = len(result.text)
    reply_chars = len(result.text) if result.outcome is not DualOutcome.FAILED else 0
    wav_sec_text = f"{wav_sec:g}" if wav_sec is not None else "-"
    engine = local_engine or "-"
    return (
        f"[ASR] req={req_id} chosen={chosen} "
        f"local_engine={engine} "
        f"wav_bytes={wav_bytes} wav_sec≈{wav_sec_text} "
        f"premium_ms={_fmt_ms(result.premium_ms)} "
        f"premium_chars={_fmt_num(premium_chars)} "
        f"premium_err={_premium_err(result)} "
        f"local_ms={_fmt_ms(result.local_ms)} "
        f"local_chars={_fmt_num(local_chars)} "
        f"local_err={result.local_error or '-'} "
        f"reply_chars={reply_chars}"
    )


def format_local_done(
    *,
    req_id: str,
    local_result: dict,
    local_engine: str | None = None,
) -> str:
    if local_result.get("ok"):
        text = local_result.get("text", "")
        chars = len(text) if isinstance(text, str) else 0
        err = "-"
    else:
        chars = "-"
        err = local_result.get("error") or "unknown"
    engine = local_engine or "-"
    return (
        f"[ASR] req={req_id} event=local_done "
        f"local_engine={engine} "
        f"local_ms={_fmt_ms(local_result.get('ms'))} "
        f"local_chars={chars} local_err={err}"
    )


def format_premium_diag(*, req_id: str, diag: dict) -> str:
    """格式化高级模型诊断行；不含密钥与音频。"""
    err = _one_line(diag.get("err"), limit=200)
    return (
        f"[ASR] req={req_id} event=premium_diag "
        f"stage={diag.get('stage') or 'unknown'} "
        f"peer={diag.get('peer') or '-'} "
        f"dns_ms={_fmt_ms(_as_float(diag.get('dns_ms')))} "
        f"connect_ms={_fmt_ms(_as_float(diag.get('connect_ms')))} "
        f"recognize_ms={_fmt_ms(_as_float(diag.get('recognize_ms')))} "
        f"request_id={diag.get('request_id') or '-'} "
        f"connect_id={diag.get('connect_id') or '-'} "
        f"err={err}"
    )


def emit(message: str) -> None:
    print(message, flush=True)
    logging.getLogger(LOGGER_NAME).info(message)


def _one_line(value: object, *, limit: int) -> str:
    if value is None:
        return "-"
    text = " ".join(str(value).split())
    if not text:
        return "-"
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _chosen_label(result: DualResult) -> str:
    if result.outcome is DualOutcome.PREMIUM_CHOSEN:
        return result.provider or "premium"
    if result.outcome is DualOutcome.LOCAL_CHOSEN:
        return "local"
    return "failed"


def _premium_chars(result: DualResult) -> int | None:
    if result.outcome is DualOutcome.PREMIUM_CHOSEN:
        return len(result.text)
    return None


def _premium_err(result: DualResult) -> str:
    if result.outcome is DualOutcome.PREMIUM_CHOSEN:
        return "-"
    if result.failure_kind and result.failure_kind != "local":
        return result.failure_kind
    return "-"


def _fmt_ms(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:g}"


def _fmt_num(value: int | None) -> str:
    if value is None:
        return "-"
    return str(value)
