"""本地令牌鉴权（architecture.md 2.2）。

预期令牌由 Electron Main 生成并经 ``BIDCRAFT_SIDECAR_TOKEN`` 注入，
请求需带 ``Authorization: Bearer <令牌>``。

未配置环境变量（开发者手动裸跑 uvicorn）时不鉴权——sidecar 仅监听
127.0.0.1，且正常 Electron 链路必定注入令牌。
"""

import os
import secrets

from fastapi import Header, HTTPException, status


def require_sidecar_token(
    authorization: str | None = Header(default=None),
) -> None:
    expected = os.environ.get("BIDCRAFT_SIDECAR_TOKEN")
    if not expected:
        return

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少本地令牌",
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="本地令牌无效",
        )
