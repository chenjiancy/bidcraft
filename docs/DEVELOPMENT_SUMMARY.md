# BidCraft AI 标书制作软件 — 开发总结

> 生成时间：2026-09-30
> 覆盖范围：Task 1 ~ Task 21 + 代码审查缺陷修复

---

## 一、项目概况

| 项目 | 内容 |
|---|---|
| **定位** | 个人项目：AI 驱动的监理标书辅助制作工具 |
| **核心底线** | **不废标**（所有质量门禁围绕此目标）|
| **技术栈** | Electron + React 18 + TypeScript + FastAPI + SQLite + MinerU OCR |
| **参考对象** | 易标（商务标生成工具）|
| **样本来源** | 用户提供的真实和县城投招标/投标文件（存 `samples-local/`，gitignore）|

---

## 二、阶段划分与完成情况

### Phase 1.0 — Walking Skeleton（垂直骨架）

> 目标：以"1 家企业 + 1 个项目 + 和县真实采购文件 + 1 个云端模型"打通最小链路。

| Task | PR | 内容 | 状态 |
|---|---|---|---|
| 1 | #13 | 开发环境骨架、最小 CI、Dev/Prod 分流 | ✅ |
| 2 | #15 | 应用外壳、导航、明暗主题 | ✅ |
| 3 | #17 | Sidecar 进程管理、IPC、SSE | ✅ |
| 4 | #19 | SQLite + Alembic + 隔离仓储 | ✅ |
| 5 | #22 | 企业/项目管理最小 CRUD + 回收站 | ✅ |
| 6 | #24 | 模型配置（DPAPI）、连通性测试、调用日志 | ✅ |
| 7 | #26 | 端到端走通（上传→解析→门禁→进入项目）| ✅ |

### Phase 1.1 — 解析能力（六任务）

> 目标：招标文件完整结构化解析，打通解析→评分→格式章节化→清单确认全流程。

| Task | PR | 内容 | 关键特性 |
|---|---|---|---|
| 8 | #31 | 文本/OCR 解析与结构化 | MinerU 3.4.5 独立 venv、.doc 转换、同名去重 |
| 9 | #33 | 解析配置（18 项目录 + LLM 开关）| 项目级落库、PARSED 后变更提示 |
| 10 | #34 | 规则粗分 + LLM 校验 | 术语识别+动态词典、幻觉拦截、全文审计 |
| 11 | #35 | 评分办法 → score_table.json | 规则抽取+LLM 兜底、schema 硬校验 |
| 12 | #36 | 投标文件格式章节化 docx | docxtpl 三来源统一、red_flags 不静默丢失 |
| 13 | #37 | 解析清单 UI + 门禁解锁 | PARSE_CONFIRMED 状态机、三条 Tab 确认 |

### Phase 1.2 — 商务标生成（八任务）

> 目标：素材→模板→渲染→PDF 导出全流程闭环。

| Task | PR | 内容 | 关键特性 |
|---|---|---|---|
| 14 | #38 | 商务标格式清单确认 | FORMAT_CONFIRMED 状态门禁 |
| 15 | #39 | 素材库管理 | 命名规范+OCR+归档管线+FTS5 索引+动态词典 |
| 16 | #40 | 素材提取清单 | 两源聚合+FTS5 BM25 查询+多轮循环收敛 |
| 17 | #41 | 模板库管理 | 版本管理+合规检查+软删除 |
| 18 | #43 | 模板匹配与语义比对 | TemplateCompare 关联表+差异确认+READY_TO_RENDER 门禁 |
| 19 | #44 | docxtpl 逐章渲染 | A/B 类占位+警告清单+跨页检测+一致性审计 |
| 20 | #45 | 转 PDF + PDF 合并 | PyMuPDF 合并+书签+EXTERNAL 排除 |
| 21 | #46 | 两级回收站 | 系统/企业内 + 定时清理 + purge_at 可配 |

### 质量保障 — 代码审查缺陷修复（2026-09-30）

> 全面代码审查识别出 9 Critical + 20 Major，逐条修复并提交到 main。

#### Critical（9 条，不废标底线）

| Commit | 问题 | 修复方案 |
|---|---|---|
| `45a11ca` | C2 归档成功后 unlink 用户源文件 | 取消 unlink，源文件保留在收件箱 |
| `7d919d4` | C9/C7 模板路径双前缀 + agency 路径穿越 | 统一为 data_root 绝对路径 + safe_filename |
| `fdfa8c7` | C1 Electron 路由白名单不含下划线 | 正则改为 `[a-z0-9_]+` |
| `97ff794` | C3 项目素材 file_path 双前缀 | 修正为 `_path_base / final_path` |
| `1e71046` | C4 score_table schema 校验失败仍转 SCORE_PARSED | raise ParseError 阻断状态升级 |
| `b6c80e2` | C5 PARSE_CONFIRMED 后重登记文件删产物不回退状态 | 先 ensure_transition 回退到 UPLOADED |
| `b732117` | C6 同名 doc/docx 转换互相覆盖 | 输出 unique_path |
| `9032d69` | C8 渲染时重新生成 render_plan 覆盖 B 类确认值 | 加载已有计划按章节+占位名匹配保留 |

#### Major（11 条）

| Commit | 问题 | 修复方案 |
|---|---|---|
| `7fff50c` | M1 purge 不删业务行 | 同时删除 enterprise/project/material/template 表记录 |
| `950e276` | M2 FTS5 索引无人调用 | 删除/恢复素材时同步更新索引 |
| `4c60eee` | M3 alembic 双头迁移 | merge revision 3b426c0f86f8 |
| `ab38f4b` | M4 SSE 事件结构不一致 | `_emit_progress` 统一为 `{stage, percent, message, extra?}` |
| `e21f0cb` | M5 素材分页 total 错误 | 新增 `repo.count()` 查询真实总数 |
| `7b0b3e9` | M6 健康检查超时不 kill | waitForHealth 失败时终止子进程 |
| `74182f1` | M10/M13/M14/M18 | 审计日志 + 路径穿越防护 + 重试 + 大小限制 |
| `9bab992` | M20 日志无统一配置 | main.py 添加 logging.basicConfig |
| `6d02599` | mypy 类型错误 2 处 | down_revision tuple 类型 + ensure_transition type: ignore |

---

## 三、测试结果

### 基线测试（全量）

| 维度 | 结果 | 备注 |
|---|---|---|
| pytest 集成测试 | **275 passed**（3 warnings）| 排除 engine 真实样本测试 |
| vitest 前端测试 | **40 passed**（8 test files）| 16.41s |
| ruff lint | ✅ All checks passed | |
| mypy 类型检查 | ✅ Success: no issues found in 111 source files | |
| eslint | ✅ `--max-warnings=0` | |
| tsc typecheck | ✅ node + web 全绿 | |
| alembic migrations | ✅ 单 head（3b426c0f86f8 merge revision）| |

### 已知预存问题

| 文件 | 问题 | 根因 | 与本次修复关系 |
|---|---|---|---|
| `tests/engine/test_real_parse.py` × 2 | 真实样本路径缺失 | `samples/` 目录为空，真实样本在 gitignored 的 `samples-local/` | **无关**（预存问题）|

---

## 四、GitHub 进度

| PR | 标题 | 状态 |
|---|---|---|
| #13 | Task 1 开发环境骨架 | ✅ 已合并 |
| #15 | Task 2 应用外壳导航 | ✅ 已合并 |
| #17 | Task 3 Sidecar 进程管理 | ✅ 已合并 |
| #19 | Task 4 数据层 SQLAlchemy+Alembic | ✅ 已合并 |
| #22 | Task 5 企业/项目管理 | ✅ 已合并 |
| #24 | Task 6 模型配置连通性 | ✅ 已合并 |
| #26 | Task 7 Walking Skeleton 验收 | ✅ 已合并 |
| #31 | Task 8 招标文件解析 | ✅ 已合并 |
| #33 | Task 9 解析配置 | ✅ 已合并 |
| #34 | Task 10 规则粗分+LLM 校验 | ✅ 已合并 |
| #35 | Task 11 评分办法解析 | ✅ 已合并 |
| #36 | Task 12 投标文件格式章节化 | ✅ 已合并 |
| #37 | Task 13 解析清单 UI+门禁 | ✅ 已合并 |
| #38 | Task 14 商务标格式清单 | ✅ 已合并 |
| #39 | Task 15 素材库管理 | ✅ 已合并 |
| #40 | Task 16 素材提取清单 | ✅ 已合并 |
| #41 | Task 17 模板库管理 | ✅ 已合并 |
| #43 | Task 18 模板匹配与语义比对 | ✅ 已合并 |
| #44 | Task 19 docxtpl 逐章渲染 | ✅ 已合并 |
| #45 | Task 20 转 PDF+合并（含 PyMuPDF 依赖修复）| ✅ 已合并 |
| #46 | Task 21 两级回收站 | ✅ 已合并 |
| main | 9 Critical + 11 Major 缺陷修复（18 commit）| ✅ 已推送 |

**当前 HEAD**：`6d02599`（fix: 修复 2 处 mypy 类型错误）

---

## 五、文档体系

| 文件 | 内容 | 最新状态 |
|---|---|---|
| `docs/PROJECT_RULES.md` | 项目硬约束与工作协议 | 规则 1–14 全量落盘 |
| `.trae/specs/ai-bid-making/spec.md` | 需求规格（FR/NFR/约束/AC）| Task 1–21 全部覆盖 |
| `.trae/specs/ai-bid-making/checklist.md` | 阶段检查清单 | Task 1–21 全部勾选 + 缺陷修复记录 |
| `.trae/specs/ai-bid-making/tasks.md` | 实施任务清单 | Phase 1.2 全部完成标记 |
| `docs/conversations/` | 每 Task 对话沉淀 | 1–21 各一次日志 |
| `docs/DEVELOPMENT_SUMMARY.md` | 本文件 | 2026-09-30 生成 |

---

## 六、方法论沉淀（规则 12–14）

| 规则 | 来源 | 核心内容 |
|---|---|---|
| **规则 12：依赖完整性** | Task 20 PyMuPDF 漏声明教训 | pyproject.toml 必须显式声明所有 import 的包；本机全绿 ≠ CI 全绿 |
| **规则 13：异常不静默** | Task 20 _merge_pdfs 吞异常教训 | 禁止 `except: pass` / `except: return False`；必须记录日志或暴露错误详情 |
| **规则 14：缺陷修复流程** | 今日全面审查实践 | 按业务后果从重到轻排序 → 逐条修复 → 报告 → 等确认 → 独立 commit → 下一条 |

---

## 七、下一步方向

### 短期（P0）
| 方向 | 说明 |
|---|---|
| **真实样本全链路走查** | 用 `samples-local/和县2026年老旧小区改造项目` 实际运行 9 步走查（启动→创建企业→上传招标文件→解析确认→素材归档→提取→模板匹配→渲染→PDF 导出），捕捉业务雷 |

### 中期（P1）
| 方向 | 说明 |
|---|---|
| **Task 20 推迟项** | 图片压缩（PyMuPDF 压缩优化）|
| **Phase 1.2 剩余 AC 验证** | 确认 AC-16~24 全部满足 |

### 长期（P2）
| 方向 | 说明 |
|---|---|
| **标书检查模块** | FR-6 待讨论（质量检查规则）|
| **PDF 合成** | 多 PDF 合并为最终标书 |
| **用户反馈闭环** | 上线后样本收集与模型调优 |

---

## 八、关键决策记录

| 决策 | 背景 | 结果 |
|---|---|---|
| MinerU 使用独立 `.venv-mineru` | torch/paddle 数 GB，与 sidecar 主 venv 隔离 | 不进 CI，仅本机开发使用 |
| 真实样本存 `samples-local/` | 含敏感信息的投标文件不进公开仓库 | gitignore，不推送 GitHub |
| 路由白名单采用正则而非白名单列表 | 扩展性好，避免每次加新接口都改代码 | 修复后支持下划线路径 |
| 素材 file_path 区分企业共享/项目独享 | 企业共享用绝对路径（purge 可直接 unlink），项目用相对路径 | 修复后统一为 `_path_base / final_path` |
| 回收站 purge 同时删业务表 | 软删除仅进回收站，purge 才是物理删除 | M1 修复后 enterprise/project/material/template 四表同步清除 |

---

*本文件为 BidCraft 项目第一阶段（Task 1–21 + 缺陷修复）的完整记录，供后续迭代参考。*
