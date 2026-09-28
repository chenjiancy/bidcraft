"""Sidecar 运行配置：数据根目录解析（architecture.md 第 10.3 节）。

数据根来源优先级：
1. 环境变量 ``BIDCRAFT_DATA_ROOT``（Electron Main 注入，dev/prod 同源机制）；
2. 打包后 exe 的 ``--data-root`` 命令行参数（PyInstaller 阶段接入）；
3. 用户主目录兜底（正常 Electron 启动链路下不应走到）。
"""

import os
import sys
from pathlib import Path

FALLBACK_DATA_ROOT = Path.home() / ".bidcraft"


def _cli_data_root() -> str | None:
    """从命令行读取 ``--data-root <path>``（供打包后的 exe 使用）。"""
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--data-root" and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith("--data-root="):
            return arg.split("=", 1)[1]
    return None


def resolve_data_root() -> Path:
    raw = os.environ.get("BIDCRAFT_DATA_ROOT") or _cli_data_root()
    if raw:
        return Path(raw)
    return FALLBACK_DATA_ROOT


DATA_ROOT = resolve_data_root()
DB_PATH = DATA_ROOT / "bidcraft.db"
CONFIG_DIR = DATA_ROOT / "config"
LOG_DIR = DATA_ROOT / "logs"
