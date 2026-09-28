# 架构设计文档（architecture.md）

> 项目：AI标书制作 ｜ 日期：2026-09-28 ｜ 状态：待用户确认
> 配套：[spec.md](file:///e:/bidcraft/bidcraft-master/.trae/specs/ai-bid-making/spec.md) ｜ [tech-selection.md](file:///e:/bidcraft/bidcraft-master/docs/architecture/tech-selection.md)
> 范围：一期（阶段 1.0→1.2）；为后续阶段预留扩展点。

## 一、进程模型与职责

| 进程 | 技术 | 职责 | 不可做 |
|---|---|---|---|
| Renderer | React+TS（Chromium） | 全部 UI、用户交互、XState 状态呈现、清单编辑与确认 | 不直接访问文件系统/网络/Python |
| Main | Node.js（Electron 主进程） | 窗口生命周期、IPC 白名单、文件对话框、sidecar 进程管理与健康检查、DPAPI 调用、自动更新 | 不含业务逻辑与文档处理 |
| Python Sidecar | FastAPI + uvicorn | PDF/Word/OCR 解析、规则库、LLM 网关、docxtpl 渲染、比对、转 PDF/合并 | 仅监听 127.0.0.1；不主动外联模型以外地址 |

进程生命周期：应用启动 → Main 初始化 → 拉起 Python（随机端口 + 令牌鉴权 + 健康检查）→ 渲染窗口；应用退出 → Main 优雅关闭 Python。Python 崩溃 → 状态机标异常、UI 提示重启该环节，不静默。

## 二、通信设计

### 2.1 Renderer ↔ Main：IPC 通道（contextBridge 白名单）

暴露为 `window.bid.*`，按域分组：

| IPC 通道 | 方向 | 用途 |
|---|---|---|
| `dialog:openFile/openFiles/saveFile` | R→M | 原生文件选择（限定扩展名） |
| `app:getVersion/getPath` | R→M | 版本、数据目录 |
| `sidecar:health` | R→M | 查询 Python 健康状态 |
| `sidecar:call(route, payload)` | R→M | 统一转发到 Python HTTP（带令牌） |
| `sidecar:stream(route, payload)` | R→M | 转发并订阅 SSE 进度（回调 onProgress） |
| `task:cancel(taskId)` | R→M | 取消异步任务（NFR-2） |
| `cred:setApiKey/getApiKey` | R→M | 经 keyring/DPAPI 读写（NFR-3） |
| `shell:openPath/openExternal` | R→M | 打开文件/文件夹/链接（校验白名单） |

安全：contextIsolation 开启、nodeIntegration 关闭；所有通道参数做类型与路径校验。

### 2.2 Main ↔ Python：HTTP API（REST + SSE）

统一前缀 `/api/v1`；除健康检查外需 `Authorization: Bearer <本地令牌>`。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 健康检查 |
| POST | `/parse/document` | 上传招标文件，启动解析（SSE 返回进度） |
| GET | `/parse/{task_id}` | 获取解析结果（清单、章节、锚点） |
| POST | `/parse/confirm` | 保存人工确认后的清单 |
| POST | `/score/extract` | 解析评分办法 → score_table.json |
| POST | `/material/query` | 素材库查询（指定/语义匹配） |
| POST | `/material/archive` | 归档素材（OCR + 命名解析） |
| POST | `/template/match` | 模板匹配（相似度） |
| POST | `/template/compare` | 模板与解析格式比对（finding 列表） |
| POST | `/render/bid` | docxtpl 逐章生成（SSE 进度） |
| POST | `/convert/pdf` | Word 转 PDF |
| POST | `/merge` | 合并文档 |
| GET | `/config/{scope}` | 系统级/企业级配置（企业优先） |
| PUT | `/config/{scope}` | 写配置 |

SSE 事件统一：`{stage, percent, message, extra?}`；终态 `completed`/`failed`/`cancelled`。

#### Task 8 已落地路由（招标文件解析 v1）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/parse/engine` | MinerU/LibreOffice 引擎探针（版本、CUDA、可用性） |
| POST | `/enterprises/{eid}/projects/{pid}/parse/sources` | 登记本机源文件（绝对路径，sidecar 同机复制入库） |
| POST | `.../parse/start` | 启动解析/断点续跑（SSE；响应头 `X-Task-Id`；body `{reparse?: bool}`） |
| GET | `.../parse/status` | 状态机 + checkpoint + sources/dedupe/chapters 汇总 |
| POST | `.../parse/retry` | 单项重试（body `{item: key|null}`，null=续跑未完成项） |
| POST | `/tasks/{task_id}/cancel` | 取消运行中任务（复用通用任务取消通道） |

实现说明：Main 进程在 SSE body 到达前先下发一条 IPC 元事件（`stage:'meta'`，`extra.taskId`）供渲染端取消；该事件不来自后端、不入库。

## 三、代码目录结构（仓库）

```
bidcraft-master/
├── package.json                 # electron-vite 工作区根
├── electron.vite.config.ts
├── src/                         # Renderer（React）
│   ├── main.tsx
│   ├── App.tsx
│   ├── layouts/                 # 左侧导航+主工作区、主题
│   ├── pages/
│   │   ├── enterprise/          # 企业/项目管理
│   │   ├── parse/               # 招标文件解析+清单确认
│   │   ├── bid/                 # 商务标制作
│   │   ├── check/               # 标书检查（二期启用）
│   │   └── settings/            # 模型/系统/企业配置
│   ├── features/                # 业务组件（按模块）
│   ├── components/              # 通用组件（统一确认 UI、finding 列表）
│   ├── machines/                # XState 状态机（EM-5）
│   ├── stores/                  # Zustand
│   ├── api/                     # window.bid 封装
│   ├── types/
│   └── styles/                  # Tailwind、主题变量
├── electron/                    # Main 进程
│   ├── main.ts
│   ├── preload.ts
│   ├── ipc/                     # IPC 处理器（白名单）
│   ├── sidecar.ts               # Python 进程管理
│   └── cred.ts                  # DPAPI/keyring
├── sidecar/                     # Python FastAPI
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py
│   │   ├── api/                 # 路由（parse/material/template/render/...）
│   │   ├── services/            # 业务逻辑
│   │   │   ├── mineru_client.py # MinerU 解析引擎（PDF/Word/扫描件/OCR 一体化）
│   │   │   ├── parser_docx.py   # python-docx（模板比对用）
│   │   │   ├── llm.py           # LiteLLM 网关（可选，默认关）
│   │   │   ├── rules/           # 规则库（EM-3，可单测）
│   │   │   ├── render.py        # docxtpl
│   │   │   ├── compare.py       # 语义比对
│   │   │   └── convert.py       # 转PDF/合并
│   │   ├── models/              # SQLAlchemy 模型
│   │   ├── schemas/             # Pydantic
│   │   └── core/                # 配置、安全、日志
│   └── tests/                   # pytest + 黄金样本（EM-1）
├── docs/                        # 文档（architecture/conversations）
└── samples/                     # 样本（gitignore 大文件；用户按指示放入）
```

## 四、SQLite 数据模型（核心表）

> 文件内容存文件系统；数据库存索引、关系、状态、元数据。

| 表 | 关键字段 | 说明 |
|---|---|---|
| `enterprise` | id, name, legal_person, agent(必填), contact, phone, intro, status, deleted_at | 企业；软删除 |
| `project` | id, enterprise_id(FK), name, code, agent(选填), status, deleted_at | 项目；隔离边界 |
| `parse_task` | id, project_id, file_path, mode(默认/高精度), status, result_json, confirmed_at | 解析任务 |
| `parse_item` | id, parse_task_id, category, content, anchor_page, anchor_coord, source_snippet, risk, status(逐条确认) | 解析清单条目 |
| `score_table` | id, project_id, version, structure_json | 评分表（EM 复用） |
| `material` | id, enterprise_id, project_id?(项目独享), category, name, file_path, ocr_text, valid_until, version, status, deleted_at | 素材（企业共享/项目独享）；FTS5 虚表索引 name + ocr_text（BP-8） |
| `material_extract_list` | id, project_id, round, content_json, confirmed_at | 素材提取清单（多轮） |
| `template` | id, enterprise_id, agency, doc_type, path, version, meta_json, status, deleted_at | 模板（企业级；同目录 vX.Y 版本子文件夹） |
| `template_compare` | id, project_id, findings_json, confirmed_at | 比对结果 |
| `generated_doc` | id, project_id, chapter, file_path, source_template_version, status | 生成文件+版本快照 |
| `llm_call_log` | id, project_id, model, tokens_in/out, duration_ms, cost, created_at | EM-4 成本可观测 |
| `config_kv` | scope(system/enterprise), enterprise_id?, key, value | 配置（企业优先） |
| `recycle_bin` | id, item_type, enterprise_id?, ref_id, deleted_at, purge_at | 两级回收站（项目/素材/模板均入企业内回收站；保留时长可配，默认 30 天） |
| `app_event` | id, project_id?, type, payload, created_at | 状态转换/审计留痕 |

隔离强制方式：所有业务查询默认带 `enterprise_id` / `project_id` 约束（仓储层统一注入 + 测试覆盖），杜绝跨企业/跨项目读取。

## 五、文件系统目录规划（用户数据根目录）

```
<BidCraftData>/                     # 默认 %APPDATA%/BidCraft，可在系统配置改
├── config/
│   ├── system.json                 # 系统级配置
│   └── keywords.dict.json          # 动态关键字词典
├── enterprises/
│   └── <enterprise_id>/
│       ├── enterprise.json
│       ├── materials/              # 共享素材库（FR-4 层级结构）
│       │   ├── 资质/
│       │   ├── 人员/<姓名>/...
│       │   ├── 业绩/<项目全名_日期_总监>/...
│       │   ├── 荣誉/
│       │   └── 财务/
│       ├── templates/              # 共享模板库（FR-5）
│       │   └── <代理机构>/<招标|采购|询比价>/...（含 template.json）
│       └── projects/
│           └── <project_id>/
│               ├── project.json
│               ├── source/         # 原招标文件（登记时复制入库，safe_filename+重名后缀）
│               ├── sources.json    # 登记清单（含 sha256，Task 8）
│               ├── dedupe.json     # 同名多格式去重决策/丢弃/不一致记录（Task 8）
│               ├── chapters.json   # 章节树（含 page_idx/bbox 锚点 + 目录交叉校验，Task 8）
│               ├── parse/          # 解析产物根目录（Task 8 落地）
│               │   ├── raw/         # MinerU 原始产物（每源一个子目录：<stem>.md + content_list.json + middle.json + images/）
│               │   ├── work/        # LibreOffice 转换的工作 PDF（.doc/.docx 指纹与解析输入）
│               │   ├── checkpoints/ # BP-1 断点文件 document_parse.json（原子写，崩溃 running 回置 idle）
│               │   ├── structured/  # 结构化产物（score_table.json 等，Task 11 落地）
│               │   └── confirmed/  # 人工确认后的最终清单（parse_checklist.json，Task 13 落地）
│               ├── parsed/         # 解析格式章节 docx（投标文件格式，Task 12 落地）
│               ├── project-materials/   # 项目独享资料库（社保等）
│               ├── template-work/  # 提取到项目内的模板
│               ├── output/         # 逐章生成 Word
│               ├── pdf/            # 转换结果（逐章 PDF + 合并 PDF，Task 20）
│               └── lists/          # 格式清单/素材提取清单等成果（format_checklist.json / material_extract.json，Task 14/16）
├── recycle/                        # 系统回收站（企业）
└── logs/                           # 按日期滚动
```

样本路径（开发期）：仓库 `samples/<样本名>/`，由 AI 指定、用户放入；大文件 gitignore。

## 六、状态机（EM-5 落地）

### 6.1 项目级主状态
```
INIT(已建项目)
  → UPLOADED(已传招标文件)
  → PARSING(解析中) ─cancel/失败→ UPLOADED
  → PARSED(解析完成，Task 8 落地)
  → SCORE_PARSED(评分办法解析完成，Task 11 落地)
  → PARSE_REVIEW(待人工确认清单)
  → PARSE_CONFIRMED(清单已确认，解锁业务模块)
  → FORMAT_REVIEW(商务标格式清单待确认，Task 14 落地)
  → FORMAT_CONFIRMED(格式清单已确认，Task 14 落地)
  → MATERIAL_LOOP(素材提取循环，Task 16 落地)
  → MATERIAL_CONFIRMED(素材提取清单已保存，Task 16 落地)
  → TEMPLATE_MATCHED(模板已匹配)
  → TEMPLATE_REVIEW(差异待确认)
  → READY_TO_RENDER(全部确认)
  → RENDERING(逐章生成)
  → RENDERED(已生成)
  → EXPORTED(已转 PDF/合并导出，Task 20 落地；成果不可变)
  → CHECKED(已检查，二期)
```
门禁：PARSE_CONFIRMED 之前其他业务模块 UI 置灰（FR-2）。

> Task 8 落地：前四个状态持久化在 `project.parse_status`（INIT/UPLOADED/PARSING/PARSED）。
> 合法转换：INIT→UPLOADED（登记）、UPLOADED→PARSING、PARSING→PARSED；
> 取消/异常一律 PARSING→UPLOADED（可断点续跑）；PARSING 自环允许崩溃后幂等重入；
> PARSED→UPLOADED/PARSING 允许换文件重解析。每次转换写 `app_event`（type=`parse_state_change`）。

### 6.2 文件级状态（每个章节/素材独立）
`PENDING → PROCESSING → AWAIT_CONFIRM → CONFIRMED → GENERATED`；
旁路状态：`MISSING`（缺失，只披露不阻断）、`EXTERNAL`（系统外）、`ERROR`。

### 6.3 规则
- 每次状态转换写 `app_event`；
- MISSING/ERROR/EXTERNAL 仅披露、不阻断其他环节；
- 冲突（如比对双方不一致）永不自动应用，停留 AWAIT_CONFIRM。

## 七、关键流程时序（一期）

### 7.1 解析流程
1. 用户上传文件 → Main 校验 → Python `/parse/document`（SSE：提取→粗分→LLM校验→摘要审计）；
2. 输出可编辑清单（不一致标红）→ 用户逐条确认/增删 → `/parse/confirm`；
3. 同时产出 `parse/structured/score_table.json`（评分办法结构化，Task 11）与 `parsed/` 章节 docx（Task 12）；
4. 状态 → PARSE_CONFIRMED，解锁模块。

#### 7.1.1 Task 8 已落地流水线（BP-1 Checkpoint 驱动，权重 5/20/25/85/100）

```
dedupe（同名分组，docx>doc>pdf）
  → preprocess:<file>（.doc/.docx 经 LibreOffice 转工作 PDF）
  → dedupe-verify（PDF 文本指纹：页数+归一化文本 sha256，相似度≥0.85 判同；
                   同名异内容不去重，候选改名 -mmN 保留并披露）
  → mineru:<file>（MinerU pipeline -m auto：文字版直提 / 扫描件自动 PP-OCRv6）
  → chapters:<file>（章节树 + 目录交叉校验 + 噪声内部消化）
  → PARSED
```

- Checkpoint 项状态 idle/running/success/error，原子落盘；崩溃后 running 回置 idle，
  重跑只执行未成功项（断点续跑）；单项重试按依赖级联清除下游（如 mineru 重置连带 chapters）。
- MinerU 3.4.5 实测产物布局：`parse/raw/<stem>/<method>/`（method=auto/txt/ocr），
  含 `<stem>.md`、`<stem>_content_list.json`（块带 type/text/text_level/page_idx/bbox）、
  `<stem>_middle.json`、`images/`。
- 噪声容错（TR-8.6）："目 录"类变体目录页识别、表单勾选/冒号尾行误标过滤、
  同页 ≥3 个一级标题的文件构成清单整组丢弃、页眉 3 页窗口去重、章节 end_page 不倒挂；
  被消化数量计入 `stats.heading_noise_dropped`，不打扰用户。
- 真实样本基线（开发机 RTX 3060 Ti）：57 页文字版 154s；97 页纯扫描件（0 文本层）OCR 199s。

### 7.2 商务标制作
1. 格式：PARSE_CONFIRMED 后展示 parsed/ 逐章 docx 清单 → 增删改、新增项识别 → 逐条确认（Task 14）→ FORMAT_CONFIRMED；
2. 素材：`/material/query` → 可编辑查询清单 → 用户补充素材库 → 循环 2-3 轮 → 保存提取清单（Task 16）→ MATERIAL_CONFIRMED；
3. 模板：`/template/match`（≥90% 或人工指定）→ 提取模板到项目（Task 17/18）；
4. 比对：`/template/compare`（文件关联表 + finding）→ 差异列表 → 人工逐一确认；
5. 渲染：`/render/bid`（docxtpl；文字/图片占位；图片等比缩放、不跨页）→ 逐章 Word（Task 19）；
6. 可选：转 PDF、PDF 合并（图片压缩推迟）→ EXPORTED（Task 20）。报价类文件按 EXTERNAL/缺失披露，不阻断。

## 八、安全边界汇总

- Renderer 零系统权限，仅白名单 IPC；
- Python 仅 127.0.0.1 + 随机端口 + 本地令牌；
- API Key 仅 DPAPI；日志脱敏；
- 文件操作经路径校验，禁止逃逸数据根目录；
- 模型外联遵循 NFR-3（首次提示）。

## 九、测试架构（EM-6）

> 详见 [spec.md EM-6](file:///e:/bidcraft/bidcraft-master/.trae/specs/ai-bid-making/spec.md) 测试金字塔与分层测试策略。本节记录架构层面的测试落点。

### 9.1 分层模型

采用 Testing Trophy + Honeycomb 混合模型，集成测试占主体（本项目重 I/O，核心风险在集成）。

| 层级 | 前端（Electron+React） | 后端（Python sidecar） | 比例 |
|---|---|---|---|
| 静态分析 | TypeScript + ESLint | mypy + ruff | 必选地基 |
| 单元测试 | Vitest（纯函数、hooks、Zustand、XState 转换） | pytest（规则库、命名解析、隔离过滤） | ~30% |
| 集成测试 | RTL + Vitest Browser Mode（组件交互、清单编辑） | pytest + FastAPI TestClient（MinerU 解析、docxtpl 渲染、SQLite 仓储） | ~50%（焦点） |
| E2E | Playwright（主线流程：建企业→建项目→上传→解析→确认→素材→模板→渲染） | — | ~20% |

### 9.2 专项测试落点

| 专项 | 测试位置 | 关键点 |
|---|---|---|
| 黄金样本回归（EM-1） | `sidecar/tests/golden/` | 真实招标文件解析结果固化为期望输出，MinerU 升级/规则变更重跑 |
| 数据隔离专项 | `sidecar/tests/test_isolation.py` | 构造越权访问用例，断言仓储层 `enterprise_id`/`project_id` 过滤生效 |
| 确定性回归（商务标） | `sidecar/tests/test_render_regression.py` | 固定输入→固定输出，生成的 Word 与期望文档比对 |
| 状态机测试 | `src/machines/__tests__/` | XState 合法/非法转换 + 断点恢复 |
| LLM 模式测试 | `sidecar/tests/test_llm_modes.py` | 默认关断言 + mock 校验/双通道，测试原文锚定拦截幻觉 |
| 真实引擎端到端（Task 8） | `sidecar/tests/engine/`（marker `engine`；扫描件另标 `slow`） | 真实 MinerU 3.4.5 + LibreOffice + `samples/` 样本：TR-8.1 文字版 bbox/章节、TR-8.2 扫描件 OCR、TR-8.3 .doc 转换、TR-8.5 合成夹具指纹；无 `.venv-mineru` 自动 skip，CI 不装 |

### 9.3 CI 分层触发

| 触发事件 | 静态 | 单元 | 集成 | E2E | 黄金样本 |
|---|---|---|---|---|---|
| 推送 feature/fix | ✅ | ✅ | ✅ | ❌ | ❌ |
| 创建/更新 PR | ✅ | ✅ | ✅ | ✅ | ✅ |
| 推送 main | ✅ | ✅ | ✅ | ✅ | ✅ |
| 打 v* 标签 | ✅ | ✅ | ✅ | ✅ | ✅+构建 |

### 9.4 目录结构补充

```
src/__tests__/              # 前端单元测试（Vitest）
src/machines/__tests__/     # 状态机测试
sidecar/tests/
├── unit/                   # 纯单元（checkpoint/状态机/去重/章节/路径/引擎产物定位）
├── integration/            # FastAPI TestClient（API/SSE/取消/续跑/隔离；MinerU 全部 fake）
├── engine/                 # 真实引擎端到端（marker: engine/slow，本机手工跑，CI skip）
├── golden/                 # 黄金样本（EM-1）
├── test_isolation.py       # 数据隔离专项
├── test_render_regression.py  # 商务标确定性回归
└── test_llm_modes.py       # LLM 模式测试
e2e/                        # Playwright E2E
```

测试基础设施（Vitest + pytest 配置、CI 分层 job、示例测试）在 Task 1 搭建。

## 十、dev/prod 环境隔离

> 2026-09-28 确认。Electron 默认 dev/prod 共享 userData 路径，会互相污染数据（开发测试数据混入生产标书，或生产标书被调试破坏）。对本案（标书数据是核心资产，规则 7 数据完整性）是灾难性的，必须在 Task 1 就处理。

### 10.1 环境检测

electron-vite 在开发模式下注入 `ELECTRON_RENDERER_URL`（electron-vite v5 实测；比 `NODE_ENV` 可靠）：

```typescript
// electron/main.ts（必须在 app.whenReady() 之前调用）
const isDev = !!process.env.ELECTRON_RENDERER_URL;
app.setName(isDev ? 'BidCraft-dev' : 'BidCraftApp');
// app.getPath('userData') 自动返回:
//   dev  → %AppData%\BidCraft-dev
//   prod → %AppData%\BidCraftApp
```

生产环境目录名不用 `BidCraft`（与仓库上层目录 `e:\bidcraft` 同名易混淆）。

### 10.2 数据根目录传给 sidecar

```typescript
// electron/sidecar.ts
const dataRoot = app.getPath('userData');
// 未打包运行：直接启动 .venv 内的 uvicorn（不经 shell/cmd，child.pid 即真实进程，
//   进程树可整树结束，避免 cmd 先退导致 uv/python 孤儿）；
// 打包后：PyInstaller exe，--data-root 供 argparse 使用
const runner = isDev
  ? join(sidecarDir, '.venv', 'Scripts', 'uvicorn.exe')
  : sidecarExePath;
const child = spawn(runner, isDev
  ? ['app.main:app', '--host', '127.0.0.1', '--port', String(port)]
  : ['--data-root', dataRoot], {
  cwd: isDev ? sidecarDir : undefined,
  env: {
    ...process.env,
    BIDCRAFT_DATA_ROOT: dataRoot,      // 环境变量兜底（uvicorn CLI 不接受 --data-root）
    BIDCRAFT_SIDECAR_TOKEN: token,     // 本地令牌鉴权
  },
});
// 退出：before-quit 中 preventDefault，await stopSidecar()（Windows 经
// taskkill /T /F 并等待结束）后再 app.quit()
```

### 10.3 Sidecar 接收数据根目录

```python
# sidecar/app/core/config.py
import os
from pathlib import Path
DATA_ROOT = Path(args.data_root or os.environ.get('BIDCRAFT_DATA_ROOT'))
DB_PATH = DATA_ROOT / 'bidcraft.db'
CONFIG_DIR = DATA_ROOT / 'config'
LOG_DIR = DATA_ROOT / 'logs'
```

### 10.4 API Key 隔离

```typescript
// electron/cred.ts
const service = isDev ? 'BidCraft-dev' : 'BidCraftApp';
// keytar 按(service, account)存储，dev/prod 自然隔离
await keytar.setPassword(service, 'llm-api-key', encryptedKey);
```

### 10.5 目录结构对比

```
%AppData%/
├── BidCraft-dev/              ← 开发环境
│   ├── config/
│   │   ├── system.json
│   │   └── keywords.dict.json
│   ├── enterprises/
│   │   └── <enterprise_id>/...
│   ├── bidcraft.db
│   └── logs/
│
└── BidCraftApp/               ← 生产环境
    ├── config/
    ├── enterprises/
    ├── bidcraft.db
    └── logs/
```

样本文件（`samples/`、`samples-local/`）在仓库内，是只读输入，不涉及 userData，不与 dev/prod 数据冲突。

### 10.6 开发环境重置脚本

```json
// package.json scripts
{
  "reset:dev": "node scripts/reset-dev.js"
}
```

删除 `%AppData%\BidCraft-dev\`，清空开发数据，用于开发迭代时从头来过。

### 10.7 CI 测试环境

GitHub Actions runner 用临时路径（如 `%RUNNER_TEMP%\BidCraft-test`），不与 dev/prod 冲突。CI 中通过环境变量 `BIDCRAFT_DATA_ROOT` 指定。

### 10.8 MinerU 独立解释器环境（Task 8）

MinerU 3.4.5 依赖体量大（torch CUDA、paddleocr 系模型库），与主 sidecar 依赖（FastAPI/pypdf/uv.lock）
**物理隔离**：独立虚拟环境 `sidecar/.venv-mineru/`（已入 .gitignore，不进 uv.lock、不进 CI），
sidecar 以子进程方式调用其 CLI：

```
mineru -p <input> -o <out> -b pipeline -m auto -l ch
```

- 解释器发现：环境变量 `BIDCRAFT_MINERU_PYTHON` → 开发期默认 `sidecar/.venv-mineru/Scripts/python.exe`；
- LibreOffice（.doc 转换）发现：`BIDCRAFT_SOFFICE` → PATH → Windows 默认安装路径；
- 版本不符（主版本 ≠3）/未安装 → `GET /parse/engine` 返回 available=false 并带原因，前端禁用启动，不静默降级；
- 已知环境补丁：3.4.5 遗漏依赖 `six`（pytorch_paddle OCR 链 import），装机后需
  `uv pip install --python .venv-mineru/Scripts/python.exe six`；
  torch 用 cu128 CUDA 轮（torch 2.11.0+cu128，RTX 3060 Ti 实测可用）；
- pipeline 模型首次解析时自动下载（或 `mineru-models-download modelscope/pipeline` 预下），
  缓存于用户模型目录，不属仓库资产；
- MinerU 许可证为自定义条款（非标准 SPDX），分发前需法务复核（见会话记录披露项）。

## 十一、发布与自动更新

> 需求详见 [spec.md NFR-7](file:///e:/bidcraft/bidcraft-master/.trae/specs/ai-bid-making/spec.md)。本节记录架构层面的落点。

### 11.1 自动更新架构

```
GitHub Releases (latest.yml + NSIS.exe + .blockmap)
        ↑                                    ↓
  CI 构建(tag 触发)                    客户端启动轮询
                                        ↓
                              electron-updater 比对版本
                                        ↓
                              差异下载(blockmap) → quitAndInstall
```

- **electron-updater 集成**：Main 进程 `autoUpdater.setFeedURL({ provider: 'github', owner: 'chenjiancy', repo: 'bidcraft' })`；`autoUpdater.checkForUpdatesAndNotify()`。
- **Python sidecar 更新**：通过 `extraResources` 打入 NSIS，随主包整体替换，不做独立差分。版本号与 Electron 绑定。
- **更新选项**：`autoDownload: false`（手动确认）或 `true`（自动下载）；`oneClick: true`（NSIS 静默安装）。

### 11.2 CI/CD 发布工作流

```yaml
# .github/workflows/release.yml（Task 1 产出 ci.yml 后补充）
on:
  push:
    tags: ['v*']
jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - # npm ci + uv sync
      - # npm run build
      - run: npx electron-builder --publish always
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### 11.3 生产→开发反馈闭环

```
生产环境问题
    ↓
electron-log 本地日志 + 应用内"报告问题"按钮
    ↓
GitHub Issue（附带日志/系统信息）
    ↓
feature 分支修复 → PR → 合并
    ↓
tag v* → CI 出包 → GitHub Releases
    ↓
electron-updater 推送到生产 → 验证复现
```

- **当前阶段**：electron-log（NFR-6）+ GitHub Issues 手动闭环。
- **分发阶段**：引入 `@sentry/electron`（main + renderer 初始化），自动捕获 JS 异常 + 原生 Minidump 崩溃。

### 11.4 分阶段实施

| 阶段 | 实施项 |
|---|---|
| Task 1 | dev/prod userData 隔离（第十章）+ electron-updater 依赖安装 |
| 阶段 1.0 验收后 | release.yml 工作流 + `electron-builder --publish always` |
| 实际使用阶段 | 启用 `checkForUpdatesAndNotify` + 应用内"报告问题"按钮 |
| 分发阶段 | Sentry 集成 |
