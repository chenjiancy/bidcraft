# AI标书制作 - 检查清单（checklist.md）

> 状态：2026-09-28 更新。已完成项打勾，实施阶段对应 Task 1-8 逐项验收。

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
- 纪律复核：
  - [x] 完成即报告、用户确认后提交 PR、CI 全绿用户确认后才合并（Task 8、9、10、11、12、13 已遵守）
  - [x] 测试问题与环境补丁、许可证风险已披露，无静默/杜撰（Task 8、9、10、11、12、13 已遵守）

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

## 发布前检查
- [ ] CI/CD 流水线通过（本机全绿后推送触发）
- [ ] 安装包（electron-builder NSIS）可在干净 Windows 10/11 安装运行
- [ ] 用户环境无需安装 Python（PyInstaller 内置）
- [ ] API Key 未出现在配置/日志/包中
- [ ] 大体积样本未打入安装包
- [ ] electron-updater 自动更新框架已集成（依赖、更新源 GitHub Releases、更新检查/安装逻辑；对应 NFR-7 / architecture.md 第十一章）
- [ ] dev/prod userData 目录隔离已验证（生产构建走 `BidCraftApp`，与开发环境 `BidCraft-dev` 互不污染；对应 NFR-7 / architecture.md 第十章）
