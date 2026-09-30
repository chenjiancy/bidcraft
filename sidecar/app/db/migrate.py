"""启动时自动迁移：把数据根下的 bidcraft.db 升级到最新版本。

在 sidecar 启动钩子里调用，使开发（uvicorn 直跑）与打包 exe 共用同一条路径
（此前二者都依赖手工执行 ``alembic upgrade head``，全新数据根首次启动即为空库）。

``script_location`` 由本模块位置计算而非取自 ini：ini 里是相对路径
``app/db/alembic`` 且带 ``prepend_sys_path = .``，打包成 onefile exe 后 cwd
不可控，相对路径会失效。数据库 URL 由 ``alembic/env.py`` 依据
``BIDCRAFT_DATA_ROOT`` 自行设置，这里不需要重复。
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)

_ALEMBIC_DIR = Path(__file__).resolve().parent / "alembic"
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def run_migrations() -> None:
    """升级到最新版本；失败向上抛出，由调用方终止启动。

    刻意不吞异常：空库/半迁移库继续提供服务会退化成散落的 HTTP 500，
    与项目"不静默"的要求相悖。
    """
    cfg = Config(str(_ALEMBIC_INI)) if _ALEMBIC_INI.exists() else Config()
    cfg.set_main_option("script_location", _ALEMBIC_DIR.as_posix())
    command.upgrade(cfg, "heads")
    logger.info("数据库迁移完成（已升级到 heads）")
