# Session 12: Task 12 投标文件格式章节化 docx

## 日期
2026-09-29

## 背景
在 Task 11（评分办法解析 → SCORE_PARSED，PR #35）已合并基础上，实现 Task 12「投标文件格式章节化 docx」：在 Task 8 chapters.json 章节边界内，把招标文件「投标文件格式」章逐章导出为独立 docx（含封面），供后续 Task 13 解析清单 UI 引用。范围只做自动切分 + 逐章保存；人工增删、地址链接留 Phase 1.2。

## 需求确认（编码前，用户回复 A 确认三个方案偏差点）
1. **决策 1=A'**：三种源文件（文字版 PDF / 扫描件 PDF / docx）内容来源**统一走 MinerU content_list**，不直读原文件；章节边界 100% 复用 chapters.json 页码闭区间。与 spec TR-12.1/12.3「从原文件直接抽取」字面有偏差，优点是一条实现路径、表格/图片块都在 content_list 内、三来源行为一致。
2. **决策 2=A**：产物目录 `parse/docx/`（非 spec 字面的 `parsed/`），与既有 parse/raw、parse/work、parse/structured 组织一致。
3. **决策 3=A**：无「投标文件格式」章节时标 success + 空清单 + 事件日志提示，不阻塞主流程，终态仍 SCORE_PARSED。
4. 状态机不新增状态，复用 SCORE_PARSED，靠 manifest.json `completed` 标志位 + 每章 checkpoint 区分完成度。

## 编码内容

1. **路径与依赖**：
   - `app/parse/paths.py`：`docx_dir()` → 项目 `parse/docx/`、`docx_manifest_path()` → `parse/docx/manifest.json`；复用既有 `safe_filename`（非法字符清洗+截断 180）、`unique_path`、`ensure_within_project`（路径穿越防护）
   - pyproject 新增 `python-docx>=1.1.2`（实装 1.2.0 + lxml 6.1.3，uv.lock 同步）

2. **app/parse/docx_build.py 纯逻辑模块**：
   - `SectionPlan`（source_stem/seq：封面 0、正文从 1 起/title/kind：cover|section/start_page/end_page；`checkpoint_key` = `docx:{stem}:{seq:02d}`；`filename` = `{seq:02d}_{safe_filename(title)}.docx`）、`SourcePlan`
   - `find_format_chapter`：chapters 树前序遍历定位标题归一化含「投标文件格式」的节点；`find_cover_in_subtree` 精确匹配「封面」
   - `plan_source`：封面先在格式章子树找，找不到搜整棵树（关键事实：chapters.py `_BARE_TITLES` 把无编号「封面」恒识别为一级章，是格式章同级而非子节点）；direct children 排除封面后各成一章；无 children 用 text_level≤2 块 fallback（排除格式章自身标题块防误判 seq=1）；完全平铺则整章合成一个 docx
   - `collect_blocks`：页码闭区间收块，跳过同页同名章节标题块防标题重复
   - 表格：`_TableHTMLParser` 解析 MinerU table_body HTML；`_parse_md_table` 老版 Markdown 表格降级（丢分隔行）
   - `blocks_to_docx`：python-docx 落盘，Normal 样式正文设仿宋（w:eastAsia）；title heading level 0；text_level 块→heading；table→Table Grid（HTML 优先 MD 降级，都失败红字「表格无法还原」）；image→「caption，请对照原文件」红字；空区间红字；返回 paragraphs/tables/images/red_flags 计数
   - `render_section`：ensure_within_project 校验后写 `docx/{safe_filename(stem)}/{filename}`，返回相对路径 + 页码 + 计数
   - `assemble_manifest`：completed=False 骨架，含 total_files 与每节 checkpoint_key

3. **流水线集成（service.py）**：
   - 权重 `_W_DOCX_END=98`（extract 94 / score 97 / docx 98 / LLM 99-100）；原 stage 8/9 顺延为 9/10，新 stage 8 为 docx 章节化
   - `_plan_docx`：读 chapters.json + 从 mineru success 项收集 content_list → plan_all_sources → 动态注册 checkpoint labels（封面「投标文件封面导出（docx）」，其余「格式章节导出（docx）：{title}」）
   - 逐章 `render_section`（to_thread）；单章失败 mark_error + app_event `parse_docx_error` + emit 后继续其余章（TR-12.7）；规划/manifest 级异常 `parse_docx_stage_error` 不阻塞；0 章时 emit「未识别到「投标文件格式」章节」
   - `_write_docx_manifest`：按 checkpoint 实际状态回填每个 file 的 state/output/error，重算 completed
   - `_docx_summary` → get_status 新增 `docx` 键（sources/files/cover/completed/errors/red_flags/missing_format_sources）；schema ParseStatusOut 加 `docx`
   - `reset_item`：新增 `_reset_docx_source(stem)`（删该源 docx: 项+产物子目录+manifest）与 `_reset_docx_all()`；docx 单项重试 reset 前先从 output.file 取路径（ensure_within_project 校验）删文件+manifest；mineru:/chapters: 级联源级清理，dedupe-verify/preprocess:/dedupe 级联全量清理；docx 与 extract/score 无依赖
   - `register_sources` 失效清理含 manifest + 整个 docx 目录
   - docx 不影响终态（仍按 score:extract 成败决定 SCORE_PARSED/PARSED）

4. **前端适配**：
   - `api/parse.ts`：`DocxSummary` 类型 + `ParseStatus.docx`
   - `ParsePage.tsx`：完成态新增「投标文件格式（逐章 docx）」卡片——文档数、封面有无、失败章数（提示可单项重试）/completed、red_flags「需对照原文件」、missing_format_sources 来源提示；docx: 项自动复用通用单项重试列表
   - mock：setup.ts 与 parse-config.test.tsx status 加 `docx`（makeCallMock/renderParsePage opts 透传）；新增 2 测试（正常摘要、无格式章空清单提示）

## 测试情况
- 后端：`pytest tests/unit tests/integration` → **172 passed**
  - 新增 test_docx_build.py 14 单测：格式章定位/not found/直接子章+封面编号页码文件名/fallback text_level/封面同级整树兜底/平铺整章/多源/收块去标题/HTML 表格/MD 表格/图片+坏表标红/空区间/render 分源目录+文件名清洗/路径逃逸拒绝
  - 新增 test_parse_docx_api.py 6 集成：TR-12.1 文字版 PDF、TR-12.2 扫描件 PDF、TR-12.3 docx 源（均断言三个 docx 文件名 + 第二子节表格行列内容）、无格式章空清单且终态 SCORE_PARSED、TR-12.6 跨企业 404 + 目录隔离、TR-12.7 注入 seq=02 渲染失败→该项 error 成功章保留→单项 retry 续跑只调用渲染 1 次且封面 mtime 不变
- 前端：vitest → **32 passed**（7 文件，新增 2 例）
- `ruff check app tests` / `mypy app --ignore-missing-imports` / `tsc --noEmit` / eslint 改动文件全绿
- CI（PR #36）：Lint & Type Check / Unit Tests / Integration Tests / Golden Sample Regression / E2E Smoke (Electron) 全部 pass

## 过程问题与修复（披露）
1. **文件名期望修正**：初版集成测试断言 `01_一、投标函.docx`，实际 chapters 树节点 `title` 为去编号章名（编号在 `number` 字段），产出 `01_投标函.docx`——恰好与 TR-12.4 示例一致，按实际修正测试。
2. **ruff E501×3 + I001×2 + mypy arg-type×1**：长 f-string 拆行；import 排序让 ruff --fix 处理（service 合并成单行 import）；python-docx `document.save()` 不接受 Path 类型（mypy），改 `str(out_path)`（运行时本来正常）。
3. **前端「无」标签多匹配**：无格式章场景封面 Tag 与导出 0 Tag 文案都是「无」，getByText 撞多元素 → 改 getAllByText 断言长度 2。
4. 历史坑规避：note 字符串用中文书名号「」防 ASCII 引号嵌套 SyntaxError；封面构造为顶级章（与格式章平级）而非子节点。

## 已知披露
- **未做真实招标文件样本窗口验证**：全部基于 fake MinerU 构造的中文 content_list。真实复杂合并单元格、图片封面、扫描 OCR 噪声下的还原效果待样本确认；无法还原的表格/图片/空区间均红字占位并计入 red_flags，不静默丢失。
- 三来源统一 content_list 与 spec TR-12.1/12.3 字面（直读原文件保留原貌）存在已确认偏差：python-docx 生成的是结构化重排文档，不保证与原文排版像素一致；需要原貌的场景留待后续评估。
- docx 下载接口、人工增删章节、地址链接均不在本期（Phase 1.2 / Task 13 衔接）。

## 合并记录
- PR #36（branch `feature/task12-docx-chapters` → `main`）
- squash 合并，commit `f3c042b`（2026-09-29）
- 12 files changed, +1301/-8
- 远程分支已删除，本地 main 已同步

## 下一步
Task 13：解析清单 UI（逐条确认/增删、标红）+ 门禁解锁（Depends On Task 12 已满足）。Task 13 将引用 extract_list / score_table / parse/docx 产物做人工复核界面。
