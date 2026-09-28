# 会话索引

| 编号 | 日期 | 主题 | 关键产出 | 记录文件 |
|---|---|---|---|---|
| 01 | 2026-09-27 | 仓库初始化 + Spec 文档骨架 + 对话记录机制 | 远程仓库关联、spec.md/tasks.md/checklist.md 空结构、对话记录目录 | [session-01.md](sessions/2026-09-27-session-01.md) |
| 02 | 2026-09-27 | 需求逐模块填充 FR-1～FR-5 | FR-1 企业/项目、FR-2 解析、FR-3 商务标、FR-4 素材库、FR-5 模板库需求；新增数据完整性/方案评估/测试样本规则 | [session-02.md](sessions/2026-09-27-session-02.md) |
| 03 | 2026-09-28 | 真实样本核验 + NFR + 技术选型与架构 | 和县采购/投标文件核验、8 条工程建议、5 项增补、NFR-1～6、假设、技术选型、架构设计、tasks/checklist | [session-03.md](sessions/2026-09-28-session-03.md) |
| 04 | 2026-09-28 | Task 1 编码：项目骨架与最小 CI | Electron44+React18+TS+AntD5+Tailwind 骨架、FastAPI sidecar(/health)、Vitest/pytest 分层、ci.yml 分层 job、Husky、dev/prod 隔离、electron-updater 骨架 | [session-04.md](sessions/2026-09-28-session-04.md) |
| 05 | 2026-09-28 | Task 3 编码：Sidecar 进程管理与通信骨架 | 随机端口+本地令牌、IPC 白名单(call/stream/cancel)、SSE 测试事件流、崩溃检测、127.0.0.1 限定；修复 shell 进程树孤儿问题 | [session-05.md](sessions/2026-09-28-session-05.md) |
| 06 | 2026-09-28 | Task 4 编码：数据层基座 | SQLAlchemy 2.1 ORM（enterprise/project/config_kv/app_event）、Alembic 首版迁移（从零建库实证）、仓储层 scope 统一注入（跨企业读写/写入拦截） | [session-06.md](sessions/2026-09-28-session-06.md) |
