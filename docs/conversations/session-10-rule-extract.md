# Session 10: Task 10 规则粗分 + LLM 校验

## 日期
2026-09-29

## 背景
在 Task 9（解析配置 UI）已合并基础上，实现 Task 10「规则粗分 + LLM 校验（默认路径 + 校验模式）」。Task 10 是招标文件解析的核心：在 MinerU 解析结果上，先走规则库确定性提取，再按需走 LLM 校验；同时完成术语识别、混合章节子节性质标注、约束原文锚定校验等。

## 需求确认（编码前）
- 已确认默认路径=纯规则（不调用 LLM），校验模式=LLM 增强（不是双通道）。
- 已确认双通道模式推迟到后续迭代（TR-10.9）。
- 已确认 extract:llm 失败不阻塞 PARSED（用户需知情，可单项重试）。
- 已确认提示词缓存预热先跑"项目概述"项再并发其余（BP-10）。

## 编码内容
1. **规则库 rules/ 纯逻辑包**（TR-10.1～10.5）：
   - `app/rules/catalog.py`：18 key → 分类（资格/废标/商务评分/技术要求/通用）+ 约束抽取（金额/期限/页数/社保/数量）
   - `app/rules/terms.py`：文档类型判定（招标/采购/询比价）+ 动态术语词典 + dict payload 构建
   - `app/rules/nature.py`：子节性质标注（商务/技术/通用）+ SectionRecord
   - `app/rules/extract.py`：整份文档序列化 → 标题定位 → 子树分块 → 规则匹配 → anchor_verified → extract_list.json
   - `app/rules/anchor.py`：空白归一化（含全角空格）后包含匹配，规则与 LLM 共用
   - `tests/unit/test_rules.py`：9 单测覆盖分类/约束/锚定/判型/术语/nature（全绿）

2. **LLM 校验链路**（TR-10.6～10.8）：
   - `app/services/llm.py`：`chat_completion()` + `ChatResult.cached_tokens`；httpx 同步，调用方 `asyncio.to_thread` 包异步层
   - `app/models/llm_call_log.py` + alembic migration：新增 `cached_tokens` 列
   - `app/parse/llm_validate.py`：校验模式 `_SYSTEM_VALIDATE` / `_SYSTEM_AUDIT`；quote 回原文校验，失败强制 risk=high 并清空 quote（拦截幻觉）
   - `tests/unit/test_llm_validate.py`：5 单测覆盖幻觉拦截/LLM error/audit/cached_tokens 透传（全绿）

3. **流水线集成**（service.py + checkpoint/config）：
   - 新增阶段：stage 6 `extract:coarse`（恒有），stage 7 `extract:llm`（仅 llm_enabled + mode==validate）
   - `_run_extract_coarse`：写 `extract_list.json`，动态词典落 `<data_root>/config/keywords.dict.json`（按 project_id 去重累积）
   - `_run_extract_llm`：预热 project_overview → sleep(_LLM_CACHE_WARMUP_WAIT) → Semaphore(4) 并发其余 → audit_gap
   - `affected_checkpoint_items`：配置变更只返回 `("extract:coarse", "extract:llm")`，由前端逐项 retry 续跑
   - `reset_item`：extract:coarse 级联重置 extract:llm；mineru:/chapters:/dedupe-verify/preprocess:/dedupe 均级联重置 extract
   - `register_sources`：失效清理加 `extract_list.json`
   - `get_status`：加 `extraction` 摘要字段（doc_type/items_total/items_extracted/red_flags/llm）

4. **前端适配**：
   - `api/parse.ts`：`startParse` 增加可选 `apiKey?`；status 加 `extraction` 字段
   - `ParsePage.tsx`：勾选变更后显示「重新解析受影响项」+「全部重跑」双按钮；摘要卡片显示文档类型/要素提取/风险提示/LLM 状态；双通道 Radio 禁用并标注"后续迭代"
   - `setup.ts`：mock status 加 `extraction: null`

## 测试情况
- 后端：`pytest sidecar/ -q` → 148 passed, 1 skipped（engine_probe）
- `ruff check sidecar/app` 全绿
- `mypy sidecar/app --ignore-missing-imports` 全绿（Task 8 已签 check_untyped_defs = False）
- 前端：`npm test` 22 快照 + 全部通过（含 setup/parse 测试）
- 窗口验证：
  - TR-10.9 双通道禁用 ✓
  - TR-10.6 API Key 阻断 ✓
  - 术语识别/约束抽取/分类 ✓
  - 配置变更定向重跑 ✓

## 已知披露
- LLM 校验模式未做真实 API 调用验证，由 fake chat 单测+集成测试覆盖；真实环境验证需用户提供 API Key。
- 规则库对弱模板 HTML→PDF 样本的标题定位失败率较高（测试用 10 项 missing 仅 1 found），对真实招标 PDF 预期更高；后续随真实样本扩充调优。
- 动态词典 `keywords.dict.json` 未做并发锁保护（当前单用户，后续多用户/多进程时需考虑）。

## 合并记录
- PR #34（branch `feature/task10-rule-extract` → `main`）
- squash 合并，commit `668e07d`
- 23 files changed, +2271/-59
- 本机 pre-commit（eslint/prettier/ruff）全部通过

## 下一步
Task 11：评分办法解析 → `score_table.json`
