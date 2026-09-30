# Session 14: 合并冲突清理 + 远端 main 污染修复 + C6 缺陷修复

## 日期
2026-09-30

## 背景
用户要求把 `origin/feat/task-14-format-checklist` 合并进 main。排查后发现合并提交
`b82615c`（Merge remote-tracking branch 'origin/fix/code-review-bug-fixes'）是在
**冲突未真正解决**的情况下被提交的，且**已经推送到 origin/main**——远端 main 因此带
语法垃圾、无法编译。

## 问题一：坏合并把冲突标记当代码提交

### 影响范围（HEAD 与 origin/main 均为 b82615c）
| 文件 | 问题 |
|---|---|
| src/pages/bid/BidPage.tsx | 3 处冲突标记 |
| src/pages/parse/ParsePage.tsx | 3 处冲突标记 |
| src/stores/useAppStore.ts | 6 处冲突标记 |
| sidecar/app/parse/state.py | 4 处冲突标记（2 处落在 ParseStatus Literal 与 _TRANSITIONS，属语法错误） |
| sidecar/app/parse/paths.py | 2 处冲突标记 |
| .trae/specs/ai-bid-making/tasks.md | 1 处冲突标记 |
| .trae/specs/ai-bid-making/checklist.md | 1 处冲突标记 |
| electron/preload.ts | `shell` 键重复定义（**无冲突标记**，静默合并产物） |
| src/__tests__/setup.ts | `shell` 键重复定义（同上） |

### 溯源
用 `git grep -c "^<<<<<<< HEAD"` 逐一比对历史提交：至少从 `5bc7db9`（task13 合并）起，
上述 7 个文件的冲突标记就已存在，并被其后 5 次合并（task16 / task20 / task21 /
cleanup-requireunlock / code-review-bug-fixes）原样继承（更早提交未逐一核对）。

### 决策
冲突一律"保留 HEAD 侧"：HEAD 侧是含 Task 15–21 与 Task 22 的较新版本，
`feat/task-14-format-checklist` 侧是 Task 14 时间点的旧版本（仅含 Task 14 及之前的实现与文档）。
重复键删除冗余块。全部改动均为纯删除（109 行），不改动任何业务逻辑。

## 问题二：convert_to_pdf 返回不存在的路径（C6）

### 现象
engine 真实样本测试 2 条失败：`test_doc_conversion_via_libreoffice`、
`test_synthetic_same_name_docx_pdf_deduped`，报错均指向不存在的 `xxx-1.pdf`。

### 根因
commit `b732117`（C6 修复，属 PR #47「代码审查缺陷修复」）在 `convert_to_pdf` 末尾追加：

```python
produced = paths.unique_path(produced)
```

但 `unique_path` 的语义是"目标已存在则返回 `-1` 后缀路径"，而此处 `produced` 刚通过
`is_file()` 校验、必然存在，于是函数**永远返回一个不存在的 `-1` 路径**。调用方
`service.py` 紧接着用该路径做 `pdf_text_fingerprint`，必然失败
→ `.doc/.docx → PDF` 链路整体不可用（TR-8.3）。

### 修复
改为"先落 staging、再以唯一名移入 out_dir"：

1. 用 `tempfile.mkdtemp(prefix="bidcraft-lo-", dir=out_dir)` 建私有 staging 目录，
   同时承载 soffice 的 UserInstallation profile 与本次产物（保留原有防 profile 锁能力）；
2. soffice `--outdir` 指向 staging；
3. 转换成功后在 `out_dir` 上用 `unique_path` 取目标名，`shutil.move` 移入；
4. 整个函数体套 `try/finally` 清理 staging；取消/超时/异常路径保持原有 kill 子进程行为。

返回值恒为真实产物路径；同名源（`a.doc` / `a.docx`）分别落到 `a.pdf` / `a-1.pdf`，
C6 想防的"互相覆盖"才真正成立。

### 为什么 PR #47 没拦住
`convert_to_pdf` 此前只有 engine 集成测试覆盖，而 engine 标记的用例被 CI 排除
（`pyproject.toml` markers：engine = 需要本机 MinerU venv/样本的真实解析测试，CI 不装）。
本次补 `tests/unit/test_preprocess.py`（假 soffice 子进程，不依赖本机 LibreOffice）作为回归护栏。

## 测试情况
| 阶段 | 结果 |
|---|---|
| 修复前 pytest | 282 passed / **2 failed**（engine） |
| 修复后 pytest | **287 passed**（含 5 条 engine 用例） |
| eslint / ruff / mypy / tsc | 全绿 |
| vitest | 74 passed |
| 回归单测反向验证 | 临时把 preprocess.py 回退到缺陷版本，`test_preprocess.py` 中 2 条立即失败，复现 `a-1.pdf` 不存在症状 |

## 披露
1. **远端 main 曾被污染**：坏合并 `b82615c` 已推送；本次修复在本地完成，需走 PR 合回。
2. 清理范围超出"冲突文件"：`electron/preload.ts`、`src/__tests__/setup.ts` 的重复键
   没有冲突标记，属静默合并产物；若不清理，`tsc` 直接报 TS1117。
3. 从 `5bc7db9` 到 `b82615c`，main 长期处于不可编译状态，说明合并流程缺少
   "合并后先跑 lint/typecheck 再提交"的门禁。
4. 排查中曾怀疑是环境问题（LibreOffice 未装或超时），实测本机 soffice 转换正常
   （约 1–2 分钟，远低于 600s 超时阈值），排除环境因素后才定位为代码缺陷。

## 本次产出文件
- [preprocess.py](file:///e:/bidcraft/bidcraft-master/sidecar/app/parse/preprocess.py) - C6 修复：staging 目录 + 唯一名移入
- [test_preprocess.py](file:///e:/bidcraft/bidcraft-master/sidecar/tests/unit/test_preprocess.py) - 新增回归单测（3 条）
- [BidPage.tsx](file:///e:/bidcraft/bidcraft-master/src/pages/bid/BidPage.tsx)、[ParsePage.tsx](file:///e:/bidcraft/bidcraft-master/src/pages/parse/ParsePage.tsx)、[useAppStore.ts](file:///e:/bidcraft/bidcraft-master/src/stores/useAppStore.ts)、[state.py](file:///e:/bidcraft/bidcraft-master/sidecar/app/parse/state.py)、[paths.py](file:///e:/bidcraft/bidcraft-master/sidecar/app/parse/paths.py)、[preload.ts](file:///e:/bidcraft/bidcraft-master/electron/preload.ts)、[setup.ts](file:///e:/bidcraft/bidcraft-master/src/__tests__/setup.ts)、[tasks.md](file:///e:/bidcraft/bidcraft-master/.trae/specs/ai-bid-making/tasks.md)、[checklist.md](file:///e:/bidcraft/bidcraft-master/.trae/specs/ai-bid-making/checklist.md) - 清理冲突标记与重复键

提交：`918ebd9`（合并清理）、`f5d553b`（C6 修复 + 回归单测）

## 待办/后续
- 上述两个提交走 PR 合入 main，恢复远端可编译状态
- 建议（待定）：为合并流程增加"合并后跑 lint/typecheck"门禁，或把 engine 用例纳入
  CI 的可跳过矩阵，避免同类缺陷再次无声通过
