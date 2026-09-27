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
│   │   │   ├── parser_pdf.py    # PyMuPDF
│   │   │   ├── parser_docx.py   # python-docx
│   │   │   ├── ocr.py           # PaddleOCR
│   │   │   ├── llm.py           # LiteLLM 网关
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
| `material` | id, enterprise_id, category, name, file_path, ocr_text, valid_until, version, status | 素材（企业级） |
| `material_extract_list` | id, project_id, round, content_json, confirmed_at | 素材提取清单（多轮） |
| `template` | id, enterprise_id, agency, doc_type, path, version, meta_json, status | 模板（企业级） |
| `template_compare` | id, project_id, findings_json, confirmed_at | 比对结果 |
| `generated_doc` | id, project_id, chapter, file_path, source_template_version, status | 生成文件+版本快照 |
| `llm_call_log` | id, project_id, model, tokens_in/out, duration_ms, cost, created_at | EM-4 成本可观测 |
| `config_kv` | scope(system/enterprise), enterprise_id?, key, value | 配置（企业优先） |
| `recycle_bin` | id, item_type, enterprise_id?, ref_id, deleted_at, purge_at | 回收站（30 天可配） |
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
│               ├── source/         # 原招标文件
│               ├── parsed/         # 解析格式章节 docx（投标文件格式）
│               ├── project-materials/   # 项目独享资料库（社保等）
│               ├── template-work/  # 提取到项目内的模板
│               ├── output/         # 逐章生成 Word
│               ├── pdf/            # 转换结果
│               └── lists/          # 素材提取清单等成果
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
  → PARSE_REVIEW(待人工确认清单)
  → PARSE_CONFIRMED(清单已确认，解锁业务模块)
  → MATERIAL_LOOP(素材提取循环)
  → TEMPLATE_MATCHED(模板已匹配)
  → TEMPLATE_REVIEW(差异待确认)
  → READY_TO_RENDER(全部确认)
  → RENDERING(逐章生成)
  → RENDERED(已生成)
  → CHECKED(已检查，二期)
```
门禁：PARSE_CONFIRMED 之前其他业务模块 UI 置灰（FR-2）。

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
3. 同时产出 score_table.json 与 parsed/ 章节 docx；
4. 状态 → PARSE_CONFIRMED，解锁模块。

### 7.2 商务标制作
1. 素材：`/material/query` → 可编辑查询清单 → 用户补充素材库 → 循环 2-3 轮 → 保存提取清单；
2. 模板：`/template/match`（≥90% 或人工指定）→ 提取模板到项目；
3. 比对：`/template/compare`（文件关联表 + finding）→ 差异列表（含投标函直接更新项）→ 人工逐一确认；
4. 渲染：`/render/bid`（docxtpl；文字/图片占位；图片等比缩放、不跨页）→ 逐章 Word；
5. 可选：转 PDF、合并。报价类文件按 EXTERNAL/缺失披露，不阻断。

## 八、安全边界汇总

- Renderer 零系统权限，仅白名单 IPC；
- Python 仅 127.0.0.1 + 随机端口 + 本地令牌；
- API Key 仅 DPAPI；日志脱敏；
- 文件操作经路径校验，禁止逃逸数据根目录；
- 模型外联遵循 NFR-3（首次提示）。
