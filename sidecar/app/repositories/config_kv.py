"""config_kv 仓储：system / enterprise 两级，企业级必须带 enterprise_id。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.config_kv import ConfigKV
from app.repositories.base import RepositoryError

VALID_SCOPES = ("system", "enterprise")


class ConfigKVRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _stmt(self, scope: str, key: str, enterprise_id: str | None):
        if scope not in VALID_SCOPES:
            raise RepositoryError(f"非法 scope: {scope}")
        if scope == "enterprise" and not enterprise_id:
            raise RepositoryError("enterprise 级配置必须提供 enterprise_id")
        if scope == "system" and enterprise_id is not None:
            raise RepositoryError("system 级配置不得带 enterprise_id")
        return (
            select(ConfigKV)
            .where(ConfigKV.scope == scope)
            .where(
                ConfigKV.enterprise_id.is_(enterprise_id)
                if scope == "system"
                else ConfigKV.enterprise_id == enterprise_id
            )
            .where(ConfigKV.key == key)
        )

    def get_value(self, scope: str, key: str, enterprise_id: str | None = None) -> str | None:
        instance = self.session.execute(self._stmt(scope, key, enterprise_id)).scalar_one_or_none()
        return instance.value if instance else None

    def set_value(
        self,
        scope: str,
        key: str,
        value: str | None,
        enterprise_id: str | None = None,
    ) -> None:
        instance = self.session.execute(self._stmt(scope, key, enterprise_id)).scalar_one_or_none()
        if instance is None:
            self.session.add(
                ConfigKV(
                    scope=scope,
                    key=key,
                    value=value,
                    enterprise_id=enterprise_id if scope == "enterprise" else None,
                )
            )
        else:
            instance.value = value
