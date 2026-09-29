# Session 13: Task 13 解析清单 UI + 门禁解锁

## 日期
2026-09-29

## 背景
Phase 1.1 收尾 Task。整合 Task 8-12 产物（规则粗分 extract_list.json / 评分表 score_table.json / 投标文件格式 docx manifest），实现三 Tab 清单复核 UI + 逐条确认 + 标红 + 门禁解锁。修正前端错误的"SCORE_PARSED 自动解锁"为后端 PARSE_CONFIRMED 驱动。

## 编码内容

### 后端
1. **状态机 state.py**：ParseStatus 扩展 PARSE_REVIEW/PARSE_CONFIRMED + 转换表（SCORE_PARSED→PARSE_REVIEW→PARSE_CONFIRMED；上游重试回退 SCORE_PARSED）
2. **路径 paths.py**：confirmed_dir() + checklist_path() → parse/confirmed/parse_checklist.json
3. **schemas/parse.py**：ParseChecklistOut（三类全量+confirmed快照+review_state）、ParseConfirmIn（items[]+三类最终态+note）、ParseConfirmOut
4. **service.py**：
   - `get_checklist()`：读三类产物全量
   - `enter_review()`：SCORE_PARSED→PARSE_REVIEW（幂等），注册 parse:confirm checkpoint
   - `confirm_checklist()`：硬校验全条目 confirmed=true → 写 parse_checklist.json → mark_success → PARSE_CONFIRMED
   - `_invalidate_confirmed()`：上游重试回退（删 checklist + reset checkpoint + 状态回退）
   - `reset_item` 签名加 factory 参数，末尾调 _invalidate_confirmed
   - `register_sources` 加删 confirmed_dir
   - `get_status` 加 confirmed 摘要（_confirmed_summary）
5. **api/parse.py**：GET /parse/checklist、POST /parse/review、POST /parse/confirm 三端点

### 前端
6. **useAppStore.ts**：parseStatus 派生 isParseConfirmed（setParseStatus 内部 set isParseConfirmed = s==='PARSE_CONFIRMED'）；移除 ParsePage 中 setParseConfirmed(true) 的错误调用
7. **api/parse.ts**：ExtractList/ScoreTable/DocxManifest 全量类型 + ParseChecklist/ParseConfirmPayload/ParseConfirmResult + getParseChecklist/enterParseReview/confirmParseChecklist API + ConfirmedSummary
8. **ParseChecklistReview.tsx**（新建）：三 Tab 组件（ExtractionTab/ScoreTab/DocxTab），逐条 Checkbox + 标红 + 进度条 + 保存并解锁按钮（disabled unless all_confirmed）；DocxTab 有"打开文件"按钮调 window.bid.shell.openDocxFile
9. **ParsePage.tsx**：移除 auto-unlock、加 setParseStatus、review phase 渲染 ParseChecklistReview、"进入清单复核"按钮
10. **electron IPC**：preload.ts shell.openDocxFile + main.ts handler（路径穿越防护：resolve 校验位于 docx 目录内）+ global.d.ts BidAPI 扩展

### 测试
11. **walking-skeleton.test.tsx**：必改——解析完成不再自动解锁，需 mock review+confirm 才 PARSE_CONFIRMED；新增切换项目/企业重置 parseStatus 断言
12. **parse-config.test.tsx**：SCORE_PARSED 不再自动 setParseConfirmed，显示"进入清单复核"按钮
13. **setup.ts**：mock 加 confirmed/checklist/review/confirm 路由 + shell.openDocxFile
14. **test_parse_confirm_api.py**（新建，6 集成测试）：checklist 全量/review 转换幂等/缺确认 400/全确认 200+落盘/隔离/上游重试回退

## 测试情况
- 后端：pytest → 178 passed（+6 集成）；ruff/mypy 全绿
- 前端：vitest → 32 passed；tsc/eslint 全绿
- CI（PR #37）：五项全绿

## 披露
1. walking-skeleton 测试语义修正：解析完成不再自动解锁（spec 正确行为）
2. docx Tab 不做增删（仅确认+打开），商务标阶段留 Phase 1.2
3. score 人工改分不重算 total_score_check（人工兜底）
4. 未做真实样本窗口验证

## 合并记录
- PR #37（branch `feature/task13-parse-checklist-gate` → `main`）
- squash 合并，commit `88d208f`（2026-09-29）
- 16 files changed, +1553/-46
- 远程分支已删除，本地 main 已同步

## 下一步
Phase 1.1 全部完成（Task 1-13 done）。Phase 1.2 商务标生成从 Task 14 开始（PARSE_CONFIRMED → FORMAT_REVIEW → FORMAT_CONFIRMED → MATERIAL_LOOP）。
