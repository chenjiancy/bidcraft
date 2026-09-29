# Session 11: Task 11 评分办法解析 → score_table.json

## 日期
2026-09-29

## 背景
在 Task 10（规则粗分 + LLM 校验）已合并（PR #34）基础上，实现 Task 11「评分办法解析」。Task 11 是 Task 10 要素提取中评分办法部分的深度结构化：新建评分表专用规则子集，产出统一层级结构的 `score_table.json`，并扩展状态机至 SCORE_PARSED。

## 需求确认（编码前）
- 方案 A：规则库前置机械抽取，LLM 仅做校验模式增强（复用 Task 10 同一套 LLM 开关，默认关不调 LLM）。
- 层级结构：评分大类 → 评分项 → 分值 → 所需证明材料 → 门槛条件（日期/金额/数量）。
- 合计分值 ≠100 标红披露但**不阻断**产出（人工兜底）。
- Schema 硬校验为门禁，通过后置 `schema_validated` 标志位，Task 13 只查标志位。
- 证明材料仅抽名称，不做素材库匹配（匹配留 Phase 1.2）。

## 编码内容

1. **rules/scoring 纯逻辑子集**（TR-11.1～11.5）：
   - `thresholds.py`：日期（近 N 年/有效期/年月日）、金额（合同金额≥XX 万/元）、数量（≥N 个/项/人）三类正则，`Threshold` dataclass + `find_thresholds` 按行扫描
   - `extract.py`：`extract_score_table(score_matches, *, generated_at)` 主入口；`_is_category_line`（大类关键词+分值，且排除编号前缀防评分项误判）；`_extract_materials`（"提供/附/须附"引导或括号内材料名）；`_parse_score_items` 逐行解析评分项，识别不出的入 unrecognized 标红；tech_score + business_score 多来源合并；`total_score_check`（expected=100/actual/ok，容差 0.01）
   - `schema.py`：JSON Schema Draft202012 定义 categories/items/materials/thresholds/total_score_check/red_flags 结构；`validate_score_table` 通过时写 `schema_validated=True`
   - `tests/unit/test_scoring.py`：10 单测覆盖门槛三类、大类/评分项、材料、多来源合并、合计不符标红不阻断、确定性（r1==r2）、schema 合法/非法/kind 拒绝

2. **LLM 校验专项**（TR-11.7）：
   - `app/parse/score_llm.py`：`_SYSTEM_SCORE` 聚焦 completeness（评分项完整性）/sum_check（跨表合计）/threshold_coverage（门槛遗漏）/overall_risk；`validate_score()` 读 score_table + 评分章节 snippet，返回 status/data/error

3. **状态机扩展**（TR-11.8）：
   - `state.py`：ParseStatus 增 `SCORE_PARSED`；`_TRANSITIONS` 增 PARSED→SCORE_PARSED、PARSING→SCORE_PARSED（一次跑完直达）、SCORE_PARSED 出边
   - 终态：score:extract success → SCORE_PARSED；否则回落 PARSED（评分阶段失败不阻断）

4. **流水线集成**（TR-11.9/11.10）：
   - checkpoint 新增 `score:extract`（恒有）/`score:llm`（仅校验模式注册）；权重 _W_EXTRACT_END=94、_W_SCORE_END=97
   - Stage 7 评分表规则粗分、Stage 8 extract:llm、Stage 9 score:llm（编号顺延）；两个 score 阶段失败均 mark_error + emit 不阻塞
   - `_run_score_extract`：读 extract_list.json 收集 tech/business_score matches → 抽取 → Schema 校验 → 写 `structured/score_table.json`
   - `_run_score_llm`：读 score_table + 评分章节 snippets → 专项校验 → 回写 llm 字段
   - reset 级联：extract:coarse/mineru:/chapters:/dedupe-verify/preprocess:/dedupe 均级联 `_reset_score()`；新增 score:extract/score:llm reset 分支
   - `affected_checkpoint_items` 返回含 score:extract、score:llm；API `reparse_required` 条件覆盖 SCORE_PARSED
   - 产物路径 `paths.score_table_path()` 落项目 parse/structured/，register_sources 失效清理含此文件；`get_status` 新增 `score` 摘要（categories/total_score/score_ok/red_flags/schema_validated/llm）
   - schema：ParseStatusOut 增 `score` 字段；依赖增 `jsonschema>=4.23`（uv.lock 同步 4.26.0）

5. **前端适配**（TR-11.8 展示）：
   - `api/parse.ts`：`ScoreSummary` 类型 + `ParseStatus.score`
   - `ParsePage.tsx`：SCORE_PARSED 与 PARSED 同等视为完成态并解锁门禁；新增「评分表摘要」卡片（大类数/合计分值≠100 红色标签提示核对/风险项数/结构校验标志/LLM 状态）；单项重试复用通用 retryItem，自动覆盖 score checkpoint 项
   - mock：setup.ts / parse-config.test.tsx status 响应加 `score` 字段；新增 2 前端测试（SCORE_PARSED 解锁、合计≠100 标红卡片）

## 测试情况
- 后端：`pytest`（忽略 engine）→ **153 passed**，其中新增 test_scoring.py 10 例；集成测试状态断言更新为 SCORE_PARSED（full_pipeline/resume/state_events/llm_missing_api_key/config_change 共 12 处适配）
- 前端：vitest → **30 passed**（7 文件，新增 2 例）
- tsc / eslint / ruff（pre-commit lint-python-staged）全绿
- CI（PR #35）：Lint & Type Check / Unit Tests / Integration Tests / E2E Smoke (Electron) / Golden Sample Regression 全部 pass

## 过程问题与修复（披露）
1. **大类行误判**：`_is_category_line` 初版将"技术方案 30分"这类编号评分项误判为大类行 → 加 `_ITEM_PREFIX` 编号前缀排除。
2. **状态机缺直达边**：一次跑完抛 `IllegalTransitionError: PARSING → SCORE_PARSED` → `_TRANSITIONS[PARSING]` 补 SCORE_PARSED。
3. **pre-commit 拦截 2 处**（比本机自查更严）：`api/parse.py:267` E501 行超长拆行；`rules/scoring/extract.py` F841 未使用变量 cat_score/cat_m 删除。修复后复跑 16 相关测试无回归。
4. **uv.lock 缺 jsonschema**：本机 venv 已装所以 pytest 可过，但锁文件未更新会导致 CI 缺包 → `uv lock` 补入 jsonschema 4.26.0 及传递依赖（attrs/jsonschema-specifications/referencing/rpds-py）。

## 已知披露
- 评分表抽取基于关键词+正则规则，非标准表格（复杂合并单元格、图片化表格）可能抽取不全 → unrecognized 标红 + LLM 校验兜底，符合"标红不阻断"设计；规则随真实样本持续扩充。
- 未做真实样本窗口验证（与 Task 10 末期节奏一致）；测试由 fake MinerU 中文块集成测试 + 10 条规则单测覆盖。真实评分办法章节样本的端到端验证建议在 Task 13（清单 UI）前补做一次。
- score:extract 失败时终态回落 PARSED，不阻断主线；前端可通过 checkpoint 单项重试。

## 合并记录
- PR #35（branch `feature/task11-score-table` → `main`）
- squash 合并，commit `3e5fbf2`（2026-09-29）
- 21 files changed, +1032/-30
- 远程分支已删除，本地 main 已同步

## 下一步
Task 12：投标文件格式章节化 docx（Depends On Task 11 已满足）。范围：自动切分 + 逐章 docx 落地（含封面），复用 Task 8 章节边界，人工增删/地址链接留 Phase 1.2。
