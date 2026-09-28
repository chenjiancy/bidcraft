# 技术选型报告（tech-selection.md）

> 项目：AI标书制作 ｜ 日期：2026-09-28 ｜ 状态：**已确认（2026-09-28 用户拍板）**
> 决策：方案 A（Electron + React + TS + Python sidecar）｜ UI 组件库 Ant Design 5 ｜ 文档解析引擎 MinerU（内置 OCR）
> 依据：spec.md 已确认需求（一期"解析→商务标"主线、Windows 桌面端、NFR-1～6）+ 联网调研 2026 年主流技术栈。

## 一、选型约束（来自需求）

| 约束 | 来源 |
|---|---|
| Windows 10/11 桌面端，UI 漂亮、明暗双主题 | NFR-1、NFR-4 |
| PDF / Word / 扫描件（OCR）解析 | FR-2 |
| docx 模板渲染：文字占位 + **图片占位**（大量） | FR-3、FR-5 |
| Word 转 PDF、文档合并 | FR-3 |
| 本地两级数据模型（企业-项目）+ 素材/模板结构化 | FR-1、FR-4、FR-5 |
| API Key DPAPI 加密、异步任务、中断恢复 | NFR-2/3/5 |
| 个人单机开发，参考易标（Electron+React） | 背景 |

## 二、候选方案对比

### 方案 A：Electron + React + TypeScript + Python Sidecar（推荐 ⭐）
- Electron 承载 UI（React + TS）；Python 以本地 sidecar 进程（FastAPI/本地 HTTP）承担全部文档智能处理。
- 与易标架构一致，UI 与功能布局参考可直接迁移。

### 方案 B：Tauri 2 + React + Python Sidecar
- Tauri（Rust 后端）替代 Electron，包体 2-10MB；仍需 Python sidecar 处理文档。

### 方案 C：纯 Python（PySide6 + QML）
- 单语言，文档处理生态最强；但 UI 生态与易标参考差异大。

### 方案 D：Electron + 纯 Node/TS
- docxtemplater 渲染；**图片模块商业付费**，且 OCR/文档处理库不如 Python。

| 维度 | A（推荐） | B | C | D |
|---|---|---|---|---|
| UI 漂亮/易标参考 | ★★★ | ★★★ | ★★ | ★★★ |
| docx 图片占位 | ★★★ docxtpl 免费 | ★★★ | ★★★ | ★ 付费 |
| PDF/OCR 生态 | ★★★ | ★★★ | ★★★ | ★★ |
| 个人开发复杂度 | ★★（JS+Python，无 Rust） | ★（Rust+Python 双重） | ★★★ 单语言 | ★★ |
| 安装包体积 | ★（100-200MB） | ★★★（含 Python 约 30-50MB） | ★★ | ★ |
| 跨平台预留 | ★★★ | ★★★ | ★★ | ★★★ |
| 成熟度/资料 | ★★★ | ★★ | ★★ | ★★★ |

**结论：推荐方案 A。** 包体大对个人单机使用无实质影响；避免 Rust 学习成本；与易标参考路径一致；Python 侧文档能力最强且全开源。方案 B 的包体优势在本机使用场景下不构成决策理由。

## 三、推荐技术栈明细（方案 A）

### 3.1 前端 / 桌面壳
| 用途 | 选型 | 说明 |
|---|---|---|
| 桌面框架 | Electron（最新稳定版，开发时锁定） | 成熟、Chromium 渲染一致 |
| UI 框架 | React 18+ + TypeScript | 易标同栈 |
| 构建工具 | Vite + electron-vite | 快速 HMR |
| UI 组件库 | Ant Design 5（或 Arco Design，开发时二选一） | 内置明暗主题、桌面后台类组件全 |
| 状态管理 | Zustand | 轻量；配合状态机 |
| 客户端状态机 | XState | 对应 EM-5 |
| 样式 | Tailwind CSS + CSS Variables（主题切换） | |
| 路由 | React Router（Hash 模式） | |

### 3.2 Python Sidecar（文档智能核心）
| 用途 | 选型 | 说明 |
|---|---|---|
| 进程形态 | FastAPI + uvicorn（本地 127.0.0.1，随机端口） | 易标同思路；Electron 启动时拉起、退出时关闭 |
| Word 模板渲染 | **docxtpl + python-docx** | Jinja2 语法（spec FR-5 已预留）；InlineImage 免费 |
| PDF/Word/扫描件 解析引擎 | **MinerU**（Apache 2.0 自定义许可） | 一体化引擎：文字版 PDF 文本提取 + 扫描件 OCR（PP-OCRv6）+ 原生 DOCX 解析（3.0+）+ 输出 Markdown + JSON（带页码坐标和 bbox，满足原文锚定）。本机 GPU 3060Ti 8G 加速；提供 mineru-api 异步任务接口，与 sidecar 架构契合 |
| Word 格式解析（模板比对用） | python-docx（文字+表格结构） | 用于模板比对 |
| OCR（素材归档用） | MinerU 内置 OCR 或独立 PaddleOCR | 素材归档时识别证书文字；开发时验证是否复用 MinerU 还是独立 OCR |
| LLM 接入（可选，解析阶段辅助） | LiteLLM（统一 100+ 云端模型接口） | 配合本地模型（Ollama，OpenAI 兼容接口）；**默认关，用户按需开启**（见 FR-2/FR-4） |
| Word 转 PDF | LibreOffice headless（soffice）或调用本机 Word（docx2pdf） | 开发时验证可用性与保真度 |
| 文档合并 | PyMuPDF（PDF 合并）；docx 合并用 docxcompose | |
| 图片处理 | Pillow（缩放、压缩、格式转换） | 等比 contain 适配 |
| 凭据加密 | keyring（DPAPI 后端） | NFR-3 |

### 3.3 数据存储
| 用途 | 选型 | 说明 |
|---|---|---|
| 结构化数据 | SQLite + SQLAlchemy 2（Alembic 迁移） | 企业/项目/清单/状态/调用日志 |
| 文件存储 | 本地文件系统（规范化目录） | 素材库、模板库、项目文件 |
| 检索加速 | 文件命名规范 + SQLite 索引；语义检索后评估（sqlite-vec / Chroma） | EM-3 规则库为主 |
| 设置 | JSON 配置文件（系统级/企业级，企业优先） | FR-1 第 5 点 |

### 3.4 工程与质量
| 用途 | 选型 |
|---|---|
| Python 打包分发 | PyInstaller（sidecar 单目录/单文件，内置运行时，用户免装 Python） |
| 安装包 | electron-builder（NSIS，Windows） |
| 测试 | pytest（Python）+ Vitest/Playwright（前端）；黄金样本回归（EM-1） |
| 日志 | Python loguru + 前端 electron-log；按日期滚动、脱敏 |
| CI/CD | GitHub Actions（本机全绿后推送触发，规则 9） |

## 四、目标架构（逻辑分层）

```
┌────────────────────────── Electron 应用 ──────────────────────────┐
│  Renderer（React + TS）                                           │
│  左侧导航 + 主工作区：企业/项目 │ 解析 │ 商务标 │ 检查 │ 配置      │
│  XState（EM-5 状态机）· Zustand · 统一确认 UI（EM-2）             │
└───────────────▲───────────────────────────┬───────────────────────┘
                │ IPC（contextBridge）      │
┌───────────────┴───────────────────────────▼───────────────────────┐
│  Main Process（Node）                                             │
│  窗口/生命周期 · sidecar 进程管理 · 文件对话框 · 自动更新          │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ HTTP（127.0.0.1）
┌───────────────────────────────▼───────────────────────────────────┐
│  Python Sidecar（FastAPI）                                         │
│  解析服务（PDF/Word/OCR）│ 清单引擎 │ docxtpl 渲染 │ 比对引擎      │
│  LLM 网关（LiteLLM）│ 规则库（EM-3）│ 转PDF/合并 │ keyring(DPAPI) │
└───────┬───────────────────────────────────────────────┬───────────┘
        │                                               │
┌───────▼────────┐                            ┌─────────▼──────────┐
│ SQLite         │                            │ 文件系统            │
│ 企业/项目/清单  │                            │ 素材库/模板库/项目   │
│ 状态/日志       │                            │ （规范目录）        │
└────────────────┘                            └────────────────────┘
```

## 五、关键技术风险与对策

| # | 风险 | 对策 |
|---|---|---|
| R1 | 本机 Python 已损坏 | 开发用独立 venv/嵌入版 Python；最终用 PyInstaller，用户环境不依赖本机 Python |
| R2 | Word→PDF 保真度（排版偏移） | 优先验证 LibreOffice/本机 Word 两条路径；以真实样本比对，差异披露 |
| R3 | OCR 准确率（手写签名、印章遮挡） | 仅作 B 类辅助 + 人工核对；关键字段靠命名规范与直接录入；MinerU PP-OCRv6 内置 |
| R4 | sidecar 端口占用/启动失败 | 随机端口 + 健康检查；启动失败明确报错、不静默 |
| R5 | LLM 幻觉 | **默认不启用 LLM**（纯确定性管线）；用户开启时走原文锚定校验（找不到原文标红） |
| R6 | Electron 包体 + Python 运行时 + MinerU 模型过大 | PyInstaller 精简依赖；素材样本不打入安装包；MinerU 模型首次运行下载缓存 |
| R7 | IPC/HTTP 边界安全 | sidecar 仅监听 127.0.0.1；contextBridge 最小暴露 |
| R8 | MinerU 版本迭代 breaking change | 本期锁定具体版本；升级前回归测试 |

## 六、已决策项（2026-09-28 用户拍板）

1. ✅ 总体方案采纳 **A（Electron + React + TS + Python sidecar）**——已落盘 spec.md/架构/tasks.md。
2. ✅ UI 组件库选定 **Ant Design 5**——已写入 spec.md 约束与 tasks.md Task 1。
3. ⏳ MinerU 版本锁定：决策已确认为"开发时确定（3.x 稳定版 vs 4.0 新版）"——记入 spec.md 待解决问题 TS-2，开发 Task 8 前定版。
4. ✅ 后续路径：已输出架构设计文档（architecture.md，含第十/十一章 dev/prod 隔离 + 发布更新）并填充 tasks.md（Task 1-7 + 1.1/1.2 概要）。
