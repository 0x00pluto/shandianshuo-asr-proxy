"""读取 configs/premium.json，并按环境变量挑出当前高级模型。

出厂默认在 config-templates/；首次缺失时拷入 configs/。
密钥只来自环境变量名（配置里的 api_key_env），不读配置文件里的明文密钥。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .config_bootstrap import ensure_runtime_configs, runtime_dir

REQUIRED_FIELDS = ("id", "endpoint", "resource_id", "api_key_env", "timeout_sec")
IMPLEMENTED_IDS = frozenset({"doubao"})


@dataclass(frozen=True)
class PremiumProvider:
    id: str
    endpoint: str
    resource_id: str
    api_key_env: str
    timeout_sec: float


@dataclass(frozen=True)
class ActivePremium:
    provider: PremiumProvider
    api_key: str


def default_config_path() -> Path:
    return runtime_dir() / "premium.json"


def load_premium_list(
    config_path: Path | None = None,
    *,
    read_text: Callable[[Path], str] | None = None,
) -> list[PremiumProvider]:
    if config_path is None:
        ensure_runtime_configs()
        path = default_config_path()
    else:
        path = config_path
    reader = read_text or (lambda p: p.read_text(encoding="utf-8"))
    try:
        raw = reader(path)
    except FileNotFoundError as exc:
        raise SystemExit(f"找不到高级模型配置：{path}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"高级模型配置不是合法 JSON：{path}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"高级模型配置根节点必须是对象：{path}")
    items = data.get("premium")
    if not isinstance(items, list):
        raise SystemExit(f"高级模型配置缺少 premium 数组：{path}")
    providers: list[PremiumProvider] = []
    for index, item in enumerate(items):
        providers.append(_parse_provider(item, path, index))
    return providers


def select_active_premium(
    providers: list[PremiumProvider],
    environ: Mapping[str, str] | None = None,
) -> ActivePremium | None:
    env = environ if environ is not None else os.environ
    for provider in providers:
        if provider.id not in IMPLEMENTED_IDS:
            continue
        api_key = env.get(provider.api_key_env, "")
        if isinstance(api_key, str) and api_key.strip():
            return ActivePremium(provider=provider, api_key=api_key.strip())
    return None


def load_premium_runtime(
    config_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[list[PremiumProvider], ActivePremium | None]:
    providers = load_premium_list(config_path)
    return providers, select_active_premium(providers, environ)


def _parse_provider(item: Any, path: Path, index: int) -> PremiumProvider:
    if not isinstance(item, dict):
        raise SystemExit(f"premium[{index}] 必须是对象：{path}")
    missing = [name for name in REQUIRED_FIELDS if name not in item]
    if missing:
        raise SystemExit(
            f"premium[{index}] 缺少字段 {', '.join(missing)}：{path}"
        )
    provider_id = item["id"]
    endpoint = item["endpoint"]
    resource_id = item["resource_id"]
    api_key_env = item["api_key_env"]
    timeout_sec = item["timeout_sec"]
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise SystemExit(f"premium[{index}].id 必须是非空字符串：{path}")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise SystemExit(f"premium[{index}].endpoint 必须是非空字符串：{path}")
    if not isinstance(resource_id, str) or not resource_id.strip():
        raise SystemExit(f"premium[{index}].resource_id 必须是非空字符串：{path}")
    if not isinstance(api_key_env, str) or not api_key_env.strip():
        raise SystemExit(f"premium[{index}].api_key_env 必须是非空字符串：{path}")
    if not isinstance(timeout_sec, (int, float)) or timeout_sec <= 0:
        raise SystemExit(f"premium[{index}].timeout_sec 必须是正数：{path}")
    return PremiumProvider(
        id=provider_id.strip(),
        endpoint=endpoint.strip(),
        resource_id=resource_id.strip(),
        api_key_env=api_key_env.strip(),
        timeout_sec=float(timeout_sec),
    )
