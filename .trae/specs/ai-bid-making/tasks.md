# AI标书制作 - 实施任务清单（tasks.md）

> 状态：Phase 1.0 已完成（Task 1-7，PR #13/#15/#17/#19/#22/#24/#26）；Phase 1.1 全部 Task 已落盘（Task 8-13，待"开始编码"指令）；1.2 为概要、进入前细化。
> 执行纪律：逐项完成 → 立即报告 → 用户确认 → 提交 → 再进入下一项；未经确认不跨项。
> 编码冻结：须收到用户明确"开始编码"指令后方可执行 Task 1。
> 任务类型的测试要求（TR）仅可为 `rule` 或 `rubric`。

## 阶段 1.0：Walking Skeleton（垂直骨架）
> 目标：以"1 家企业 + 1 个项目 + 和县真实采购文件 + 1 个云端模型"打通最小链路。

## Task 1: 开发环境、项目骨架与最小 CI
- **Status**: done（2026-09-28 合并，PR #13，TR-1.1～1.8 全部满足）
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
- **Status**: done（2026-09-28 合并，PR #15，TR-2.1～2.2 全部满足）
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 主窗口 + 左侧导航 + 主工作区布局；各模块占位页（企业/项目、解析、商务标、检查、配置）。
  - 明暗双主题切换（AntD5 + CSS 变量）；业务模块在未解锁前置灰。
- **Test Requirements**:
  - `rule` TR-2.1: 导航可在各占位页切换；主题切换后全部组件跟随（两种主题截图为证）。
  - `rule` TR-2.2: 1366×768 与 4K 缩放下布局不错乱（截图为证）。

## Task 3: Python Sidecar 进程管理与通信骨架
- **Status**: done（2026-09-28 合并，PR #17，TR-3.1～3.3 全部满足）
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
- **Status**: done（2026-09-28 合并，PR #19，TR-4.1/4.2 全部满足）
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - SQLAlchemy 2 + Alembic；建立 architecture.md 第四节核心表（先 enterprise/project/config_kv/app_event，其余随阶段补）。
  - 仓储层统一注入 enterprise_id/project_id 过滤的隔离机制。
- **Test Requirements**:
  - `rule` TR-4.1: 迁移命令可从零建表（数据库文件与表清单为证）。
  - `rule` TR-4.2: pytest 覆盖跨企业/跨项目读取被拦截（测试结果为证）。

## Task 5: 企业/项目管理最小功能
- **Status**: done（2026-09-28 合并，PR #22，TR-5.1～5.3 全部满足）
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
- **Status**: done（2026-09-28 合并，PR #24，TR-6.1/6.2 满足）
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
- **Status**: done（2026-09-28 合并，PR #26，TR-7.1/7.2 满足）
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

## 阶段 1.1：招标文件解析（细化中）
> **借鉴点参考**（详见 [yibiao-borrowing.md](file:///e:/bidcraft/bidcraft-master/docs/references/yibiao-borrowing.md)）：
> - BP-1 长任务 Checkpoint（高）：解析多项任务独立 checkpoint，断点续跑、单项重试。
> - BP-3 Schema 硬校验（高）：score_table.json 等核心产物结构校验，阶段交接门禁。
> - BP-4 确定性与语义分工（高）：规则库前置做机械检查，LLM 仅做语义判断。
> - BP-10 提示词缓存预热（低）：LLM 可选路径多项调用时缓存预热降成本。
> 借鉴点拆解进度：BP-1 已拆解至 Task 8/11（TR-8.7/TR-11.9）；BP-3 已拆解至 Task 11（TR-11.6）；BP-4 已拆解至 Task 10；BP-10 已拆解至 Task 10。全部拆解完成。

## Task 8: 招标文件文本/OCR 解析与结构化
- **Status**: pending
- **Priority**: high
- **Depends On**: Task 7
- **Description**:
  1. **MinerU 集成与版本锁定**（决策 TS-2）：锁定 MinerU 具体版本，本机 GPU 3060Ti 8G 加速配置；封装 MinerU 调用接口（输入文件路径 → 输出 Markdown + JSON）。
  2. **输入预处理**：`.doc`（老二进制 Word）经 LibreOffice headless 转 PDF/docx 再进 MinerU（保留原貌）；`.docx`/`.pdf` 直接进 MinerU。
  3. **文本/OCR 自动分流提取**（FR-2 第 1 点）：MinerU 自动判断输入类型——文字版走文本提取，扫描件走内置 PP-OCRv6（无需自建 OCR 管线）；统一输出 Markdown（正文）+ JSON（带页码坐标和 bbox，满足原文锚定）；表格结构提取。
  4. **章节切分与子节结构建立**：整份合并单文件（单 PDF/单 docx 含全部章节）解析后先做章节切分（与"逐章 docx"假设对齐，docx 落地在 Task 12）；混合章节（如商务+技术混合）在切分时建立子节结构，内容性质标注在 Task 10。
  5. **同名多格式去重**：识别同名多格式同内容文件（如`资格证明.doc`+`资格证明.pdf`），保留主格式（docx 优先于 doc，pdf 兜底），去重项不入解析清单/风险清单，视为噪声内部消化。
  6. **源文件噪声容错**：章节识别以正文实质内容为准、目录仅交叉校验；比对按内容顺序匹配而非编号数字；文字颜色/底纹等视为噪声。
  7. **长任务 Checkpoint（BP-1，高优先级）**：解析作为长任务，独立 checkpoint 落盘（状态：idle/running/success/error + 内容），任务中断后只跑未成功项；支持单项重试。Checkpoint 框架在 Task 8 建立，供 Task 9-13 复用。
  8. **状态机扩展（EM-5）**：在 Task 7 状态机骨架基础上扩展解析阶段状态（UPLOADED→PARSING→PARSED），状态转换留痕，异常标记 error 不静默。
  9. **产物存储**：MinerU 输出的 Markdown/JSON 存于项目内目录（如 `<project>/parse/raw/`），按项目隔离；具体路径在 Task 8 落盘前同步补充到架构文档。
- **Acceptance Criteria Addressed**: FR-2 第 1 点（上传/入口/OCR 自动处理）、第 3 点（解析引擎 MinerU）、第 4 点（章节切分与去重、源文件噪声容错）
- **Test Requirements**:
  - `rule` TR-8.1: 文字版 PDF（和县柳庄路样本）经 MinerU 解析成功输出 Markdown + JSON，JSON 含页码坐标和 bbox（输出文件为证）。
  - `rule` TR-8.2: 扫描件 PDF 经 MinerU 自动触发 PP-OCRv6 OCR 成功，输出与文字版格式一致（输出文件为证）。
  - `rule` TR-8.3: `.doc` 文件经 LibreOffice headless 转换后进 MinerU 成功解析（转换日志+输出为证）。
  - `rule` TR-8.4: 整份合并单文件解析后章节切分正确，切分章节数与目录/正文一致（切分结果为证）。
  - `rule` TR-8.5: 同名多格式同内容文件识别后去重，保留主格式（docx>doc>pdf），去重项不入清单（去重日志为证）。
  - `rule` TR-8.6: 源文件噪声容错——目录页码错乱/编号跳号重复/标题不一致等噪声内部消化，不打扰用户、不进风险清单（解析结果为证）。
  - `rule` TR-8.7: 长任务 Checkpoint——解析中断后重启只跑未成功项，已成功项结果保留（中断恢复日志为证）。
  - `rule` TR-8.8: 状态机 UPLOADED→PARSING→PARSED 转换留痕，异常时标记 error 不静默（状态日志为证）。
  - `rule` TR-8.9: 解析产物按项目隔离存储，跨项目互不可见（存储路径检查+隔离测试为证）。
- **Notes**:
  - MinerU 版本在 Task 8 锁定（TS-2 决策点落地）。
  - Task 8 不涉及 LLM（默认路径），LLM 可选路径在 Task 10（原 Task 11）。
  - 章节切分后的逐章 docx 落地在 Task 12（原 Task 13）。
  - 素材库 OCR 文本落库（原 Task 9 的一部分）移至 Phase 1.2 Task 15 素材库管理。
  - 样本已就绪（文字版/扫描件/.doc/整份合并/同名多格式）。

## Task 9: 解析配置
- **Status**: pending
- **Priority**: high
- **Depends On**: Task 8
- **Description**:
  1. **配置项定义**：8 关键项（必选、不可取消）+ 其他项（可选）。关键项按 spec.md FR-2 第 2 点：项目概述、技术评分要求、项目信息、甲方信息、响应文件要求、代理机构信息、商务评分要求、无效标与废标项。其他项按 spec.md 清单（交货和服务要求、采购清单、投标关键节点、投标保证金、资格性审查、符合性检查、开标要求、评标要求、合同授予与签订、合同解除和终止等）。
  2. **LLM 辅助配置**（BP-4 分工开关）：启用 LLM 辅助（总开关，默认关）+ 模式选择（二选一：校验模式 / 双通道模式），仅当总开关开启时模式选择生效；总开关关闭时走默认路径（纯确定性，无 LLM）。
  3. **配置 UI**：上传招标文件后、启动解析前的配置面板；支持勾选其他项、切换 LLM 总开关与模式；关键项强制勾选不可取消。
  4. **配置存储**：项目级配置，存入数据库（config_kv 表或专用配置表）；不设置时使用默认配置（8 关键项必选、其他项默认不选、LLM 总开关默认关）。
  5. **配置变更与重新解析**：用户修改配置后，提示受影响项需重新解析（复用 Task 8 建立的 BP-1 Checkpoint 单项重试机制）。
- **Acceptance Criteria Addressed**: FR-2 第 2 点（解析配置）
- **Test Requirements**:
  - `rule` TR-9.1: 配置 UI 展示 8 关键项（必选、不可取消）+ 其他项（可勾选），与 spec.md FR-2 第 2 点清单一致（界面截图为证）。
  - `rule` TR-9.2: LLM 总开关默认关闭，关闭时模式选择置灰；开启后可选校验模式或双通道模式（界面交互为证）。
  - `rule` TR-9.3: 配置存入项目级数据库，不设置时使用默认配置（数据库记录为证）。
  - `rule` TR-9.4: 修改配置后提示受影响项需重新解析，复用 Checkpoint 单项重试（操作日志为证）。
- **Notes**:
  - Task 9 是配置 UI，Task 8 是解析引擎；用户操作顺序为"上传→配置→解析"，开发顺序为"引擎→配置 UI"（先有引擎再建配置 UI）。
  - 原 tasks.md 概要中的"高精度开关"在 spec.md 中对应"LLM 总开关 + 模式选择"（FR-2 第 2 点），非独立开关；本任务统一术语为"LLM 总开关 + 模式选择"。
## Task 10: 规则粗分 + LLM 校验（默认路径 + 校验模式）
- **Status**: pending
- **Priority**: high
- **Depends On**: Task 9
- **Description**:
  1. **规则库建立（BP-4 + EM-3）**：版本化、可单元测试的规则库，识别规则能确定的要素（页数上限、社保月份、金额格式、提示语残留、占位未填等）；规则库随业务持续扩充；规则库前置做机械检查，不调用 LLM。
  2. **默认路径：规则粗分**（FR-2 第 3 点）：MinerU 解析结果 → 规则库分类（资格条款、废标条款、商务评分、技术要求）→ 原文锚定校验（约束必须能在原文片段找到对应文字，找不到标红）。完全确定性、可重复。
  3. **术语识别**（FR-2 第 4 点）：解析时判定文件类型（招标/采购/询比价，封面等位置可判），软件新生成的文字按对应术语体系（投标人/投标文件/投标函 或 供应商/响应文件/报价函 等）；询比价应答文件称"询比价响应文件"或"响应文件"，具体称谓记入动态词典；源文件原文一律原样保留，绝不做全局术语替换。
  4. **混合章节内容性质标注**（FR-2 第 4 点）：存在商务+技术混合章节（如"五、服务方案"下：供应商介绍/人员力量/业绩/荣誉为商务子节，监理大纲为技术子节），Task 8 已建立子节结构，本任务标注内容性质（商务子节/技术子节）；一期商务子节正常进素材提取、模板比对与生成，技术子节仅保留评分点标题骨架；状态机按子节记录状态。
  5. **可选路径：校验模式**（FR-2 第 3 点，LLM 可选）：LLM 对已有解析结果做校验——识别实质性要求/否决投标项、检查隐藏硬性约束、标记隐性条款，输出【是否硬性条款 + 约束条件 + 原文片段引用 + 风险标记】；约束必须能在原文找到（拦截幻觉）。
  6. **全文摘要审计**（FR-2 第 3 点，校验模式的一部分）：LLM 通读全文输出要求大类，与解析大类做数量校验，发现漏章节。
  7. **提示词缓存预热（BP-10，低优先级）**：校验模式多项调用 LLM 时，先单独运行"项目概述"项，成功后等待缓存生效，再将其余解析项全部并发提交；系统提示 + 完整招标文件作为公共前缀被缓存，后续请求只付增量 token 费用。
  8. **输出**：提取/比对结果全部以可编辑清单形式呈现，不一致处标红（清单 UI 在 Task 13）。
  9. **双通道模式推迟**：双通道模式（原方案二）推迟到后续迭代，本任务不实现。
- **Acceptance Criteria Addressed**: FR-2 第 3 点（默认路径 + 校验模式）、第 4 点（术语识别、混合章节按子节处理）、EM-3（规则库前置）、BP-4（确定性与语义分工）、BP-10（提示词缓存预热）
- **Test Requirements**:
  - `rule` TR-10.1: 规则库分类——给定 MinerU 解析结果，规则库正确分类为资格条款/废标条款/商务评分/技术要求（分类结果为证）。
  - `rule` TR-10.2: 原文锚定校验——规则库识别的约束能在原文片段找到对应文字，找不到标红（校验结果为证）。
  - `rule` TR-10.3: 规则库可单元测试——给定固定输入，规则库输出固定结果，可重复（单元测试为证）。
  - `rule` TR-10.4: 术语识别——判定文件类型正确（招标/采购/询比价），新生成文字按对应术语体系；源文件原文原样保留（识别结果为证）。
  - `rule` TR-10.5: 混合章节按子节处理——建立子节结构并标注内容性质（商务子节/技术子节），状态机按子节记录状态（结构+状态为证）。
  - `rule` TR-10.6: 校验模式（LLM 开启时）——LLM 输出【是否硬性条款 + 约束条件 + 原文片段引用 + 风险标记】，约束能在原文找到（拦截幻觉），找不到标红（校验结果为证）。
  - `rule` TR-10.7: 全文摘要审计（LLM 开启时）——LLM 通读全文输出要求大类，与解析大类做数量校验，发现漏章节（审计结果为证）。
  - `rule` TR-10.8: 提示词缓存预热（LLM 开启时）——先跑"项目概述"项预热缓存，其余项并发提交，llm_call_log 对比预热前后 token 消耗（日志为证）。
  - `rule` TR-10.9: 双通道模式未实现——总开关关闭时走默认路径（不调 LLM），开启校验模式时不触发双通道（代码审查为证）。
- **Notes**:
  - 规则库在 Task 10 建立，随业务持续扩充。
  - 双通道模式推迟到后续迭代（spec.md Roadmap"高精度双通道后续迭代"）。
  - 术语识别归属 Task 10；混合章节建立子节结构在 Task 8，标注内容性质在 Task 10。
## Task 11: 评分办法解析 → `score_table.json`【原 Task 12，编号顺延】
- **Status**: pending
- **Priority**: high
- **Depends On**: Task 10
- **Description**:
  1. **规则库新建评分表专用规则子集**（`rules/scoring/`，版本化、可单元测试）：Task 10 规则库只到大类粗分，Task 11 新建评分表专用规则子集，负责评分表行/列识别、字段映射、分值/门槛条件抽取；规则子集随业务持续扩充（与 Task 10 规则库同机制）。
  2. **解析方式**（方案 A）：规则库前置做机械抽取，LLM 仅做校验模式增强，与 Task 10 复用同一套 LLM 开关与模式选择（总开关默认关，关闭时走纯规则库，不调 LLM）。
  3. **统一层级结构抽取**（FR-2 第 4 点）：评分大类 → 评分项 → 分值 → 所需证明材料 → 门槛条件（日期/金额/数量）。
  4. **所需证明材料**（A）：仅从评分办法原文抽取评分项要求的材料名称（如"监理大纲""人员配置表""业绩证明"），不做素材库匹配（匹配留 Phase 1.2 素材提取清单）。
  5. **门槛条件**（A1）：规则库用正则/模式匹配抽取三类硬性条件——日期（如"近 3 年"、有效期）、金额（如"合同金额≥XX 万"）、数量（如"≥3 个业绩"）；识别不出的存原文片段 + 标红，提示人工处理（不静默）。
  6. **多来源合并**（A）：规则库支持从多个章节/表格抽取并合并为单一 `score_table.json`，评分大类字段标识来源章节（如"商务评分""技术评分"），跨表合计校验。
  7. **评分合计校验**（A）：规则库校验分值合计（如总分应为 100），合计≠100 时标红披露但不阻断产出 JSON（人工兜底修正）。
  8. **Schema 硬校验门禁**（方案 A，BP-3 高优先级）：产出 `score_table.json` 后立即用 JSON Schema 校验结构（字段齐全/类型正确），校验失败进修复循环（标红、人工修正），通过后标记"结构已校验"标志位；Task 13 只查标志位，不重复校验。
  9. **LLM 校验模式专项增强**（B）：LLM 开启校验模式时，Task 11 新增评分办法专项校验——评分项完整性（是否覆盖评分办法原文所有评分项）、分值合计（跨表合计是否正确）、门槛遗漏（是否遗漏门槛条件），与 Task 10 通用校验互补。
  10. **状态机扩展**（B，EM-5）：在 Task 8 的 UPLOADED→PARSING→PARSED 基础上新增 SCORE_PARSED 状态，状态机扩展为 UPLOADED→PARSING→PARSED→SCORE_PARSED，评分办法解析作为独立阶段留痕，状态转换留痕，异常标记 error 不静默。
  11. **BP-1 Checkpoint 复用**：复用 Task 8 建立的 BP-1 Checkpoint 框架，评分办法解析作为独立 checkpoint 项（状态：idle/running/success/error + 内容），断点续跑、单项重试。
  12. **产物存储**：`<project>/parse/structured/score_table.json`，与 raw 平级的 structured 子目录，按项目隔离；该 JSON 是 Task 10 清单中"评分办法"部分的结构化子产物，Task 13 清单 UI 中评分办法部分引用此 JSON 渲染。
  13. **三处复用**（FR-2 第 4 点）：`score_table.json` 一处产出、三处复用——(1) Phase 1.2 素材提取清单来源；(2) Phase 1.2 商务标检查清单来源；(3) Phase 4 AI 评标打分表。
- **Acceptance Criteria Addressed**: FR-2 第 4 点（score_table.json 核心对象、统一层级结构、一处产出三处复用）、EM-5（状态机扩展 SCORE_PARSED）、BP-3（Schema 硬校验门禁）、BP-1（Checkpoint 复用）、BP-4（规则库前置 + LLM 校验分工）
- **Test Requirements**:
  - `rule` TR-11.1: 评分表专用规则子集——给定评分办法原文，规则库正确识别评分表行/列、抽取评分大类/评分项/分值（抽取结果为证）。
  - `rule` TR-11.2: 所需证明材料抽取——仅抽取材料名称，不匹配素材库（抽取结果为证）。
  - `rule` TR-11.3: 门槛条件抽取——日期/金额/数量三类用正则/模式匹配抽取为结构化字段，识别不出的存原文片段 + 标红（抽取结果为证）。
  - `rule` TR-11.4: 多来源合并——多个章节/表格的评分信息合并为单一 JSON，评分大类字段标识来源章节（合并结果为证）。
  - `rule` TR-11.5: 评分合计校验——分值合计≠100 时标红披露但不阻断产出 JSON（校验结果为证）。
  - `rule` TR-11.6: Schema 硬校验——产出后立即用 JSON Schema 校验，失败进修复循环，通过后标记"结构已校验"标志位（校验日志为证）。
  - `rule` TR-11.7: LLM 校验模式专项——评分项完整性/分值合计/门槛遗漏校验（LLM 开启时，校验结果为证）。
  - `rule` TR-11.8: 状态机扩展——UPLOADED→PARSING→PARSED→SCORE_PARSED 转换留痕，异常标记 error 不静默（状态日志为证）。
  - `rule` TR-11.9: BP-1 Checkpoint——评分办法解析作为独立 checkpoint 项，中断后重启只跑未成功项，已成功项结果保留（中断恢复日志为证）。
  - `rule` TR-11.10: 产物按项目隔离存储，跨项目互不可见（存储路径检查+隔离测试为证）。
- **Notes**:
  - Task 11 是 Task 10 规则粗分的深度结构化（评分办法部分），不是独立模块。
  - 评分表专用规则子集随业务持续扩充（与 Task 10 规则库同机制）。
  - 双通道模式推迟到后续迭代（与 Task 10 一致）。
  - 样本已就绪（含评分办法章节的招标文件）。
## Task 12: 投标文件格式章节化 docx【原 Task 13，编号顺延】
- **Status**: pending
- **Priority**: high
- **Depends On**: Task 11
- **Description**:
  1. **范围边界**（方案 A）：Task 12 只做"自动切分 + 逐章保存（含封面）"。"人工增删、地址链接"属商务标阶段（spec.md FR-3 第 1 点），留到 Phase 1.2。
  2. **章节识别复用 Task 8**（方案 C）：Task 8 章节切分已识别"投标文件格式"章节边界，Task 12 在该边界内做子章节切分 + docx 落地，不重复识别。
  3. **docx 内容来源**（方案 C，混合）：
     - 文字版 PDF/docx：从原文件直接抽取每章内容保存为 docx（保留原貌，FR-2 第 1 点原则）。
     - 扫描件 PDF：无原文件文本可抽取，从 MinerU OCR 的 Markdown 转 docx（用 python-docx 或 pandoc）。
  4. **封面处理**（方案 C）：识别到封面则单独保存为独立 docx（`00_封面.docx`），无封面则跳过。
  5. **子章节命名规范**（方案 A）：序号 + 章节名，如 `00_封面.docx`、`01_投标函.docx`、`02_法定代表人身份证明.docx` 等；序号保持原文顺序；重名时加后缀区分。
  6. **产物存储**：`<project>/parsed/` 目录（架构文档第五章已定义），按项目隔离。
  7. **状态机**（方案 A）：复用 SCORE_PARSED 状态，不新增状态；通过 `parsed/` 目录文件存在性 + 完成标志位区分是否落地完成。
  8. **BP-1 Checkpoint 复用**：复用 Task 8 建立的 BP-1 Checkpoint 框架，章节化落地作为独立 checkpoint 项（状态：idle/running/success/error + 内容），断点续跑、单项重试（某章失败重启只重跑该章）。
  9. **与 Task 13 的关系**：Task 12 产出逐章 docx，Task 13 解析清单 UI 引用这些 docx 展示地址链接（供人工复核）；Task 12 是产出方，Task 13 是展示与确认方。
- **Acceptance Criteria Addressed**: FR-2 第 4 点（章节切分与去重、整份合并单文件切分逐章保存）、FR-3 第 1 点（docx 逐章保存部分，人工增删/地址链接留 Phase 1.2）、BP-1（Checkpoint 复用）
- **Test Requirements**:
  - `rule` TR-12.1: 整份合并单文件（文字版 PDF）——从原文件抽取每章内容保存为逐章 docx，封面单独保存（输出文件为证）。
  - `rule` TR-12.2: 整份合并单文件（扫描件 PDF）——从 MinerU OCR 的 Markdown 转换为逐章 docx（输出文件为证）。
  - `rule` TR-12.3: 整份合并单文件（docx）——从原文件抽取每章内容保存为逐章 docx，保留原貌（输出文件为证）。
  - `rule` TR-12.4: 子章节命名规范——`00_封面.docx`、`01_投标函.docx` 等序号+章节名，序号保持原文顺序，重名加后缀（文件名为证）。
  - `rule` TR-12.5: 封面处理——有封面则单独保存为独立 docx，无封面则跳过不报错（输出文件+日志为证）。
  - `rule` TR-12.6: 产物按项目隔离存储，跨项目互不可见（存储路径检查+隔离测试为证）。
  - `rule` TR-12.7: BP-1 Checkpoint——章节化落地作为独立 checkpoint 项，某章失败重启只重跑该章，已成功章结果保留（中断恢复日志为证）。
- **Notes**:
  - Task 12 只做自动切分 + 逐章保存，"人工增删、地址链接"属商务标阶段（Phase 1.2）。
  - Task 12 复用 Task 8 的章节切分边界，不重复识别。
  - 状态机复用 SCORE_PARSED，不新增状态。
  - Task 11（评分办法解析）与 Task 12（投标文件格式章节化）逻辑上可并行（均依赖 Task 10 规则粗分），按编号顺序 Task 12 Depends On Task 11，开发时可按需调整顺序。
  - 样本已就绪（含投标文件格式章节的招标文件）。
## Task 13: 解析清单 UI（逐条确认/增删、标红）+ 门禁解锁【原 Task 14，编号顺延】
- **Status**: pending
- **Priority**: high
- **Depends On**: Task 12
- **Description**:
  1. **清单 UI 组织（分区/分 tab 独立展示）**：三类解析产物分区/分 tab 独立展示——
     - **Tab 1：规则粗分清单**（Task 10 产物）——按 Task 9 的 8 关键项 + 其他项分区组织，每条含原文锚定校验结果、LLM 校验结果（若开启）、术语识别、混合章节子节标注；不一致处标红。
     - **Tab 2：评分表**（Task 11 `score_table.json`）——按统一层级结构（评分大类→评分项→分值→所需证明材料→门槛条件）展示；查"结构已校验"标志位（不重复 Schema 校验）；合计≠100、门槛识别不出等标红。
     - **Tab 3：投标文件格式**（Task 12 逐章 docx）——列表展示 `<project>/parsed/` 下逐章 docx，每条附地址链接便于人工查核（点击打开文件）。
  2. **可编辑操作**：
     - **逐条确认**：每条目可确认/修改。
     - **增删**：仅限解析阶段的条目级修正（如规则粗分误分类的删除/修正、被遗漏解析项的新增补录）；商务标阶段的人工增删/地址链接回填属 Phase 1.2，不在 Task 13。
     - **标红**：统一呈现 Task 10（原文锚定找不到、LLM 校验差异）、Task 11（合计≠100、门槛条件识别不出）的标红场景。
  3. **门禁解锁逻辑**：
     - **转换条件**：清单中全部条目都逐条确认才能保存解锁；未确认的条目标红提醒，阻断保存。
     - **标红不永久阻断**：标红项经人工确认后即解除阻断（人工兜底，符合"解析需人工兜底"核心原则）。阻断的是"未确认"，不是"标红"——标红只是提示有不一致需人工关注。
     - **解锁范围**：商务标制作 + 标书检查及其他非配置类业务模块；配置类功能不受门禁限制（spec FR-2 第 1 点）。
  4. **状态机**：PARSE_REVIEW（待人工确认清单）→ PARSE_CONFIRMED（清单已确认，解锁业务模块），复用 architecture.md 已定义状态，不新增状态。
  5. **BP-1 Checkpoint 复用**：复用 Task 8 建立的 BP-1 Checkpoint 框架，清单确认作为独立 checkpoint 项（状态：idle/running/success/error + 内容），断点续跑、单项重试。
  6. **产物存储**：清单确认结果保存到 `<project>/parse/confirmed/parse_checklist.json`（架构文档第五章 parse/ 目录下新增 confirmed/ 子目录），按项目隔离；同时经 `/parse/confirm` API 落库（architecture.md 已定义）。
- **Acceptance Criteria Addressed**: FR-2 第 1 点（功能门禁）、第 4 点（输出与确认）、AC-14（UI 清单 + 门禁解锁）、BP-1（Checkpoint 复用）
- **Test Requirements**:
  - `rule` TR-13.1: 清单 UI 分区/分 tab 展示——规则粗分清单（按 8 关键项+其他项分区）、评分表、投标文件格式三 tab 独立展示（界面截图为证）。
  - `rule` TR-13.2: 投标文件格式 tab 每条附地址链接，点击可打开逐章 docx 文件（操作录屏为证）。
  - `rule` TR-13.3: 逐条确认——每条目可确认/修改，未确认条目标红提醒，阻断保存（界面交互为证）。
  - `rule` TR-13.4: 增删仅限解析阶段条目级修正——可删除误分类条目、新增遗漏解析项；商务标阶段增删不在此实现（代码审查为证）。
  - `rule` TR-13.5: 标红统一呈现——原文锚定找不到、LLM 校验差异、合计≠100、门槛识别不出等标红场景在清单 UI 统一展示（界面截图为证）。
  - `rule` TR-13.6: 标红不永久阻断——标红项经人工确认后解除阻断，可保存（操作录屏为证）。
  - `rule` TR-13.7: 门禁解锁——全部条目确认后保存，状态机转入 PARSE_CONFIRMED，商务标/检查模块从置灰变为可用（状态日志+界面截图为证）。
  - `rule` TR-13.8: 配置类功能不受门禁限制——清单未确认时配置页仍可用（界面截图为证）。
  - `rule` TR-13.9: BP-1 Checkpoint——清单确认作为独立 checkpoint 项，中断后重启续跑（中断恢复日志为证）。
  - `rule` TR-13.10: 产物按项目隔离存储，跨项目互不可见（存储路径检查+隔离测试为证）。
- **Notes**:
  - Task 13 是 Phase 1.1 收尾 Task，整合 Task 8-12 产物。
  - 商务标阶段的人工增删/地址链接回填属 Phase 1.2（spec FR-3 第 1 点）。
  - 状态机复用 PARSE_REVIEW→PARSE_CONFIRMED，不新增状态。
  - 样本已就绪（含完整解析产物的招标文件）。

## 阶段 1.2：商务标生成（概要，进入前细化）
> **借鉴点参考**（详见 [yibiao-borrowing.md](file:///e:/bidcraft/bidcraft-master/docs/references/yibiao-borrowing.md)）：
> - BP-1 长任务 Checkpoint（高）：逐章渲染等长任务断点续跑。
> - BP-2 导出占位+警告清单（高）：渲染输出时不静默，缺失项占位+清单披露。
> - BP-3 Schema 硬校验（高）：模板比对等阶段交接门禁。
> - BP-4 确定性与语义分工（高）：模板比对机械检查 vs 语义判断分工。
> - BP-5 渲染计划（中）：渲染前生成结构化填充计划，用户确认后执行。
> - BP-6 图片闭环（中）：占位→匹配→缩放→不跨页→缺失披露全链路。
> - BP-7 一致性审计（中）：渲染后规则库扫描术语/信息一致性。
> - BP-8 FTS5 检索（中）：素材库查询用 SQLite FTS5 全文检索。
> - BP-9 三级素材管理+历史复用（低）：素材三级组织+历史清单复用。
> 进入本阶段细化时，将上述借鉴点拆解为对应 Task 的 TR。

- Task 15: 素材库管理（层级/命名规范、动态词典、归档、版本快照）
- Task 16: 素材提取清单（查询匹配、2-3 轮循环收敛）
- Task 17: 模板库管理（目录组织、模板编辑器、template.json、版本）
- Task 18: 模板匹配（≥90%）与语义比对（文件关联表、差异确认）
- Task 19: docxtpl 逐章渲染（文字/图片占位、缩放、不跨页）
- Task 20: 转 PDF、文档合并、图片压缩
- Task 21: 回收站完整功能与 30 天清理配置

## 问题（Review 修复项）
- （暂无，仅在独立评审产生 actionable 发现后，按 Issue I-N 登记）
