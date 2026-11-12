"""双写决策与等待：本地 Whisper 与当前高级模型并行，再落到唯一结局。

不读配置文件，不读环境变量；调用方注入已解析的转写函数。
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class DualOutcome(str, Enum):
    PREMIUM_CHOSEN = "premium_chosen"
    LOCAL_CHOSEN = "local_chosen"
    FAILED = "failed"


@dataclass(frozen=True)
class DualResult:
    outcome: DualOutcome
    text: str
    provider: str | None = None
    failure_kind: str | None = None
    error: str | None = None
    local_text: str | None = None
    local_error: str | None = None


TranscribeFn = Callable[[bytes, str], str]
PremiumFn = Callable[[bytes, str], str]


def run_dual(
    wav: bytes,
    language: str,
    *,
    local_transcribe: TranscribeFn,
    premium_transcribe: PremiumFn | None,
    premium_provider: str | None = None,
    on_local_settled: Callable[[dict], None] | None = None,
    executor: concurrent.futures.Executor | None = None,
) -> DualResult:
    """同时提交可用路径，再按互斥结局选用文本。

    premium_transcribe 为 None 时高级路为 skipped，只等本地。
    高级已返回且本地仍在跑时，本地结束后调用 on_local_settled（若提供）。
    """
    owns_executor = executor is None
    pool = executor or concurrent.futures.ThreadPoolExecutor(max_workers=2)
    try:
        local_future = pool.submit(_call_local, local_transcribe, wav, language)
        if premium_transcribe is None:
            return _wait_local_only(local_future)

        premium_future = pool.submit(
            _call_premium, premium_transcribe, wav, language
        )
        return _wait_both(
            local_future,
            premium_future,
            provider=premium_provider or "premium",
            on_local_settled=on_local_settled,
        )
    finally:
        if owns_executor:
            pool.shutdown(wait=False, cancel_futures=False)


def _wait_local_only(local_future: concurrent.futures.Future) -> DualResult:
    local = local_future.result()
    if local["ok"]:
        return DualResult(
            outcome=DualOutcome.LOCAL_CHOSEN,
            text=local["text"],
            provider=None,
            failure_kind=None,
            local_text=local["text"],
        )
    return DualResult(
        outcome=DualOutcome.FAILED,
        text="",
        failure_kind="local",
        error=local["error"],
        local_error=local["error"],
    )


def _wait_both(
    local_future: concurrent.futures.Future,
    premium_future: concurrent.futures.Future,
    *,
    provider: str,
    on_local_settled: Callable[[dict], None] | None = None,
) -> DualResult:
    pending = {local_future, premium_future}
    local = None
    premium = None

    while pending:
        done, pending = concurrent.futures.wait(
            pending,
            return_when=concurrent.futures.FIRST_COMPLETED,
        )
        for future in done:
            if future is premium_future:
                premium = future.result()
                if premium["ok"]:
                    # 高级成功立刻返回；本地结果事后由调用方日志处理。
                    local_text = None
                    local_error = None
                    if local_future.done():
                        local = local_future.result()
                        if local["ok"]:
                            local_text = local["text"]
                        else:
                            local_error = local["error"]
                    else:
                        local_future.add_done_callback(
                            lambda fut, cb=on_local_settled: _settle_local(fut, cb)
                        )
                    return DualResult(
                        outcome=DualOutcome.PREMIUM_CHOSEN,
                        text=premium["text"],
                        provider=provider,
                        local_text=local_text,
                        local_error=local_error,
                    )
            else:
                local = future.result()

        if premium is not None and not premium["ok"]:
            if local is None:
                local = local_future.result()
            if local["ok"]:
                return DualResult(
                    outcome=DualOutcome.LOCAL_CHOSEN,
                    text=local["text"],
                    provider=provider,
                    failure_kind=premium["kind"],
                    error=premium["error"],
                    local_text=local["text"],
                )
            return DualResult(
                outcome=DualOutcome.FAILED,
                text="",
                provider=provider,
                failure_kind=premium["kind"],
                error=(
                    f"高级模型失败（{premium['kind']}）：{premium['error']}；"
                    f"本地也失败：{local['error']}"
                ),
                local_error=local["error"],
            )

    raise RuntimeError("双写等待循环异常结束")


def _call_local(fn: TranscribeFn, wav: bytes, language: str) -> dict:
    try:
        text = fn(wav, language)
        if not isinstance(text, str):
            text = str(text)
        return {"ok": True, "text": text}
    except Exception as exc:  # noqa: BLE001 - 泳道边界：任何异常都算本地失败
        return {"ok": False, "error": str(exc)}


def _call_premium(fn: PremiumFn, wav: bytes, language: str) -> dict:
    try:
        text = fn(wav, language)
        if not isinstance(text, str):
            text = str(text)
        return {"ok": True, "text": text, "kind": None, "error": None}
    except PremiumFailure as exc:
        return {"ok": False, "kind": exc.kind, "error": str(exc), "text": ""}
    except Exception as exc:  # noqa: BLE001 - 未分类异常归为 protocol
        return {"ok": False, "kind": "protocol", "error": str(exc), "text": ""}


def _settle_local(
    future: concurrent.futures.Future,
    on_local_settled: Callable[[dict], None] | None,
) -> None:
    try:
        result = future.result()
    except Exception as exc:  # noqa: BLE001 - 事后日志路径
        result = {"ok": False, "error": str(exc)}
    if on_local_settled is None:
        return
    try:
        on_local_settled(result)
    except Exception:  # noqa: BLE001 - 日志回调失败不影响主请求
        return


class PremiumFailure(Exception):
    """高级模型可归类失败；kind 为 timeout|network|auth|protocol 之一。"""

    def __init__(self, kind: str, message: str):
        if kind not in {"timeout", "network", "auth", "protocol"}:
            raise ValueError(f"未知失败种类：{kind}")
        self.kind = kind
        super().__init__(message)
