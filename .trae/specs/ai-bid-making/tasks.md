# AI标书制作 - 实施任务清单（tasks.md）

> 状态：阶段 1.0 任务已规划（2026-09-28），1.1/1.2 为概要、进入前细化。
> 执行纪律：逐项完成 → 立即报告 → 用户确认 → 提交 → 再进入下一项；未经确认不跨项。
> 编码冻结：须收到用户明确"开始编码"指令后方可执行 Task 1。
> 任务类型的测试要求（TR）仅可为 `rule` 或 `rubric`。

## 阶段 1.0：Walking Skeleton（垂直骨架）
> 目标：以"1 家企业 + 1 个项目 + 和县真实采购文件 + 1 个云端模型"打通最小链路。

## Task 1: 开发环境、项目骨架与最小 CI
- **Status**: pending
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 准备基础工具链：Node.js ≥22.12、uv、Python 3.12（由 uv 安装，不依赖已损坏的系统 Python）。
  - 初始化 sidecar：pyproject + FastAPI 最小入口（`/health`）；生成并提交 `uv.lock`。
  - 初始化 electron-vite + React 18 + TypeScript；集成 Ant Design 5、Tailwind、React Router（Hash）。
  - package.json 一键脚本：`dev` 同时拉起 Renderer/Electron/Python sidecar；另含 lint、test 脚本。
  - 建立最小 GitHub Actions `ci.yml`（windows-latest，分层 job：lint → 单元 → 集成；PR 上额外触发 E2E 与黄金样本，对应 EM-6 触发矩阵；步骤为 `npm ci` → `uv sync --locked` → lint/类型检查 → 测试）。
  - Husky + lint-staged 提交前钩子（ESLint/Ruff/Prettier 只查暂存文件）。
  - 测试基础设施（EM-6 要求 Task 1 落地）：前端 Vitest（含最小用例与配置）；Python pytest（含 `conftest` 与隔离测试夹具基线）；CI `ci.yml` 按触发矩阵分层运行。
  - dev/prod 环境隔离骨架（NFR-7 / architecture.md 第十章要求 Task 1 落地）：userData 按 `VITE_DEV_SERVER_URL` 检测分流 `%AppData%\BidCraft-dev`（开发）/ `%AppData%\BidCraftApp`（生产）；sidecar 经 `--data-root` + `BIDCRAFT_DATA_ROOT` 接收数据根。
  - 自动更新框架骨架（NFR-7 / architecture.md 第十一章要求 Task 1 落地）：安装 `electron-updater` + `electron-builder`（NSIS）依赖与最小配置入口；发布/检查更新逻辑在阶段 1.0 末或发布前完善，本任务仅落地依赖与框架入口。
- **Acceptance Criteria Addressed**: （AC 待定义；对应技术约束"独立 Python 环境"与 devops-environment.md 第七节 Task 1 落地项）
- **Test Requirements**:
  - `rule` TR-1.1: `node -v`（≥22.12）与 Python venv 中 `python -c "import fastapi"` 均成功（命令输出为证）。
  - `rule` TR-1.2: `npm run dev` 能启动并打开空白 Electron 窗口，且 sidecar 被自动拉起（截图/日志为证）。
  - `rule` TR-1.3: `uv.lock` 与 `package-lock.json` 已提交，CI 中 `uv sync --locked`、`npm ci` 成功（CI 日志为证）。
  - `rule` TR-1.4: 最小 `ci.yml` 在 PR 上运行成功、状态全绿（GitHub Actions 页面为证）。
  - `rule` TR-1.5: `npm test` 可运行 Vitest 并通过最小用例；`uv run pytest` 可运行 pytest 并通过最小用例（测试输出为证）。
  - `rule` TR-1.6: CI `ci.yml` 存在分层 job（lint/单元/集成，PR 额外触发 E2E/黄金样本），PR 上触发成功（CI 页面为证）。
  - `rule` TR-1.7: 开发环境 userData 落在 `BidCraft-dev`、生产构建落在 `BidCraftApp`（目录检查/日志为证）。
  - `rule` TR-1.8: `electron-updater` 与 `electron-builder` 已在 package.json 依赖中并存在最小配置入口（依赖树/配置文件为证）。
- **Notes**:
  - 依赖版本在本任务锁定并记录；CI 状态检查在本任务后补入 main 分支保护规则。
  - 本任务通过 PR 合并（分支保护生效后首个 PR）。
  - electron-updater 本任务仅落地依赖与框架入口，更新检查/安装逻辑在发布前完善。

## Task 2: 应用外壳、导航与主题
- **Status**: pending
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 主窗口 + 左侧导航 + 主工作区布局；各模块占位页（企业/项目、解析、商务标、检查、配置）。
  - 明暗双主题切换（AntD5 + CSS 变量）；业务模块在未解锁前置灰。
- **Test Requirements**:
  - `rule` TR-2.1: 导航可在各占位页切换；主题切换后全部组件跟随（两种主题截图为证）。
  - `rule` TR-2.2: 1366×768 与 4K 缩放下布局不错乱（截图为证）。

## Task 3: Python Sidecar 进程管理与通信骨架
- **Status**: pending
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - Sidecar 实现 `/health`；Main 负责拉起/关闭（随机端口 + 本地令牌）、健康检查、崩溃检测。
  - preload 暴露 `sidecar:health/call/stream`、`task:cancel`；SSE 进度协议打通（测试事件流）。
- **Test Requirements**:
  - `rule` TR-3.1: 应用启动自动拉起 sidecar 且 `/health` 返回 200；退出后进程消失（日志/进程检查为证）。
  - `rule` TR-3.2: Renderer 经 IPC 调用 sidecar 成功收到 SSE 事件序列（控制台/日志为证）。
  - `rule` TR-3.3: sidecar 仅监听 127.0.0.1（配置与连接验证为证）。

## Task 4: 数据层（SQLite + 迁移 + 隔离基）
- **Status**: pending
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - SQLAlchemy 2 + Alembic；建立 architecture.md 第四节核心表（先 enterprise/project/config_kv/app_event，其余随阶段补）。
  - 仓储层统一注入 enterprise_id/project_id 过滤的隔离机制。
- **Test Requirements**:
  - `rule` TR-4.1: 迁移命令可从零建表（数据库文件与表清单为证）。
  - `rule` TR-4.2: pytest 覆盖跨企业/跨项目读取被拦截（测试结果为证）。

## Task 5: 企业/项目管理最小功能
- **Status**: pending
- **Priority**: high
- **Depends On**: Task 4
- **Description**:
  - 企业创建/编辑/列表/切换（必填校验：委托代理人）；项目创建/编辑/列表（委托代理人选填）。
  - "当前企业/当前项目"全局状态；进入企业后仅见本企业数据。
  - 委托代理人优先级（项目优先、缺省取企业）。
  - 删除/回收站在本任务做最小版（进回收站、不物理删）；30 天清理与完整 UI 可在 1.2 收尾完善。
- **Test Requirements**:
  - `rule` TR-5.1: 可创建企业并在其下创建项目；切换企业后互不可见（截图+pytest 为证）。
  - `rule` TR-5.2: 企业委托代理人必填拦截、项目缺省时回退企业代理人（测试结果为证）。
  - `rule` TR-5.3: 删除进入回收站而非物理删除（数据库状态为证）。

## Task 6: 模型配置与连通性
- **Status**: pending
- **Priority**: high
- **Depends On**: Task 5
- **Description**:
  - 系统配置页：云端模型（供应商/base_url/model）+ API Key（DPAPI 存储）；本地模型（Ollama）配置预留。
  - LiteLLM 网关接入；"测试连接"按钮返回模型响应；llm_call_log 记录模型/token/耗时。
  - 首次外联提示（NFR-3）。
- **Test Requirements**:
  - `rule` TR-6.1: 配置一个云端模型并测试连接成功（界面结果为证；Key 不落明文）。
  - `rule` TR-6.2: 一次测试调用在 llm_call_log 有记录（数据库记录为证）。

## Task 7: Walking Skeleton 端到端验收
- **Status**: pending
- **Priority**: high
- **Depends On**: Task 6
- **Description**:
  - 用和县真实样本走通：启动 → 创建企业 → 创建项目 → 进入项目 → 模型连通。
  - 在解析入口可选择并暂存招标文件（实际解析为 1.1 内容，本任务只到上传就绪）。
  - 验证状态机：PARSE_CONFIRMED 之前业务模块置灰。
- **Test Requirements**:
  - `rule` TR-7.1: 上述端到端步骤全部可执行、无阻断（操作录屏/截图为证）。
  - `rule` TR-7.2: 未确认清单前商务标/检查入口为置灰态（截图为证）。
- **Notes**: 本任务完成标志 1.0 结束。

## 阶段 1.1：招标文件解析（概要，进入前细化）
- Task 8: PDF/Word 文本与结构解析（MinerU 文字版提取 + 页码坐标/bbox + 表格；输出 Markdown/JSON，与 spec.md FR-2 一致）
- Task 9: 扫描件 OCR（MinerU 内置 PP-OCRv6 自动触发）与素材 OCR 文本落库
- Task 10: 解析配置（8 关键项 + 可选项；解析方式/高精度开关）
- Task 11: 规则粗分 + LLM 校验（原文锚定、幻觉拦截）+ 全文摘要审计
- Task 12: 评分办法解析 → `score_table.json`
- Task 13: 投标文件格式章节化 docx（封面 + 各章；人工增删、地址链接）
- Task 14: 解析清单 UI（逐条确认/增删、标红）+ 门禁解锁

## 阶段 1.2：商务标生成（概要，进入前细化）
- Task 15: 素材库管理（层级/命名规范、动态词典、归档、版本快照）
- Task 16: 素材提取清单（查询匹配、2-3 轮循环收敛）
- Task 17: 模板库管理（目录组织、模板编辑器、template.json、版本）
- Task 18: 模板匹配（≥90%）与语义比对（文件关联表、差异确认）
- Task 19: docxtpl 逐章渲染（文字/图片占位、缩放、不跨页）
- Task 20: 转 PDF、文档合并、图片压缩
- Task 21: 回收站完整功能与 30 天清理配置

## 问题（Review 修复项）
- （暂无，仅在独立评审产生 actionable 发现后，按 Issue I-N 登记）
