# 开发/测试/生产环境与 CI/CD 质量控制方案（devops-environment.md）

> 项目：AI标书制作 ｜ 日期：2026-09-28 ｜ 状态：**已确认（2026-09-28 用户拍板）**
> 决策：强制 PR 分支保护 ｜ 安装包本期暂不签名（CI 预留签名变量）
> 适用：个人开发者（单人）；方案保持轻量、不过度工程化，随开发阶段逐步增强。
> 配套：[tech-selection.md](file:///e:/bidcraft/bidcraft-master/docs/architecture/tech-selection.md)、[architecture.md](file:///e:/bidcraft/bidcraft-master/docs/architecture/architecture.md)。

## 一、三套环境定义

| 环境 | 位置 | 用途 | 数据 |
|---|---|---|---|
| 开发 dev | 本机 | 编码、热更新、单元测试 | 独立测试用数据目录（非真实业务库） |
| 测试 test | 本机 + GitHub CI | 黄金样本回归、全部自动化测试 | samples/ 固定样本；每测隔离临时库 |
| 生产 prod | 打包产物（最终用户） | 正式使用 | `%APPDATA%/BidCraft` 真实数据 |

**核心隔离原则**：开发/测试绝不读写生产数据目录；通过环境变量 `BIDCRAFT_ENV=dev|test|prod` 切换数据根路径，启动时在标题/日志中显示当前环境，防误操作。

## 二、本地开发环境

### 2.1 基础工具链
| 工具 | 版本要求 | 用途 |
|---|---|---|
| Node.js | **≥ 22.12 LTS** | electron-builder v27 硬性要求 |
| uv | 最新稳定版 | Python 版本 + 依赖 + venv 一体化管理 |
| Python | 3.12（uv 自动安装，不依赖已损坏的系统 Python） | sidecar 运行时 |
| Git | 任意近期版 | 版本管理 |
| VS Code | — | 推荐插件：ESLint、Prettier、Ruff、Python |

### 2.2 依赖锁定
- **JS 侧**：`package-lock.json` 提交，CI 用 `npm ci`。
- **Python 侧**：`pyproject.toml` 声明 + **`uv.lock` 提交**；本地 `uv sync`，CI 用 `uv sync --locked`（lock 漂移即失败）。
- 依赖升级：本地 `uv lock --upgrade` → 测试全绿 → 提交。

### 2.3 一键脚本（package.json scripts）
| 命令 | 作用 |
|---|---|
| `npm run dev` | 同时启动 Vite Renderer + Electron + Python sidecar（开发模式，热更新） |
| `npm run sidecar:dev` | 单独以 uvicorn --reload 跑 sidecar |
| `npm test` | 前端 Vitest + Python pytest 全量 |
| `npm run test:samples` | 黄金样本回归（EM-1） |
| `npm run lint` / `format` | ESLint + Ruff 检查/修复 |
| `npm run build:sidecar` | PyInstaller 打包 sidecar |
| `npm run dist` | 完整打包 Windows 安装包（不发布） |

## 三、测试体系（金字塔）

| 层级 | 工具 | 范围 | 要求 |
|---|---|---|---|
| 单元测试 | Vitest（前端）、pytest（Python） | 规则库、解析、渲染纯逻辑、隔离仓储 | 随开发同步写；规则库（EM-3）每条规则必须有用例 |
| 集成测试 | pytest + FastAPI TestClient | IPC→sidecar→SQLite 全链路、端到端 API | 每测试用临时数据库 + 临时数据目录 |
| 黄金样本回归 | pytest 驱动 | 和县等真实样本：解析清单/评分表/生成结果对比 | 基线快照 + 结果变化须人工确认才更新快照（EM-1） |
| 端到端 UI | Playwright（Electron 模式） | 关键用户路径、置灰门禁 | 阶段 1.0 至少覆盖 walking skeleton 主路径 |
| 渲染保真 | 脚本 + 人工 | Word/PDF 与模板逐章比对 | 差异全部披露，不静默 |

**覆盖率**：本期不设硬性高覆盖率数字（符合"能跑通"定位），但要求核心基座（隔离仓储、规则库、清单确认）接近全覆盖；覆盖率随报告输出、可见即可，后期再设门禁。

## 四、GitHub Actions 工作流

### 4.1 CI（`.github/workflows/ci.yml`）
- **触发**：push 到 main、所有 PR。
- **Job（windows-latest，本项目仅 Windows）**：
  1. checkout → setup-node 22（缓存 npm）→ setup-uv/setup-python；
  2. `npm ci` + `uv sync --locked`；
  3. lint + 前端类型检查 + Ruff 检查；
  4. Vitest + pytest（含黄金样本回归）；
  5. Playwright（Electron）冒烟；
  6. 上传测试报告/产物。
- **规则 9 落地**：CI 是本机全绿后的第二道闸；本机测试不过不推送，CI 不过不合并。

### 4.2 Release（`.github/workflows/release.yml`）
- **触发**：推送 `v*` 标签（版本号以 package.json 为准，标签人工打）。
- **流程**：全量 CI 检查 → `build:sidecar`（PyInstaller）→ electron-builder `--win --publish always` → 生成 **draft** GitHub Release（含 NSIS exe + latest.yml + blockmap）。
- 人工在 GitHub 审阅 draft → 手动点"Publish release"（个人开发者保留人工闸门）。
- 幂等：同版本已发布则跳过，避免重复构建。

### 4.3 依赖安全
- Dependabot：开启 npm + pip 生态更新提醒。
- 密钥扫描：GitHub 原生 secret scanning（公开仓库免费推送保护）+ CI 中加 gitleaks 扫描步骤。
- pip 侧可加 `pip-audit`（uv 可直接 `uv tool run pip-audit`）。

## 五、质量门禁

| 门禁 | 时机 | 工具 |
|---|---|---|
| 提交前本地钩子 | git commit | Husky + lint-staged：ESLint/Ruff/Prettier 只查暂存文件 |
| 分支推送前 | 本机 | 全量测试全绿（规则 9） |
| 合并/CI | GitHub | lint、类型、全部测试、密钥扫描 |
| 发布前 | tag 构建 | CI + 安装包可安装验证（干净 Windows 环境冒烟） |

**分支策略（已确认：强制 PR）**：
- `main`：始终保持可发布，**启用分支保护**——所有变更（含文档）走 PR，要求 CI 全绿、至少 1 个批准（个人仓库可用管理员 override 自批）后方可合并。
- `feature/xxx`、`fix/xxx`：开发分支，完成后发 PR 合 main。
- 版本标签：`v1.0.0` 语义化版本。

## 六、打包与发布

### 6.1 构建顺序
```
uv sync --locked → pytest 全绿
  → PyInstaller 打包 sidecar（onedir，含 FastAPI/PaddleOCR 运行时）
  → 产物放入 Electron 资源目录
  → electron-vite 构建 Renderer
  → electron-builder --win（NSIS 安装包 + zip + latest.yml）
```

### 6.2 代码签名策略（务实）
- **事实**：2024 年起 EV 证书不再直接绕过 SmartScreen，OV/EV 均走信誉积累；个人证书成本高。
- **建议**：阶段 1.0/1.x **先不购买证书**，安装包未签名（用户首装会有 SmartScreen 提示，个人自用可接受）；CI 中签名步骤以环境变量预留（`WIN_CSC_LINK` 等），未来获取证书后零改造启用。
- 自动更新：electron-updater 对未签名包在本地分发可用；正式分发时再配合签名。

### 6.3 安装包瘦身
- 素材样本不打入包；PaddleOCR 模型按需处理（首启下载 or 打包，1.1 验证体积后定）；
- PyInstaller 排除未用依赖（matplotlib 等常见误打包）；
- NSIS 采用压缩；目标：安装包尽量控制在合理体积，最终以实测为准。

## 七、分阶段落地（避免一步到位的复杂度）

| 阶段 | 落地内容 |
|---|---|
| Task 1（1.0） | Node22 + uv + Python3.12 环境；一键 dev 脚本；最小 `ci.yml`（lint+单测） |
| 1.0 中后段 | pytest/Vitest 骨架 + Playwright 冒烟 + Husky 钩子 |
| 1.1 | 黄金样本回归接入 CI；依赖安全扫描 |
| 1.2 | release.yml + NSIS 打包全链路；签名变量预留 |
| 正式分发前 | 评估购买代码签名证书；自动更新完整性验证 |

## 八、待用户决策
1. 本环境与 CI/CD 方案是否确认？
2. 分支策略：main 直接推送（CI 必绿）还是强制 PR 分支保护？
3. 本期是否接受"暂不签名、首装 SmartScreen 提示"？
4. 确认后：是否将环境落地步骤并入 Task 1 描述，然后等"开始编码"指令？
