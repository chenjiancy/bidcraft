"""TR-4.2：仓储层跨企业/跨项目读取与写入必须被拦截。"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.project import Project
from app.repositories.app_event import AppEventRepository
from app.repositories.base import (
    NotFoundError,
    Scope,
    ScopeViolationError,
)
from app.repositories.config_kv import ConfigKVRepository
from app.repositories.enterprise import EnterpriseRepository
from app.repositories.project import ProjectRepository


@pytest.fixture
def session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{(tmp_path / 'iso.db').as_posix()}", future=True)
    Base.metadata.create_all(engine)
    s = Session(engine, expire_on_commit=False)
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def two_enterprises(session: Session) -> tuple:
    enterprises = EnterpriseRepository(session)
    ent_a = enterprises.create(name="甲企业", agent="张三")
    ent_b = enterprises.create(name="乙企业", agent="李四")
    session.flush()
    return ent_a, ent_b


def test_project_get_cross_enterprise_blocked(session: Session, two_enterprises: tuple) -> None:
    ent_a, ent_b = two_enterprises
    pa = ProjectRepository(session, Scope(enterprise_id=ent_a.id)).create("A 的项目")
    pb = ProjectRepository(session, Scope(enterprise_id=ent_b.id)).create("B 的项目")
    session.flush()

    repo_a = ProjectRepository(session, Scope(enterprise_id=ent_a.id))
    assert repo_a.get(pa.id).name == "A 的项目"
    # 跨企业读 B 的项目：NotFound（不暴露存在性）
    with pytest.raises(NotFoundError):
        repo_a.get(pb.id)

    repo_b = ProjectRepository(session, Scope(enterprise_id=ent_b.id))
    with pytest.raises(NotFoundError):
        repo_b.get(pa.id)


def test_project_list_scoped_to_enterprise(session: Session, two_enterprises: tuple) -> None:
    ent_a, ent_b = two_enterprises
    ProjectRepository(session, Scope(enterprise_id=ent_a.id)).create("A1")
    ProjectRepository(session, Scope(enterprise_id=ent_a.id)).create("A2")
    ProjectRepository(session, Scope(enterprise_id=ent_b.id)).create("B1")
    session.flush()

    a_ids = {p.id for p in ProjectRepository(session, Scope(enterprise_id=ent_a.id)).list()}
    assert len(a_ids) == 2
    b_ids = {p.id for p in ProjectRepository(session, Scope(enterprise_id=ent_b.id)).list()}
    assert len(b_ids) == 1
    assert a_ids.isdisjoint(b_ids)


def test_add_outside_scope_rejected(session: Session, two_enterprises: tuple) -> None:
    ent_a, ent_b = two_enterprises
    forged = Project(name="伪造项目", enterprise_id=ent_b.id)
    repo_a = ProjectRepository(session, Scope(enterprise_id=ent_a.id))
    with pytest.raises(ScopeViolationError):
        repo_a.add(forged)
    session.flush()
    # 未落库：A 仓储与 B 仓储都查不到
    assert repo_a.list() == []
    assert ProjectRepository(session, Scope(enterprise_id=ent_b.id)).list() == []


def test_soft_delete_cross_enterprise_blocked(session: Session, two_enterprises: tuple) -> None:
    ent_a, ent_b = two_enterprises
    pb = ProjectRepository(session, Scope(enterprise_id=ent_b.id)).create("B 项目")
    session.flush()

    with pytest.raises(NotFoundError):
        ProjectRepository(session, Scope(enterprise_id=ent_a.id)).soft_delete(pb.id)
    # B 的项目仍然活着
    assert ProjectRepository(session, Scope(enterprise_id=ent_b.id)).get(pb.id).deleted_at is None


def test_app_event_cross_enterprise_blocked(session: Session, two_enterprises: tuple) -> None:
    ent_a, ent_b = two_enterprises
    pa = ProjectRepository(session, Scope(enterprise_id=ent_a.id)).create("A 项目")
    pb = ProjectRepository(session, Scope(enterprise_id=ent_b.id)).create("B 项目")
    session.flush()

    events_a = AppEventRepository(session, Scope(enterprise_id=ent_a.id))
    events_a.record("project.init", project_id=pa.id, payload={"x": 1})
    # 伪造他企业 project_id 记事件 → 拒绝
    with pytest.raises(NotFoundError):
        events_a.record("project.init", project_id=pb.id)
    # 查他企业项目的事件 → 空
    assert events_a.list_for_project(pb.id) == []
    assert len(events_a.list_for_project(pa.id)) == 1


def test_config_kv_enterprise_isolation(session: Session, two_enterprises: tuple) -> None:
    ent_a, ent_b = two_enterprises
    cfg = ConfigKVRepository(session)
    cfg.set_value("enterprise", "theme", "red", enterprise_id=ent_a.id)
    cfg.set_value("enterprise", "theme", "blue", enterprise_id=ent_b.id)
    cfg.set_value("system", "locale", "zh-CN")
    session.flush()

    assert cfg.get_value("enterprise", "theme", enterprise_id=ent_a.id) == "red"
    assert cfg.get_value("enterprise", "theme", enterprise_id=ent_b.id) == "blue"
    assert cfg.get_value("system", "locale") == "zh-CN"
    # A 未设置的键读不到 B 的值
    assert cfg.get_value("enterprise", "other", enterprise_id=ent_a.id) is None
