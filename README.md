# AI标书制作（BidCraft）

> **本项目仅针对开发者个人业务场景开发，不是通用版本，也不以对外分发为目标。**

AI 标书制作是一款用 AI 辅助生成招投标文件的 Windows 桌面工具，当前主要聚焦**监理标书**制作，核心目标是"**不废标**"。

> `samples/` 目录下的开发测试用例（招标文件样本）均来自公网公开资料，仅用于开发与测试。

## 功能范围

| 阶段 | 内容 | 状态 |
|---|---|---|
| 1.0 | 工程地基：Electron + Python sidecar 架构、企业/项目管理、模型配置、Walking Skeleton | ✅ 已完成 |
| 1.1 | 招标文件解析：MinerU 解析（PDF/Word/扫描件 OCR）、章节切分、评分表结构化、解析清单人工确认 | 📋 已细化，待编码 |
| 1.2 | 商务标生成：格式清单确认、素材库与素材提取、模板库与匹配比对、docxtpl 逐章渲染、转 PDF/合并、回收站 | 📋 已细化，待编码 |
| 二期 | 技术标（监理大纲/服务方案）生成、标书检查 | 不在本期 |

主流程：

```
招标文件上传 → 解析（MinerU/OCR）→ 解析清单人工确认
  → 商务标格式清单确认 → 素材提取循环 → 模板匹配与差异确认
  → 逐章渲染 Word → 转 PDF / PDF 合并导出
```

设计原则：解析与生成各环节均需**人工兜底确认**；缺失项以占位文本 + 警告清单披露，不静默、不阻断；生成路径不调用 LLM；企业—项目两级数据隔离。

## 技术栈

- **桌面壳 / 前端**：Electron、React 18、TypeScript、Ant Design 5、Tailwind CSS、Zustand、React Router（Hash 模式）
- **Python Sidecar**：FastAPI + uvicorn（仅监听 127.0.0.1，Electron 主进程拉起/关闭）
- **文档处理**：MinerU（PDF/Word/扫描件解析与 OCR）、docxtpl + python-docx（Word 模板渲染）、PyMuPDF（PDF 合并）、LibreOffice headless（.doc 预处理与转 PDF）、Pillow（图片处理）
- **存储**：SQLite + SQLAlchemy 2 + Alembic 迁移；文件存本地文件系统
- **质量与工程**：pytest、Vitest、Playwright、ruff、mypy、ESLint、electron-vite、electron-builder、GitHub Actions

## 开发环境要求

- Windows 10/11（项目仅面向 Windows 桌面端）
- Node.js（LTS）与 npm
- Python 3.12+，使用 [uv](https://docs.astral.sh/uv/) 管理 sidecar 依赖
- [LibreOffice](https://www.libreoffice.org/)（.doc/.docx 转换）
- MinerU 独立解释器环境 `sidecar/.venv-mineru/`（含 GPU 加速的 torch；详见 [架构文档 10.8](docs/architecture/architecture.md)）。无该环境时真实引擎测试自动 skip

## 快速开始

```bash
# 安装前端依赖
npm install

# 方式一：完整开发模式（Electron 自动拉起 Python sidecar）
npm run dev

# 方式二：前后端分开启动
npm run sidecar:dev   # 终端 1：Python sidecar（带热重载）
npm run dev           # 终端 2：Electron
```

## 常用命令

| 命令 | 说明 |
|---|---|
| `npm run dev` | 启动开发模式 |
| `npm run build` | 构建 Electron 产物 |
| `npm run dist` | 打包 Windows 安装包（electron-builder） |
| `npm test` | 前端单元测试（Vitest） |
| `npm run test:py` | Python 全部测试（pytest） |
| `npm run test:e2e` | 构建并运行 Playwright 端到端测试 |
| `npm run lint` | ESLint + ruff + mypy + 类型检查 |
| `npm run format` | Prettier + ruff 格式化 |
| `npm run reset:dev` | 重置开发环境数据 |

## 目录结构

```
electron/          # Electron 主进程、preload、sidecar 进程管理、IPC
src/               # Renderer：React 页面、组件、状态、API
sidecar/app/       # Python FastAPI：api/ 路由、parse/ 解析、models、services
sidecar/tests/     # Python 测试：unit / integration / engine / golden
docs/              # 架构、技术选型、项目规则等开发文档
.trae/specs/       # 产品需求 spec、任务清单、checklist
samples/           # 开发测试用例，均来自公网公开资料（大文件不入 git）
scripts/           # 辅助脚本
```

## 文档

- [产品需求文档（spec.md）](.trae/specs/ai-bid-making/spec.md)
- [实施任务清单（tasks.md）](.trae/specs/ai-bid-making/tasks.md)
- [架构设计文档](docs/architecture/architecture.md)
- [技术选型报告](docs/architecture/tech-selection.md)
- [项目规则](docs/PROJECT_RULES.md)
- [需求变更日志](docs/CHANGELOG-spec.md)
- [易标借鉴点](docs/references/yibiao-borrowing.md)
