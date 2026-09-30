# AI标书制作 - 检查清单（checklist.md）

> 状态：2026-09-30 更新。已完成项打勾，实施阶段对应 Task 1-22 逐项验收。

## 需求阶段检查
- [x] 项目简介、目的、目标用户已确认
- [x] 项目目标与非目标边界已确认（一期"解析→商务标"主线）
- [x] 背景与参考项目（易标）已记录
- [x] FR-1～FR-5 已逐条确认落盘
- [x] 非功能需求 NFR-1～NFR-7 已确认
- [x] 假设 AS-1～AS-5 已确认
- [ ] FR-6 标书检查需求待讨论（阶段二开发前）

## 设计/规划阶段检查
- [x] 技术选型已确认（Electron+React+TS / Python sidecar / SQLite / AntD5 / MinerU 内置 OCR）
- [x] 架构设计已确认（进程模型、通信、目录、数据模型、状态机、安全边界）
- [x] 阶段 1.0 任务已拆（Task 1-7）并定义 TR
- [x] 1.1/1.2 概要任务已列出（进入前细化）
- [x] 数据隔离在仓储层与测试中有设计落点
- [x] 测试金字塔分层策略已确认（EM-6：静态分析/单元30%/集成50%/E2E20% + 5项专项测试 + CI分层触发矩阵）
- [x] dev/prod 环境隔离方案已确认（BidCraft-dev / BidCraftApp + ELECTRON_RENDERER_URL 检测 + BIDCRAFT_DATA_ROOT 传 sidecar）
- [x] 发布/自动更新/反馈闭环方案已确认（NFR-7：electron-updater + GitHub Releases + 当前阶段日志/Issue手动闭环 + 分发阶段Sentry）

## 实施阶段检查（阶段 1.0 Walking Skeleton）
- [x] Task 1：独立 Python 环境与 Electron 骨架就绪（TR-1.1～1.8 全部满足，PR #13）
- [x] Task 2：应用外壳、导航、明暗主题、置灰门禁（TR-2.1/2.2 全部满足，PR #15）
- [x] Task 3：Sidecar 进程管理、IPC、SSE、127.0.0.1 限定（TR-3.1/3.2/3.3 全部满足，PR #17）
- [x] Task 4：SQLite 迁移与隔离仓储（TR-4.1/4.2 全部满足，PR #19）
- [x] Task 5：企业/项目最小功能、代理人优先级、回收站最小版（TR-5.1/5.2/5.3 全部满足，PR #22）
- [x] Task 6：模型配置、DPAPI、连通性、调用日志（TR-6.1/6.2，PR #24）
- [x] Task 7：端到端走通 + 置灰门禁验证（TR-7.1/7.2，PR #26）
- 纪律复核：
  - [x] 每 Task 完成即报告、用户确认后提交、再进下一项（Task 1、2、3、4、5、6、7 已遵守）
  - [x] 任何测试问题与基座异常已披露，无静默/杜撰（Task 1、2、3、4、5、6、7 已遵守）

## 实施阶段检查（阶段 1.1 解析能力）
- [x] Task 8：招标文件文本/OCR 解析与结构化（TR-8.1～8.9 全部满足，PR #31；真实引擎 5 项本机验证：文字版/扫描件 OCR/.doc 转换/同名去重/probe）
  - 披露：MinerU 3.4.5 独立 `.venv-mineru`（gitignore，不进 CI）；需补装 six；许可证自定义待法务复核；tests/engine 仅本机运行
- [x] Task 9：解析配置（TR-9.1～9.4 全部满足，PR #33；18 项目录 8 关键必选+10 其他可勾、LLM 总开关默认关模式置灰、项目级 parse_project_config 落库、PARSED 后变更提示重解析；顺带按用户要求将启动页导航收敛为企业/项目+底部配置）
  - 披露：双通道模式仅存储选择不实现（Task 10 落地）；TR-9.4 采用"链路打通+reparse 兜底"（物理层不重跑，affected_items 映射 Task 10 接单项重试）；修复 main PR#32 README.md prettier 格式
- [x] Task 10：规则粗分 + LLM 校验（TR-10.1～10.9 全部满足，PR #34；rules/ 纯逻辑包、术语识别+动态词典、子节性质标注、LLM 校验+幻觉拦截+全文审计、缓存预热 cached_tokens 迁移、双通道禁用；窗口验证通过）
  - 披露：extract:llm 失败不阻塞 PARSED（可选增强，可单项重试）；配置变更 PUT 只返回 affected_items 由前端逐项 retry 续跑；API Key 仅 DPAPI 临时透传不落库；窗口验证样本（HTML→PDF）未入库
- [x] Task 11：评分办法解析 → score_table.json（TR-11.1～11.10 全部满足，PR #35；rules/scoring 专用规则子集：大类/评分项/证明材料/门槛三类抽取+多来源合并+合计≠100 标红不阻断；JSON Schema 硬校验门禁 schema_validated；状态机 PARSED→SCORE_PARSED；score:extract/score:llm checkpoint 复用+reset 级联；LLM 专项校验完整性/合计/门槛遗漏；前端评分表摘要卡片）
  - 披露：评分表抽取为规则（关键词+正则），非标表格（复杂合并单元格）可能抽取不全，走 unrecognized 标红 + LLM 校验兜底；score:extract 失败不阻塞终态（回落 PARSED，可单项重试）；修复 pre-commit 拦下的 E501/F841 两处；补锁 jsonschema 4.26 入 uv.lock；真实样本窗口验证未做（测试以 fake MinerU + 单测覆盖）
- [x] Task 12：投标文件格式章节化 docx（TR-12.1～12.7 全部满足，PR #36；三来源统一走 MinerU content_list + chapters.json 页码边界；docx_build 纯逻辑模块：格式章定位/封面整树兜底/HTML+MD 表格还原/仿宋正文/命名清洗与重名保序/路径穿越校验；产物 parse/docx/{stem}/ + manifest.json；stage 8 动态注册 docx:<stem>:<seq> checkpoint，单章失败不阻塞可单项重试；reset 源级/全量级联清理；status docx 摘要；前端「投标文件格式」摘要卡片）
  - 披露：三处实施偏差已经用户确认（决策1=A'统一 content_list 不直读原文件；决策2=A 目录 parse/docx/；决策3=A 无格式章空清单成功不阻塞）；图片/坏表/空区间红字占位计 red_flags 不静默丢失；未做真实样本窗口验证（fake MinerU 集成 +20 个相关测试覆盖）；docx 下载接口/人工增删/地址链接留 Phase 1.2
- [x] Task 13：解析清单 UI（逐条确认/增删、标红）+ 门禁解锁（TR-13.1～13.10 全部满足，PR #37；状态机 SCORE_PARSED→PARSE_REVIEW→PARSE_CONFIRMED；三 Tab 清单复核组件：规则粗分/评分表/投标文件格式，逐条 Checkbox 确认；全条目 confirmed=true 硬校验才保存解锁；标红不阻断（anchor 失败/合计≠100/坏表）；docx 打开走 Electron IPC shell:openDocxFile 带路径校验；parse:confirm checkpoint + parse/confirmed/parse_checklist.json；上游重试 _invalidate_confirmed 回退；移除前端错误自动解锁，isParseConfirmed 由后端 PARSE_CONFIRMED 派生）
  - 披露：walking-skeleton 测试语义修正（解析完成不再自动解锁，需 review+confirm）；docx Tab 不做增删留 Phase 1.2；score 人工改分不重算合计（人工兜底）；未做真实样本窗口验证
- [x] Task 14：商务标格式清单确认（TR-14.1～14.10 全部满足，PR #38；状态机 PARSE_CONFIRMED→FORMAT_REVIEW→FORMAT_CONFIRMED→MATERIAL_LOOP；商务标页面展示 parsed/ 逐章 docx 清单，EXTERNAL 项标注"系统外/不制作"；增（文件路径/名称两种模式）、删（仅标 removed）、改（条目层面）；找不到同名置 MISSING 标红不阻断；确认后 setFormatStatus('FORMAT_CONFIRMED') 刷新门禁；独立 format_list.json checkpoint；vitest 32 passed + pytest 184 passed 全绿）
  - 披露：编辑条目简化为"移除+重新添加"（未直接调用 update API）；未做真实样本窗口验证（fake MinerU + 单测覆盖）
- [x] Task 15：素材库管理（TR-15.1～15.15；material 表迁移 + naming/OCR/imaging/dictionary/fts5/service 模块 + /materials API；前端素材库页 + /materials 路由；pytest 194 passed + vitest 32 passed；PR #39）
  - 披露：未做真实样本窗口验证（StubOcr + 单测覆盖命名模块）；转图片依赖 PyMuPDF/LibreOffice（本机未装时走 RuntimeError）；LLM 辅助默认关闭；IPC 路径直传接口 for_path 替代 multipart 上传
- [x] Task 16：素材提取清单（TR-16.1～16.12 全部满足，PR #40；状态机 MATERIAL_LOOP→MATERIAL_CONFIRMED；material_extract_item 模型 + 迁移 a3c9f1e5d8b2；extract_service 两源聚合/证件组聚合/FTS5 多条件查询/轮次留痕/确认保存门禁；FTS5 查询重写（trigram）；/material-extract API（generate/query/save_round/confirm/import_external）；前端提取页 MaterialsExtractPage + /extract 路由；pytest 215 passed + vitest 40 passed）
  - 披露：修复 Task 14 遗留门禁派生缺陷（setParseStatus 改状态集合判定，避免状态推进后业务模块被重新锁定）；/bid 路由放宽为仅需 PARSE_CONFIRMED（格式清单复核在页内完成）；B 类（确实没有）走收件箱上传后重查，未做真实样本窗口验证（StubOcr + 单测覆盖）
- [x] Task 17：模板库管理（TR-17.1～17.14 全部满足，PR #41；Template 模型 + 迁移 e8d2f4a1b7c3；template_version_dir 目录骨架；service 合规检查/Jinja2 占位语法校验/词典覆盖率/template.json 生成；版本管理 new_version/overwrite_latest；软删除进回收站；外部写入检测；/templates API；前端 TemplatesPage + /templates 路由；pytest 235 passed）
  - 披露：修复 session.flush() 未 commit 导致数据未持久化（改为 session.commit()）；Windows rename 不覆盖已有文件（先 unlink 再 rename）；mark_all_as_deprecated 误排除当前版本（移除 version != 条件）
- [x] Task 18：模板匹配与语义比对（TR-18.1～18.15 全部满足，PR #43；TemplateCompare 模型 + 迁移 f9e3d5a7b2c1；template_match.py 自动匹配/文件关联/语义比对/差异确认门禁；状态机 TEMPLATE_MATCHED→TEMPLATE_REVIEW→READY_TO_RENDER；/template-match API 9 端点；前端 TemplateMatchPage + /template-match 路由；pytest 257 passed + vitest 40 passed）
  - 披露：PR #42 因 base 分支删除被 GitHub 自动关闭，重新 rebase 后以 PR #43 合并；ruff/mypy 31+18 处门禁修复（未用导入/变量、sessionmaker 未实例化、para.style.name 可能为 None 等）；TemplatesPage 遗留 agency 变量未声明编译错误修复；未做真实样本窗口验证
- [x] Task 19：docxtpl 逐章渲染（TR-19.1～19.10 全部满足，PR #44；render/placeholder.py 三类占位解析；render/service.py 渲染计划/A类/B类/图片闭环/docxtpl逐章/警告清单/跨页检测/一致性审计；api/render.py 9 个端点；前端 RenderPage.tsx + api/render.ts；generated_doc 模型+迁移+Repository；pytest + vitest 全绿；mypy + ruff + tsc + eslint 全绿）
  - 披露：PR #42 因 base 删除被 close 后以 #43/#44 重新合并；CI 首次 Lint & Type Check 失败（ts 类型转换、Alert status processing 无效），二次 push 后全绿；未做真实样本窗口验证
- [x] Task 20：转 PDF 与 PDF 合并（TR-20.1～20.10 全部满足，PR #45；_libreoffice_to_pdf 逐章转换 + _merge_pdfs PyMuPDF 合并 + 书签 + EXTERNAL 排除 + EXPORTED 状态转换；api/render.py 导出端点；前端 RenderPage 导出按钮；pytest 280 passed + vitest 40 passed）
  - 披露：CI 首次 Integration Tests 失败（PyMuPDF 未在 pyproject.toml 声明，导致 CI runner 缺依赖），修复后全绿；_merge_pdfs 异常信息暴露不足（except 吞异常只 return False），已修复为 emit 真实异常
- [x] Task 21：两级回收站（TR-21.1～21.12 全部满足，PR #46；RecycleBin 模型扩展 name/status/file_path/original_name；迁移 a1b2c3d4e5f6；RecycleBinRepository save_name/restore/purge；api/recycle_bin.py list/restore/purge + 系统回收站端点；删除企业拦截（有项目时拒绝）；定时清理任务（每小时扫描 purge_at <= now）；保留时长可配（config_kv 默认30天）；恢复冲突改名；schemas RecycleBinItemOut + SystemRecycleBinItemOut；12 个集成测试）
  - 披露：CI 首次 Lint & Type Check 失败（mypy rowcount 类型错误 + ruff import 问题），修复后全绿
- **代码审查缺陷修复（2026-09-30）**：全面审查识别出 9 Critical + 20 Major，已逐条修复并提交
  - **Critical（不废标底线）**：
    - C2 归档成功后 unlink 用户源文件 → 取消 unlink，源文件保留
    - C9 模板存相对路径+agency 未过滤 `../` → 改为绝对路径+safe_filename
    - C1 Electron 路由白名单不含下划线 → 正则改为 `[a-z0-9_]+`
    - C3 项目素材 file_path 双前缀 → 修正为 `_path_base / final_path`
    - C4 score_table schema 校验失败仍转 SCORE_PARSED → 改为 raise ParseError
    - C5 PARSE_CONFIRMED 后重登记文件删产物不回退状态 → 先 ensure_transition 回退
    - C6 同名 doc/docx 转换覆盖 → 输出 unique_path
    - C7 agency 路径穿越 → 并入 C9 修复
    - C8 渲染时重新生成 render_plan 覆盖 B 类用户确认值 → 加载已有计划按章节+占位名匹配保留
  - **Major**：
    - M1 purge 不删业务行 → 同时删除 enterprise/project/material/template 表记录
    - M2 FTS5 索引无人调用 → 删除/恢复素材时同步更新索引
    - M3 alembic 双头 → merge revision 3b426c0f86f8
    - M4 SSE 事件结构不一致 → _emit_progress 统一为 {stage, percent, message, extra?}
    - M5 素材分页 total 错误 → 新增 repo.count() 查询真实总数
    - M6 健康检查超时不 kill → waitForHealth 失败时终止子进程
    - M10 素材/回收站 API 无审计日志 → create/update/delete_material + restore_item 记录 AppEvent
    - M13 导出文件路径穿越 → render_download 添加 ensure_within_project 校验
    - M14 定时任务无重试 → purge 添加 3 次重试 + conflict 标记
    - M18 素材上传无大小限制 → 添加 10MB 限制返回 413
    - M20 日志无统一配置 → main.py 添加 logging.basicConfig
  - 全部测试通过（pytest 280 + vitest 40）；缺陷修复流程已写入 PROJECT_RULES.md 第 14 条
- 纪律复核：
  - [x] 完成即报告、用户确认后提交 PR、CI 全绿用户确认后才合并（Task 8~21 已遵守）
  - [x] 测试问题与环境补丁、许可证风险已披露，无静默/杜撰（Task 8~21 已遵守）

## 验收阶段检查
- [x] 阶段 1.0 验收标准（AC）已定义并全部满足（Task 1-7 全部 done，PR #13/#15/#17/#19/#22/#24/#26）
- [ ] 黄金样本回归（EM-1）已建立并跑绿
- [ ] 数据隔离专项测试已跑绿（企业/项目越权访问用例）
- [ ] 确定性回归测试（商务标）已跑绿（固定输入→固定输出比对）
- [ ] 状态机测试已跑绿（合法/非法转换 + 断点恢复）
- [ ] LLM 模式测试已跑绿（默认关断言 + mock 校验/双通道）
- [x] CI 分层触发矩阵已实现（分支跑单元+集成，PR 跑全部含E2E+黄金样本；PR #13 实证）
- [x] dev/prod userData 目录隔离已实现（BidCraft-dev / BidCraftApp，互不污染）
- [x] 本机全部测试为绿（规则 9）（22 前端 + 43 后端 = 65 passed）
- [x] Task 22：三层递进导航 + workspace两步引导 + 项目首页模块卡片 + access统一管理（TR-22.1～22.5，commit 01c31f4；pytest 287 passed + vitest 77 passed）
  - 披露：合并时有 4 文件冲突（AppLayout/nav-config/WorkspacePage/ProjectHomePage），均已解决；TR-22.3 锁定项 tooltip 命中区过窄与 global.d.ts 重复声明缺陷已于 PR #53 修复（commit 228842e）；sidecar spawn 失败不立即上报（等 30s 超时）缺陷已于 PR #54 修复（commit fafc66d）

## 发布前检查
- [ ] CI/CD 流水线通过（本机全绿后推送触发）
- [ ] 安装包（electron-builder NSIS）可在干净 Windows 10/11 安装运行
- [ ] 用户环境无需安装 Python（PyInstaller 内置）
- [ ] API Key 未出现在配置/日志/包中
- [ ] 大体积样本未打入安装包
- [ ] electron-updater 自动更新框架已集成（依赖、更新源 GitHub Releases、更新检查/安装逻辑；对应 NFR-7 / architecture.md 第十一章）
- [ ] dev/prod userData 目录隔离已验证（生产构建走 `BidCraftApp`，与开发环境 `BidCraft-dev` 互不污染；对应 NFR-7 / architecture.md 第十章）
