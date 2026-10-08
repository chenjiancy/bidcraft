---
name: isolated-sidecar-verification
description: 在隔离数据根中运行 sidecar 管线验证，含测试后端注入与强制清理。用于素材归档/OCR/FTS 真实取证、sidecar 缺陷复现、PR 合并后回归验证。普通单元测试、纯前端任务或无需真实管线的检查不要使用。
---

# isolated-sidecar-verification

> BidCraft sidecar（FastAPI）管线的隔离验证规程：**隔离数据根 → 注入后端 → 运行取证 → 强制清理**。
> 目的是用真实或桩后端跑完整管线并留下可信证据，同时绝不污染用户真实库和仓库。编码纪律仍受 `bidcraft-dev-workflow` 约束（先获编码授权、完成后停下等确认）。

## 触发时机

- 需要验证归档/OCR/FTS/词典等只有完整管线才暴露的行为（如 `ocr_text` 是否落库、FTS 是否命中文档正文）；
- 复现 sidecar 端到端缺陷，或对比修复前后行为；
- PR 合并后在 main 上做取证式回归。

不适用：常规 `pytest` 单测/集成测试、渲染器（React/TS）任务、只看静态代码即可回答的问题。

## 1. 隔离：临时脚本 + 临时数据根

- 验证脚本写到 `%Temp%`（命名如 `bc_verify_xxx.py`、`bc_ts4_xxx.py`），**禁止写进仓库**。
- 脚本开头（必须在 `import app.*` **之前**）设置独立数据根：

```python
import os, tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="bc-verify-xxx-"))
os.environ["BIDCRAFT_DATA_ROOT"] = str(ROOT)
```

这样数据库、FTS5、归档文件全部落在临时目录，与用户真实数据（`%AppData%/BidCraft(-dev)`）物理隔离。

## 2. 重建引擎与库

```python
from app.db.deps import get_engine, reset_engine
from app.db.migrate import run_migrations
from app.db.session import session_factory

reset_engine()
run_migrations()
session = session_factory(get_engine())()
try:
    ...  # 验证逻辑
finally:
    session.close()
```

设置 `BIDCRAFT_DATA_ROOT` 后必须 `reset_engine()`，否则引擎仍指向真实库。

## 3. 注入后端

- **验证真实能力**：走默认工厂，如 `archive_material(..., ocr_backend=build_default_ocr())`（RapidOCR 进程内推理，首次加载约 1s，之后每页 1~3s）。
- **服务层直测**：传入自定义 `OcrBackend` 子类（实现 `recognize(image_bytes) -> OcrResult`），可记录收到的字节做断言。
- **API 层测试（pytest）**：用 `monkeypatch.setattr(materials_api, "build_default_ocr", lambda: FakeOcr())` 替换 API 模块内引用的工厂；monkeypatch 测试结束自动还原。注意要 patch **使用点**（`app.api.materials`），不是定义点。
- 需要避免测试加载真实 ONNX 模型时，用 autouse fixture 统一打桩。
- FTS 取证：`fts5_search(fts5_db_path(eid), "关键词")` 返回 list[dict]，取 `h["material_id"]`；验证"正文可搜"而不仅是"文件名可搜"。

## 4. 运行方式（Windows / PowerShell）

```powershell
$env:PYTHONPATH="e:\bidcraft\bidcraft-master\sidecar"
# cwd 必须为 sidecar
.\.venv\Scripts\python.exe "$env:Temp\bc_verify_xxx.py"
```

- 裸跑脚本必须设 `PYTHONPATH`；`pytest` 不需要（pyproject 已配 `pythonpath=["."]`）。
- 主 venv 是 `sidecar/.venv`；MinerU venv 是 `sidecar/.venv-mineru`（torch 体系），**不能**用来跑主 app。
- 全量回归：`.\.venv\Scripts\python.exe -m pytest -q`，约 6 分钟（基线以当前 main 实际数为准）。
- 工具输出过大被截断时，读取返回的 persisted output 文件，不要重跑。

## 5. 强制清理（验证完成的硬判定）

1. 删除临时脚本：`Remove-Item "$env:Temp\bc_verify_xxx.py" -Force`；
2. 删除临时数据目录：
   `Get-ChildItem $env:Temp -Directory -Filter "bc-verify-*" | Remove-Item -Recurse -Force`；
3. `git status --short` **必须无输出**，确认仓库无新增垃圾、无误改；
4. 分支清理：`git fetch --prune origin` 清过期远端引用；squash 合并的本地分支无提交血缘，`git branch -d` 会拒绝，在确认内容已在 main（CI 全绿 + 本机测试数吻合）后用 `git branch -D` 删除。

未完成清理，不算验证结束。

## 已知坑（本仓库实测）

- `fitz` 偶发对真实存在的文件抛 `FileNotFoundError`：重试即成功，疑似瞬时占用。
- RapidOCR 返回对象读 `.txts` / `.scores`（tuple），**没有** `.txt` 属性；`zip()` 必须显式 `strict=False`（pre-commit 规则 B905）。
- `gh pr create --body` 内联含中文、反引号、反斜杠的长文本在 PowerShell 中转义会爆炸：body 写临时 `.md`，用 `--body-file`，用完即删。
- 涉及身份证等隐私样本：报告可引用文件路径和字段识别情况，不复制、不落盘证件内容；临时数据目录验证后立即删除。

## 取证输出要求

完成报告至少包含：样本清单（路径/分类）、关键量化结果（识别行数、文本长度、耗时、置信度概况）、断言结论（如 FTS 命中数）、发现的噪声/偏差，以及清理证据（`git status` 无输出）。随后按编码纪律停下，用 AskUserQuestion 给出下一步选项。
