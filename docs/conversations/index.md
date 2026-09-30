# 会话索引

| 编号 | 日期 | 主题 | 关键产出 | 记录文件 |
|---|---|---|---|---|
| 01 | 2026-09-27 | 仓库初始化 + Spec 文档骨架 + 对话记录机制 | 远程仓库关联、spec.md/tasks.md/checklist.md 空结构、对话记录目录 | [session-01.md](sessions/2026-09-27-session-01.md) |
| 02 | 2026-09-27 | 需求逐模块填充 FR-1～FR-5 | FR-1 企业/项目、FR-2 解析、FR-3 商务标、FR-4 素材库、FR-5 模板库需求；新增数据完整性/方案评估/测试样本规则 | [session-02.md](sessions/2026-09-27-session-02.md) |
| 03 | 2026-09-28 | 真实样本核验 + NFR + 技术选型与架构 | 和县采购/投标文件核验、8 条工程建议、5 项增补、NFR-1～6、假设、技术选型、架构设计、tasks/checklist | [session-03.md](sessions/2026-09-28-session-03.md) |
| 04 | 2026-09-28 | Task 1 编码：项目骨架与最小 CI | Electron44+React18+TS+AntD5+Tailwind 骨架、FastAPI sidecar(/health)、Vitest/pytest 分层、ci.yml 分层 job、Husky、dev/prod 隔离、electron-updater 骨架 | [session-04.md](sessions/2026-09-28-session-04.md) |
| 05 | 2026-09-28 | Task 3 编码：Sidecar 进程管理与通信骨架 | 随机端口+本地令牌、IPC 白名单(call/stream/cancel)、SSE 测试事件流、崩溃检测、127.0.0.1 限定；修复 shell 进程树孤儿问题 | [session-05.md](sessions/2026-09-28-session-05.md) |
| 06 | 2026-09-28 | Task 4 编码：数据层基座 | SQLAlchemy 2.1 ORM（enterprise/project/config_kv/app_event）、Alembic 首版迁移（从零建库实证）、仓储层 scope 统一注入（跨企业读写/写入拦截） | [session-06.md](sessions/2026-09-28-session-06.md) |
| 07 | 2026-09-28 | Task 5 编码：企业/项目管理最小功能 | 企业/项目 CRUD + 回收站 + 全局企业/项目上下文，TR-5.1/5.2/5.3 全满足 | [session-07.md](sessions/2026-09-28-session-07.md) |
| 08 | 2026-09-28 | Task 8 编码：招标文件文本/OCR 解析与结构化 | MinerU 3.4.5 独立环境封装、去重/预处理/章节切分/Checkpoint 断点续跑、SSE 进度与取消、真实样本端到端验证（57 页文字版/97 页扫描件） | [session-08.md](sessions/2026-09-28-session-08.md) |
| 09 | 2026-09-29 | Task 9 编码：解析配置 | 18 项目录（8 关键必选+10 其他）+ LLM 总开关/模式、项目级 parse_project_config 表、GET/PUT config API、PARSED 后变更提示重解析、122+26 测试全绿 | [session-09.md](sessions/2026-09-29-session-09.md) |
| 10 | 2026-09-29 | Task 10 编码：规则粗分 + LLM 校验 | rules/ 纯逻辑包（catalog/terms/nature/extract/anchor）、术语动态词典、LLM 校验+幻觉拦截+全文审计、cached_tokens 迁移、extract:coarse/extract:llm checkpoint、双通道禁用、148 测试全绿（PR #34） | [session-10-rule-extract.md](session-10-rule-extract.md) |
| 11 | 2026-09-29 | Task 11 编码：评分办法解析 → score_table.json | rules/scoring 子集（大类/评分项/材料/门槛三类+多来源合并+合计≠100 标红不阻断）、JSON Schema 硬校验门禁、状态机 SCORE_PARSED、score:extract/score:llm checkpoint、LLM 专项校验、前端评分表摘要、153+30 测试全绿（PR #35） | [session-11-score-table.md](session-11-score-table.md) |
| 12 | 2026-09-29 | Task 12 编码：投标文件格式章节化 docx | 三来源统一走 MinerU content_list + chapters.json 页码边界、docx_build（封面整树兜底/HTML+MD 表格/仿宋/命名保序/路径校验）、parse/docx/ 产物 + manifest、stage 8 docx:<stem>:<seq> 动态 checkpoint 章级失败重试、reset 级联、前端格式摘要卡片、172+32 测试全绿（PR #36） | [session-12-docx-chapters.md](session-12-docx-chapters.md) |
| 13 | 2026-09-29 | Task 13 编码：解析清单 UI + 门禁解锁 | 状态机 PARSE_REVIEW/PARSE_CONFIRMED、三 Tab 清单复核（规则粗分/评分表/投标文件格式）、逐条确认+标红+全确认才解锁、docx 打开走 Electron IPC 带路径校验、parse:confirm checkpoint、上游重试回退、移除前端错误自动解锁、178+32 测试全绿（PR #37） | [session-13-parse-checklist-gate.md](session-13-parse-checklist-gate.md) |
| 14 | 2026-09-30 | 合并冲突清理 + 远端 main 污染修复 + C6 缺陷修复 | 坏合并 b82615c 把冲突标记与重复键提交并推入 origin/main（9 文件、纯删除 109 行）；定位并修复 convert_to_pdf 返回不存在路径的 C6 缺陷（staging 目录 + 唯一名移入）；新增 test_preprocess.py 回归护栏；pytest 287 passed、vitest 74 passed、lint/typecheck 全绿（PR 待合） | [session-14-merge-repair.md](session-14-merge-repair.md) |
