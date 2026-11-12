"""本地 Whisper 与高级云端模型的双写路由。"""

from .premium_config import ActivePremium, load_premium_runtime
from .proxy_config import ProxyConfig, load_proxy_config
from .select import DualOutcome, DualResult, run_dual

__all__ = [
    "ActivePremium",
    "DualOutcome",
    "DualResult",
    "ProxyConfig",
    "load_premium_runtime",
    "load_proxy_config",
    "run_dual",
]
