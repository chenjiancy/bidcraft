---
name: bidcraft-dev-workflow
description: 当用户要求执行编码任务、实现 tasks.md 中的 Task、修改代码、提交/推送代码、修复 Bug、运行测试、处理 PR 合并时使用。管控 AI标书制作项目编码阶段全流程纪律，确保单任务推进、测试全绿、全程披露、PR 审查后才合并。需求讨论阶段请用 requirements-dialogue 技能。
---

# bidcraft-dev-workflow

> AI标书制作项目编码阶段的全流程纪律技能。与需求阶段的 `requirements-dialogue` 技能互补：需求讨论加载前者，编码执行加载本技能。
> 详细规则出处：[docs/PROJECT_RULES.md](../../../docs/PROJECT_RULES.md)（冲突时以该文件为准）。

## 触发时机

- 用户发出编码指令（"开始编码"、"执行 Task N"、"实现 xxx 功能"、"修复 xxx Bug"）
- 涉及创建/修改代码文件、运行测试、git 提交/推送/PR 操作的任何场景

## 全流程纪律（编码阶段）

### 1. 单任务纪律
- 一次只执行 tasks.md 中的**一个** Task，禁止跨项推进；
- Task 之间的依赖关系必须遵守（Depends On 未完成的不得开始）。

### 2. 完成节奏（铁律）
```
执行 Task → 本机测试全绿 → 报告（变更摘要 + 证据 + 披露项）→ 停下等用户确认 → 创建 feature 分支提交 → PR → 用户确认合并 → 更新 tasks.md/checklist.md → 下一项
```
- 未经用户确认，**绝不**提交、绝不进入下一项；
- 报告中必须包含：做了什么、改动文件清单、测试证据、发现的问题；
- 每个里程碑结束后，必须用 **AskUserQuestion** 给出下一步的可点击选项（如"继续 Task N+1 / 推送仓库 / 暂停"），让用户点选推进，无需另打确认指令。

### 3. 测试门禁（规则 9）
- 本机测试（Vitest + pytest）**全绿后才可推送**分支；
- CI（GitHub Actions）全绿后才可合并；
- 测试失败必须披露失败详情，禁止跳过、禁止注释掉失败用例。

### 4. 披露义务（不静默）
以下情况必须**主动披露**，等待用户决策：
- 测试失败、构建失败、环境异常（如 Python 环境损坏）；
- 实现与 spec/tasks 描述有偏差的任何取舍；
- 遇到需求未覆盖的场景时的处理选择；
- 基座数据（素材库/模板库/清单）的任何异常；
- 对实现没有把握的部分。
**绝不杜撰内容、绝不静默降级、绝不擅自扩大需求范围。**

### 5. Git/PR 流程
- 所有变更走 `feature/xxx` 或 `fix/xxx` 分支，**禁止直接推 main**（分支保护已启用）；
- commit message 格式：`类型: 摘要`（feat/fix/docs/chore/test/refactor）；
- PR 描述必须含：Summary、Test plan（勾选测试证据）；
- 合并方式：squash merge，合并后删除远程分支。

### 6. 数据与安全红线
- 敏感文件（投标文件、证书、身份证、社保）只在 `samples-local/`，严禁入库；
- API Key 只走 DPAPI，禁止写入配置/日志/代码；
- sidecar 只监听 127.0.0.1；
- 企业/项目数据隔离查询必须带过滤条件。

### 7. 会话记录
- 每完成一个 Task 或关键节点，追加写入 `docs/conversations/sessions/` 对应会话文件；
- 推送前更新 `docs/conversations/index.md` 索引。

### 8. 技能自迭代
- 本技能与 PROJECT_RULES.md 可迭代，但任何修改需用户确认后才生效；
- 发现流程漏洞时主动向用户提出修订建议。

## 与需求阶段的分工

| 阶段 | 加载技能 | 管控内容 |
|---|---|---|
| 需求讨论/方案评估 | requirements-dialogue | 倾听→复述→追问→确认→落盘→推进 |
| 编码执行 | bidcraft-dev-workflow（本技能） | 单任务→测试→披露→PR→合并 |
