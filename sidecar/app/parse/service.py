"""招标文件解析编排（Task 8 核心服务）。

流水线（checkpoint 驱动，支持断点续跑/单项重试，BP-1）::

    sources.json（登记）
      → dedupe（同名分组 + 主格式选择，纯逻辑）
      → preprocess:<file>（.doc 转 PDF；为同内容判定所需的 docx→PDF）
      → dedupe-verify（PDF 指纹比对：同内容去重 / 不同内容保留并披露）
      → mineru:<file>（MinerU 文本/OCR 自动分流，产物入 parse/raw/）
      → chapters:<file>（章节切分，汇总 chapters.json）
      → PARSED

全部产物按企业/项目两级隔离（paths 统一拼接，禁止逃逸）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.core.tasks import registry
from app.parse import chapters as chapters_mod
from app.parse import config as parse_config
from app.parse import dedupe as dedupe_mod
from app.parse import docx_build, engine, llm_validate, paths, preprocess, score_llm, state
from app.parse.checkpoint import CheckpointStore
from app.parse.dedupe import SourceFile
from app.repositories.app_event import AppEventRepository
from app.repositories.base import NotFoundError, Scope
from app.repositories.config_kv import ConfigKVRepository
from app.repositories.parse_config import ParseConfigRepository
from app.repositories.project import ProjectRepository
from app.rules import extract as rules_extract
from app.rules.scoring import extract as scoring_extract
from app.rules.scoring import schema as scoring_schema

JOB_TYPE = "document_parse"
_SOURCES_FILE = "sources.json"
_DEDUPE_FILE = "dedupe.json"
_CHAPTERS_FILE = "chapters.json"

# 阶段进度权重（累计百分比）
_W_DEDUPE = 5
_W_PREPROCESS_END = 20
_W_VERIFY_END = 25
_W_MINERU_END = 85
_W_CHAPTERS_END = 92
_W_EXTRACT_END = 94
_W_SCORE_END = 97
_W_DOCX_END = 98
# LLM 校验收尾到 99/100

# LLM 并发上限（校验模式批量项）
_LLM_CONCURRENCY = 4
# 预热后等待缓存生效（秒）
_LLM_CACHE_WARMUP_WAIT = 2.0

ProgressSink = Callable[[dict[str, Any]], None]


class ParseError(Exception):
    """解析业务错误（消息可直接展示给用户）。"""


class JobRunningError(ParseError):
    """该项目已有解析任务在运行。"""


# ---------- JSON 产物读写 ----------


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sources_path(enterprise_id: str, project_id: str) -> Path:
    return paths.parse_dir(enterprise_id, project_id) / _SOURCES_FILE


def _dedupe_path(enterprise_id: str, project_id: str) -> Path:
    return paths.parse_dir(enterprise_id, project_id) / _DEDUPE_FILE


def _chapters_path(enterprise_id: str, project_id: str) -> Path:
    return paths.chapters_path(enterprise_id, project_id)


def _work_dir(enterprise_id: str, project_id: str) -> Path:
    return paths.parse_dir(enterprise_id, project_id) / "work"


# ---------- 状态转换（短事务，全程不持有长连接） ----------


def _transition(
    factory: sessionmaker[Session],
    enterprise_id: str,
    project_id: str,
    target: state.ParseStatus,
    reason: str,
    **extra: Any,
) -> str:
    with factory() as session:
        scope = Scope(enterprise_id=enterprise_id)
        repo = ProjectRepository(session, scope)
        try:
            project = repo.get(project_id)
        except NotFoundError:
            raise ParseError("项目不存在") from None
        current = project.parse_status
        state.ensure_transition(current, target)  # type: ignore[arg-type]
        project.parse_status = target
        AppEventRepository(session, scope).record(
            "parse_state_change",
            project_id,
            {"from": current, "to": target, "reason": reason, **extra},
        )
        session.commit()
        return current


def _record_event(
    factory: sessionmaker[Session],
    enterprise_id: str,
    project_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    with factory() as session:
        AppEventRepository(session, Scope(enterprise_id=enterprise_id)).record(
            event_type, project_id, payload
        )
        session.commit()


# ---------- 源文件登记 ----------


def register_sources(
    factory: sessionmaker[Session],
    enterprise_id: str,
    project_id: str,
    files: list[dict[str, str]],
) -> dict[str, Any]:
    """把用户选择的本机文件复制入项目 source/ 并登记（TR-8.9 隔离存储）。"""
    with factory() as session:
        try:
            project = ProjectRepository(session, Scope(enterprise_id=enterprise_id)).get(project_id)
        except NotFoundError:
            raise ParseError("项目不存在") from None
        if project.parse_status == state.PARSING:
            raise JobRunningError("解析进行中，不能追加文件")
        was_parsed = project.parse_status == state.PARSED

    e_dir, p_dir = enterprise_id, project_id
    target_dir = paths.source_dir(e_dir, p_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    paths.ensure_within_project(paths.project_dir(e_dir, p_dir), target_dir)

    registered: list[dict[str, Any]] = []
    for item in files:
        src = Path(item["path"])
        if not src.is_file():
            raise ParseError(f"文件不存在或不可读：{item.get('name', item['path'])}")
        if src.suffix.lower() not in dedupe_mod.SUPPORTED_EXTS:
            raise ParseError(f"不支持的文件类型（仅 pdf/doc/docx）：{src.name}")
        safe_name = paths.safe_filename(item.get("name") or src.name)
        dest = paths.unique_path(target_dir / safe_name)
        paths.ensure_within_project(paths.project_dir(e_dir, p_dir), dest)
        shutil.copy2(src, dest)
        registered.append(
            {
                "stored_name": dest.name,
                "original_name": item.get("name") or src.name,
                "ext": dest.suffix.lower(),
                "size": dest.stat().st_size,
                "sha256": _sha256_of(dest),
                "registered_at": _now(),
            }
        )

    payload = _read_json(_sources_path(e_dir, p_dir), {"files": []})
    payload["files"].extend(registered)
    payload["updated_at"] = _now()
    _write_json(_sources_path(e_dir, p_dir), payload)

    # 新文件使既有解析产物失效：清 checkpoint/dedupe/chapters/extract/score/docx
    # （raw/work 重跑覆盖）
    ckpt = paths.checkpoints_dir(e_dir, p_dir) / f"{JOB_TYPE}.json"
    for stale in (
        ckpt,
        _dedupe_path(e_dir, p_dir),
        _chapters_path(e_dir, p_dir),
        paths.extract_list_path(e_dir, p_dir),
        paths.score_table_path(e_dir, p_dir),
        paths.docx_manifest_path(e_dir, p_dir),
    ):
        if stale.is_file():
            stale.unlink()
    stale_docx_dir = paths.docx_dir(e_dir, p_dir)
    if stale_docx_dir.is_dir():
        shutil.rmtree(stale_docx_dir)

    with factory() as session:
        project = ProjectRepository(session, Scope(enterprise_id=enterprise_id)).get(project_id)
        current = project.parse_status
        if current in (state.INIT, state.PARSED, state.UPLOADED):
            target = state.UPLOADED
            project.parse_status = target
            AppEventRepository(session, Scope(enterprise_id=enterprise_id)).record(
                "parse_state_change",
                project_id,
                {
                    "from": current,
                    "to": target,
                    "reason": "source_registered",
                    "files": [f["stored_name"] for f in registered],
                },
            )
        AppEventRepository(session, Scope(enterprise_id=enterprise_id)).record(
            "parse_sources_registered",
            project_id,
            {"files": [f["stored_name"] for f in registered], "reset_parse": was_parsed},
        )
        session.commit()

    return {"registered": registered, "total": len(payload["files"])}


# ---------- 内存任务管理（防同项目并发） ----------


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, asyncio.Task[None]] = {}
        self._task_ids: dict[str, str] = {}

    def is_running(self, enterprise_id: str, project_id: str) -> bool:
        task = self._jobs.get(self._key(enterprise_id, project_id))
        return task is not None and not task.done()

    @staticmethod
    def _key(enterprise_id: str, project_id: str) -> str:
        return f"{enterprise_id}:{project_id}"

    def start(
        self,
        enterprise_id: str,
        project_id: str,
        coro_factory: Callable[[str], Any],
    ) -> tuple[asyncio.Task[None], str]:
        """启动任务；coro_factory 接收生成的 task_id（用于取消信号注册）。"""
        key = self._key(enterprise_id, project_id)
        if self.is_running(enterprise_id, project_id):
            raise JobRunningError("该项目解析任务正在运行")
        task_id = uuid.uuid4().hex
        # 任务创建即注册取消信号，消除"协程尚未运行时取消返回 404"的竞态
        registry.register(task_id)
        task = asyncio.create_task(coro_factory(task_id))
        self._jobs[key] = task
        self._task_ids[key] = task_id

        def _cleanup(_t: asyncio.Task[None]) -> None:
            self._jobs.pop(key, None)
            self._task_ids.pop(key, None)

        task.add_done_callback(_cleanup)
        return task, task_id

    def task_id(self, enterprise_id: str, project_id: str) -> str | None:
        return self._task_ids.get(self._key(enterprise_id, project_id))


job_manager = JobManager()


# ---------- 解析计划（dedupe 阶段产物） ----------


def _load_sources(enterprise_id: str, project_id: str) -> list[SourceFile]:
    data = _read_json(_sources_path(enterprise_id, project_id), None)
    if not data or not data.get("files"):
        raise ParseError("项目尚未登记招标文件")
    src_dir = paths.source_dir(enterprise_id, project_id)
    result: list[SourceFile] = []
    for item in data["files"]:
        path = src_dir / item["stored_name"]
        if not path.is_file():
            raise ParseError(f"源文件缺失：{item['stored_name']}")
        result.append(SourceFile(path=path, stored_name=item["stored_name"]))
    return result


def _build_plan(sources: list[SourceFile]) -> dict[str, Any]:
    """分组 + 主格式选择，产出转换/解析预计划（内容判定在 verify 阶段）。"""
    groups = dedupe_mod.group_files(sources)
    plan_groups: list[dict[str, Any]] = []
    convert_needed: list[str] = []

    for stem, members in sorted(groups.items()):
        decision = dedupe_mod.plan_group(stem, members)
        primary = decision.primary
        # .doc 必须转 PDF（指纹 + MinerU 输入）
        for member in members:
            if member.ext == ".doc":
                convert_needed.append(member.stored_name)
        # 多文件组中的 .docx 需转 PDF 供同内容指纹（无论主格式/候选）；
        # 单文件 docx 直进 MinerU，不转换
        if decision.candidates:
            for member in members:
                if member.ext == ".docx":
                    convert_needed.append(member.stored_name)
        plan_groups.append(
            {
                "stem": stem,
                "members": [m.stored_name for m in members],
                "primary": primary.stored_name,
                "primary_ext": primary.ext,
                "candidates": [c.stored_name for c in decision.candidates],
            }
        )

    return {"groups": plan_groups, "convert_needed": sorted(set(convert_needed))}


def _work_pdf_name(stored_name: str) -> str:
    return f"{Path(stored_name).stem}.pdf"


# ---------- 主流水线 ----------


async def run_parse(
    factory: sessionmaker[Session],
    enterprise_id: str,
    project_id: str,
    task_id: str,
    *,
    reparse: bool,
    emit: ProgressSink,
    api_key: str | None = None,
) -> None:
    """执行（或断点续跑）解析。emit 推送 SSE 事件 dict；终态由本函数推送。

    api_key：LLM 校验模式（Task 10）的云端 Key，仅当项目配置启用
    llm_enabled 且 mode=validate 时使用；纯规则路径忽略。
    """
    eid, pid = enterprise_id, project_id
    ckpt_path = paths.checkpoints_dir(eid, pid) / f"{JOB_TYPE}.json"
    cancel_event = registry.register(task_id)
    try:
        sources = _load_sources(eid, pid)

        if reparse and ckpt_path.is_file():
            ckpt_path.unlink()

        store = CheckpointStore.load_or_create(
            ckpt_path, JOB_TYPE, {"dedupe": "同名多格式去重分析"}
        )
        store.reset_pending()

        # Task 10 要素层 checkpoint 项：extract:coarse 恒有（确定性）；
        # extract:llm 仅 LLM 总开关开启且为校验模式时注册（TR-10.9：
        # dual_channel 推迟，按默认路径不调 LLM）
        cfg = _load_parse_config(factory, eid, pid)
        store._add_new_items({"extract:coarse": "规则粗分要素提取（规则库）"})
        # Task 11：评分办法解析（恒有，依赖 extract:coarse 产出的评分章节）
        store._add_new_items({"score:extract": "评分办法结构化抽取（规则库）"})
        if cfg.llm_enabled and cfg.llm_mode == parse_config.LLM_VALIDATE:
            store._add_new_items({"extract:llm": "LLM 校验（校验模式）"})
            store._add_new_items({"score:llm": "评分表 LLM 专项校验（校验模式）"})

        _transition(factory, eid, pid, state.PARSING, reason="parse_started")
        emit({"stage": "progress", "percent": 0, "message": "解析任务开始"})

        # ---- stage 1: dedupe 分组计划 ----
        if store.get("dedupe").state != "success":
            _check_cancel(cancel_event)
            store.mark_running("dedupe")
            try:
                plan = _build_plan(sources)
                store.mark_success("dedupe", plan)
                emit(
                    {
                        "stage": "progress",
                        "percent": _W_DEDUPE,
                        "message": f"去重分析完成：{len(plan['groups'])} 组文件",
                        "extra": {"groups": len(plan["groups"])},
                    }
                )
            except Exception as exc:
                store.mark_error("dedupe", str(exc))
                raise
        plan = store.get("dedupe").output or _build_plan(sources)

        # ---- stage 2: 预处理（按需转 PDF） ----
        convert_labels = {
            f"preprocess:{name}": f"格式转换：{name}" for name in plan["convert_needed"]
        }
        store._add_new_items(convert_labels)
        pre_items = [k for k in store.items if k.startswith("preprocess:")]
        work = _work_dir(eid, pid)
        work.mkdir(parents=True, exist_ok=True)
        src_dir = paths.source_dir(eid, pid)
        for i, key in enumerate(pre_items):
            if store.get(key).state == "success":
                continue
            _check_cancel(cancel_event)
            stored = key.split(":", 1)[1]
            store.mark_running(key)
            try:
                out_pdf = await preprocess.convert_to_pdf(
                    src_dir / stored, work, cancel_event=cancel_event
                )
                fp = await asyncio.to_thread(dedupe_mod.pdf_text_fingerprint, out_pdf)
                store.mark_success(
                    key,
                    {"pdf": out_pdf.name, "pages": fp["pages"], "chars": fp["chars"]},
                )
                emit(
                    {
                        "stage": "progress",
                        "percent": _w_between(_W_DEDUPE, _W_PREPROCESS_END, i, len(pre_items)),
                        "message": f"已转换：{stored} → PDF（{fp['pages']} 页）",
                    }
                )
            except asyncio.CancelledError:
                store.mark_error(key, "用户取消")
                raise
            except Exception as exc:
                store.mark_error(key, str(exc))
                raise

        # ---- stage 3: 同内容验证 + 制定最终解析清单 ----
        store._add_new_items({"dedupe-verify": "同名文件同内容验证"})
        if store.get("dedupe-verify").state != "success":
            _check_cancel(cancel_event)
            store.mark_running("dedupe-verify")
            try:
                verify = await _verify_groups(eid, pid, plan, store, src_dir, work)
                store.mark_success("dedupe-verify", verify["output"])
                _write_json(_dedupe_path(eid, pid), verify["report"])
            except Exception as exc:
                store.mark_error("dedupe-verify", str(exc))
                raise
        verify_output = store.get("dedupe-verify").output or {}
        parse_files = {f["key"]: f for f in verify_output.get("parse_files", [])}
        emit(
            {
                "stage": "progress",
                "percent": _W_VERIFY_END,
                "message": _verify_message(verify_output),
            }
        )

        # 最终解析输入由 verify 阶段确定并持久化（mineru:<key> 项）
        parse_items = [k for k in store.items if k.startswith("mineru:")]
        if not parse_items:
            raise ParseError("去重验证后没有可解析的文件（请检查同名文件内容比对结果）")

        # ---- stage 4: MinerU 逐文件解析 ----
        proj_dir = paths.project_dir(eid, pid)
        for i, key in enumerate(parse_items):
            if store.get(key).state == "success":
                continue
            _check_cancel(cancel_event)
            file_info = parse_files.get(key.split(":", 1)[1])
            if file_info is None:
                raise ParseError(f"解析项缺少输入映射：{key}")
            stored = file_info["stored_name"]
            input_path = proj_dir / file_info["input"]
            label = file_info["label"]
            store.mark_running(key)
            raw = paths.raw_dir(eid, pid)
            raw.mkdir(parents=True, exist_ok=True)

            def _on_log(line: str, _i: int = i, _label: str = label, _k: str = key) -> None:
                emit(
                    {
                        "stage": "progress",
                        "percent": _w_between(_W_VERIFY_END, _W_MINERU_END, _i, len(parse_items)),
                        "message": f"[{_label}] {line[-120:]}",
                        "extra": {"item": _k},
                    }
                )

            try:
                result = await engine.run_mineru(
                    input_path,
                    raw,
                    cancel_event=cancel_event,
                    on_log=_on_log,
                )
                store.mark_success(
                    key,
                    {
                        "stored_name": stored,
                        "input": str(input_path.name),
                        "markdown": str(
                            result.markdown_path.relative_to(paths.project_dir(eid, pid))
                        ),
                        "content_list": (
                            str(result.content_list_path.relative_to(paths.project_dir(eid, pid)))
                            if result.content_list_path
                            else None
                        ),
                        "middle_json": (
                            str(result.middle_json_path.relative_to(paths.project_dir(eid, pid)))
                            if result.middle_json_path
                            else None
                        ),
                    },
                )
                emit(
                    {
                        "stage": "progress",
                        "percent": _w_between(
                            _W_VERIFY_END, _W_MINERU_END, i + 1, len(parse_items)
                        ),
                        "message": f"MinerU 解析完成：{label}",
                    }
                )
            except asyncio.CancelledError:
                store.mark_error(key, "用户取消")
                raise
            except Exception as exc:
                store.mark_error(key, str(exc))
                raise

        # ---- stage 5: 章节切分 ----
        chapter_items = [k for k in store.items if k.startswith("chapters:")]
        for i, key in enumerate(chapter_items):
            if store.get(key).state == "success":
                continue
            _check_cancel(cancel_event)
            mineru_key = "mineru:" + key.split(":", 1)[1]
            mineru_out = store.get(mineru_key).output
            if not mineru_out or not mineru_out.get("content_list"):
                raise ParseError(f"{mineru_key} 缺少成功产物，请重试该解析项")
            store.mark_running(key)
            try:
                content_list_rel = mineru_out["content_list"]
                cl_path = proj_dir / content_list_rel
                source_stem = Path(str(mineru_out["input"])).stem
                chapter_result = await asyncio.to_thread(
                    chapters_mod.split_chapters_from_file, cl_path, source_stem
                )
                _merge_chapters(eid, pid, source_stem, chapter_result)
                store.mark_success(
                    key,
                    {
                        "source_stem": source_stem,
                        "chapter_count": chapter_result["stats"]["chapter_count"],
                        "section_count": chapter_result["stats"]["section_count"],
                    },
                )
                emit(
                    {
                        "stage": "progress",
                        "percent": _w_between(
                            _W_MINERU_END, _W_CHAPTERS_END, i + 1, len(chapter_items)
                        ),
                        "message": f"章节切分完成：{source_stem}"
                        f"（{chapter_result['stats']['chapter_count']} 章）",
                    }
                )
            except Exception as exc:
                store.mark_error(key, str(exc))
                raise

        # ---- stage 6: 规则粗分（Task 10，确定性，恒有） ----
        if store.get("extract:coarse").state != "success":
            _check_cancel(cancel_event)
            store.mark_running("extract:coarse")
            try:
                coarse_out = await _run_extract_coarse(factory, eid, pid, store, cfg)
                store.mark_success("extract:coarse", coarse_out)
                emit(
                    {
                        "stage": "progress",
                        "percent": _W_EXTRACT_END,
                        "message": (
                            f"规则粗分完成：{coarse_out['items_extracted']}"
                            f"/{coarse_out['items_total']} 项匹配"
                            + (
                                f"，{coarse_out['red_flags']} 条标红"
                                if coarse_out["red_flags"]
                                else ""
                            )
                        ),
                    }
                )
            except Exception as exc:
                store.mark_error("extract:coarse", str(exc))
                raise

        # ---- stage 7: 评分办法结构化抽取（Task 11，确定性，恒有） ----
        if store.get("score:extract").state != "success":
            _check_cancel(cancel_event)
            store.mark_running("score:extract")
            try:
                score_out = await _run_score_extract(eid, pid)
                store.mark_success("score:extract", score_out)
                emit(
                    {
                        "stage": "progress",
                        "percent": _W_SCORE_END,
                        "message": (
                            f"评分办法解析完成：{score_out['categories']} 大类，"
                            f"合计 {score_out['total_score']:g} 分"
                            + (
                                f"，{score_out['red_flags']} 条标红"
                                if score_out["red_flags"]
                                else ""
                            )
                        ),
                    }
                )
            except Exception as exc:
                # 评分解析失败不阻塞整跑：标 error + 留痕，终态仅其成功才升 SCORE_PARSED
                store.mark_error("score:extract", str(exc))
                _record_event(
                    factory, eid, pid, "parse_score_extract_error", {"error": str(exc)[:500]}
                )
                emit(
                    {
                        "stage": "progress",
                        "percent": _W_SCORE_END,
                        "message": f"评分办法解析失败（不影响要素提取结果）：{str(exc)[:120]}",
                    }
                )

        # ---- stage 8: 投标文件格式章节化 docx（Task 12，确定性，按章失败不阻塞） ----
        try:
            docx_plans = await asyncio.to_thread(_plan_docx, eid, pid, store)
            docx_sections = [s for p in docx_plans for s in p.sections]
            content_lists = _content_lists_from_store(store, eid, pid)
            total_docx = len(docx_sections)
            if total_docx == 0:
                emit(
                    {
                        "stage": "progress",
                        "percent": _W_DOCX_END,
                        "message": "未识别到「投标文件格式」章节，跳过 docx 章节化（可人工核对）",
                    }
                )
            for i, section in enumerate(docx_sections):
                key = section.checkpoint_key
                if store.get(key).state == "success":
                    continue
                _check_cancel(cancel_event)
                store.mark_running(key)
                try:
                    record = await asyncio.to_thread(
                        docx_build.render_section,
                        section,
                        content_lists,
                        paths.project_dir(eid, pid),
                        paths.docx_dir(eid, pid),
                    )
                    store.mark_success(key, record)
                    emit(
                        {
                            "stage": "progress",
                            "percent": _w_between(_W_SCORE_END, _W_DOCX_END, i + 1, total_docx),
                            "message": (
                                f"格式章节已导出：{record['file']}"
                                + (
                                    f"（{record['red_flags']} 处需对照原文件）"
                                    if record["red_flags"]
                                    else ""
                                )
                            ),
                        }
                    )
                except asyncio.CancelledError:
                    store.mark_error(key, "用户取消")
                    raise
                except Exception as exc:
                    # 单章失败：标 error + 留痕，其余章继续（TR-12.7 可单项重试）
                    store.mark_error(key, str(exc))
                    _record_event(
                        factory,
                        eid,
                        pid,
                        "parse_docx_error",
                        {"item": key, "error": str(exc)[:500]},
                    )
                    emit(
                        {
                            "stage": "progress",
                            "percent": _w_between(_W_SCORE_END, _W_DOCX_END, i + 1, total_docx),
                            "message": f"格式章节导出失败（不影响其他章节）：{section.title}",
                        }
                    )
            await asyncio.to_thread(_write_docx_manifest, eid, pid, docx_plans, store)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # 规划/manifest 级别异常不阻塞解析主线
            _record_event(factory, eid, pid, "parse_docx_stage_error", {"error": str(exc)[:500]})
            emit(
                {
                    "stage": "progress",
                    "percent": _W_DOCX_END,
                    "message": f"投标文件格式章节化失败（不影响解析结果）：{str(exc)[:120]}",
                }
            )

        # ---- stage 9: LLM 校验（Task 10，仅校验模式；失败不阻塞 PARSED） ----
        if "extract:llm" in store.items and store.get("extract:llm").state != "success":
            _check_cancel(cancel_event)
            store.mark_running("extract:llm")
            try:
                llm_out = await _run_extract_llm(factory, eid, pid, store, api_key, emit)
                store.mark_success("extract:llm", llm_out)
                emit(
                    {
                        "stage": "progress",
                        "percent": 99,
                        "message": f"LLM 校验完成：{llm_out['validated']} 项已校验",
                    }
                )
            except Exception as exc:
                # LLM 为可选增强：失败只标记该项 error + app_event，整跑仍 PARSED
                store.mark_error("extract:llm", str(exc))
                _record_event(
                    factory, eid, pid, "parse_extract_llm_error", {"error": str(exc)[:500]}
                )
                emit(
                    {
                        "stage": "progress",
                        "percent": 99,
                        "message": f"LLM 校验失败（不影响规则粗分结果）：{str(exc)[:120]}",
                    }
                )

        # ---- stage 10: 评分表 LLM 专项校验（Task 11，仅校验模式；失败不阻塞） ----
        if "score:llm" in store.items and store.get("score:llm").state != "success":
            _check_cancel(cancel_event)
            store.mark_running("score:llm")
            try:
                score_llm_out = await _run_score_llm(factory, eid, pid, store, api_key)
                store.mark_success("score:llm", score_llm_out)
                emit(
                    {
                        "stage": "progress",
                        "percent": 100,
                        "message": "评分表 LLM 专项校验完成",
                    }
                )
            except Exception as exc:
                store.mark_error("score:llm", str(exc))
                _record_event(factory, eid, pid, "parse_score_llm_error", {"error": str(exc)[:500]})
                emit(
                    {
                        "stage": "progress",
                        "percent": 100,
                        "message": f"评分表 LLM 校验失败：{str(exc)[:120]}",
                    }
                )

        # 终态：score:extract 成功 → SCORE_PARSED；否则退回到 PARSED（为兼容）
        score_item = store.get("score:extract")
        if score_item and score_item.state == "success":
            _transition(factory, eid, pid, state.SCORE_PARSED, reason="score_extract_completed")
            emit(
                {
                    "stage": "completed",
                    "percent": 100,
                    "message": "招标文件解析完成（含评分办法）",
                    "extra": {"checkpoint": store.summary()["state"]},
                }
            )
        else:
            _transition(factory, eid, pid, state.PARSED, reason="parse_completed")
            emit(
                {
                    "stage": "completed",
                    "percent": 100,
                    "message": "招标文件解析完成",
                    "extra": {"checkpoint": store.summary()["state"]},
                }
            )
    except asyncio.CancelledError:
        _safe_transition(factory, eid, pid, state.UPLOADED, "parse_cancelled")
        emit(
            {
                "stage": "cancelled",
                "percent": 0,
                "message": "解析任务已取消（已完成项结果保留，可续跑）",
            }
        )
    except Exception as exc:
        _safe_transition(factory, eid, pid, state.UPLOADED, f"parse_failed: {exc}"[:200])
        _record_event(factory, eid, pid, "parse_error", {"error": str(exc)[:1000]})
        emit({"stage": "failed", "percent": 0, "message": f"解析失败：{exc}"[:500]})
    finally:
        registry.discard(task_id)


def _check_cancel(cancel_event: asyncio.Event) -> None:
    if cancel_event.is_set():
        raise asyncio.CancelledError("用户取消")


# ---------- Task 10：要素提取（规则粗分 + LLM 校验） ----------


def _load_parse_config(
    factory: sessionmaker[Session], enterprise_id: str, project_id: str
) -> parse_config.ParseConfig:
    """读取项目级解析配置；未保存/损坏回退默认（配置 API 已保证合法性）。"""
    with factory() as session:
        payload = ParseConfigRepository(session, Scope(enterprise_id=enterprise_id)).get_payload(
            project_id
        )
    try:
        return parse_config.from_payload(payload)
    except parse_config.ConfigError:
        return parse_config.default_config()


def _content_lists_from_store(
    store: CheckpointStore, enterprise_id: str, project_id: str
) -> dict[str, list[dict[str, Any]]]:
    """从成功的 mineru 项收集 {source_stem: content_list 块数组}。"""
    proj_dir = paths.project_dir(enterprise_id, project_id)
    out: dict[str, list[dict[str, Any]]] = {}
    for key, item in store.items.items():
        if not key.startswith("mineru:") or item.state != "success" or not item.output:
            continue
        cl_rel = item.output.get("content_list")
        if not cl_rel:
            continue
        stem = Path(str(item.output.get("input", key))).stem
        out[stem] = chapters_mod.load_content_list(proj_dir / str(cl_rel))
    return out


def _full_markdown_from_store(store: CheckpointStore, enterprise_id: str, project_id: str) -> str:
    """合并全部 mineru markdown（LLM 校验的公共前缀，BP-10）。"""
    proj_dir = paths.project_dir(enterprise_id, project_id)
    parts: list[str] = []
    for key, item in store.items.items():
        if not key.startswith("mineru:") or item.state != "success" or not item.output:
            continue
        md_rel = item.output.get("markdown")
        if not md_rel:
            continue
        md_path = proj_dir / str(md_rel)
        if md_path.is_file():
            parts.append(md_path.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


async def _run_extract_coarse(
    factory: sessionmaker[Session],
    enterprise_id: str,
    project_id: str,
    store: CheckpointStore,
    cfg: parse_config.ParseConfig,
) -> dict[str, Any]:
    """规则粗分（纯确定性）：产出 extract_list.json，返回 checkpoint output。"""
    chapters_payload = _read_json(_chapters_path(enterprise_id, project_id), {"sources": []})
    content_lists = _content_lists_from_store(store, enterprise_id, project_id)
    selected = {k for k, v in cfg.items.items() if v}

    llm_info: dict[str, Any] = {
        "enabled": cfg.llm_enabled,
        "mode": cfg.llm_mode if cfg.llm_enabled else None,
        "status": "not_run",
    }
    if cfg.llm_enabled and cfg.llm_mode == parse_config.LLM_DUAL_CHANNEL:
        # TR-10.9：双通道推迟到后续迭代，按默认路径执行并注明
        llm_info["status"] = "deferred"
        llm_info["note"] = "双通道模式推迟到后续迭代，本次按默认路径（纯规则）执行，未调用 LLM"
    elif cfg.llm_enabled and cfg.llm_mode == parse_config.LLM_VALIDATE:
        llm_info["status"] = "pending"

    payload = await asyncio.to_thread(
        rules_extract.run_extraction,
        chapters_payload,
        content_lists,
        selected,
        generated_at=_now(),
        llm_info=llm_info,
    )
    _write_json(paths.extract_list_path(enterprise_id, project_id), payload)

    # 术语动态词典（<data_root>/config/keywords.dict.json，项目间共享累积）
    dict_path = paths.data_root() / "config" / "keywords.dict.json"
    existing = _read_json(dict_path, {"version": 1, "history": []})
    entry = {"project_id": project_id, "at": _now(), **payload["doc_type"]["terms"]}
    history = [h for h in existing.get("history", []) if h.get("project_id") != project_id]
    history.append(entry)
    _write_json(dict_path, {"version": 1, "updated_at": _now(), "history": history})

    found = sum(1 for i in payload["items"] if i["status"] == "found")
    return {
        "doc_type": payload["doc_type"]["type"],
        "items_total": sum(1 for i in payload["items"] if i["selected"]),
        "items_extracted": found,
        "red_flags": len(payload["red_flags"]),
        "rules_version": payload["rules_version"],
    }


async def _run_extract_llm(
    factory: sessionmaker[Session],
    enterprise_id: str,
    project_id: str,
    store: CheckpointStore,
    api_key: str | None,
    emit: ProgressSink,
) -> dict[str, Any]:
    """LLM 校验模式（TR-10.6/10.7/10.8）：预热 → 并发校验 → 全文审计。

    失败抛异常由调用方标记 extract:llm error（不阻塞整跑 PARSED）。
    """
    with factory() as session:
        kv = ConfigKVRepository(session)
        base_url = kv.get_value("system", "llm.base_url")
        model = kv.get_value("system", "llm.model")
    if not api_key:
        raise ParseError("已启用 LLM 校验模式，但未提供 API Key（请在模型配置中保存后重试）")
    if not base_url or not model:
        raise ParseError("已启用 LLM 校验模式，但模型配置不完整（base_url/model 未设置）")

    extract_path = paths.extract_list_path(enterprise_id, project_id)
    payload = _read_json(extract_path, None)
    if payload is None:
        raise ParseError("规则粗分结果缺失，请先从 extract:coarse 重试")

    full_markdown = _full_markdown_from_store(store, enterprise_id, project_id)
    items = payload["items"]
    selected = [i for i in items if i.get("selected")]

    # BP-10：先单跑"项目概述"预热缓存，再并发其余项
    overview = next((i for i in selected if i["key"] == "project_overview"), None)
    if overview is not None:
        snippet = overview["matches"][0]["snippet"] if overview["matches"] else ""
        warm = await asyncio.to_thread(
            llm_validate.validate_item,
            overview["key"],
            overview["label"],
            full_markdown,
            snippet,
            base_url,
            model,
            api_key,
            factory,
            project_id,
        )
        overview["llm"] = warm
        emit(
            {
                "stage": "progress",
                "percent": _W_EXTRACT_END + 1,
                "message": "LLM 缓存预热完成（项目概述），并发校验其余项…",
            }
        )
        await asyncio.sleep(_LLM_CACHE_WARMUP_WAIT)

    others = [i for i in selected if i["key"] != "project_overview"]
    sem = asyncio.Semaphore(_LLM_CONCURRENCY)

    async def _one(item: dict[str, Any]) -> None:
        async with sem:
            snippet = item["matches"][0]["snippet"] if item["matches"] else ""
            item["llm"] = await asyncio.to_thread(
                llm_validate.validate_item,
                item["key"],
                item["label"],
                full_markdown,
                snippet,
                base_url,
                model,
                api_key,
                factory,
                project_id,
            )

    if others:
        await asyncio.gather(*(_one(i) for i in others))

    # TR-10.7：全文摘要审计（大类数量比对查漏）
    audit = await asyncio.to_thread(
        llm_validate.audit_gap, full_markdown, items, base_url, model, api_key, factory, project_id
    )

    payload["llm"] = {
        "enabled": True,
        "mode": parse_config.LLM_VALIDATE,
        "status": "done",
        "validated": len(selected),
        "audit": audit,
    }
    _write_json(extract_path, payload)
    return {"validated": len(selected), "audit_status": audit["status"]}


async def _run_score_extract(enterprise_id: str, project_id: str) -> dict[str, Any]:
    """评分办法结构化抽取（Task 11，纯确定性）：产出 score_table.json。

    依赖 extract_list.json 中 tech_score/business_score 的 matches（评分章节）。
    产出后立即做 Schema 硬校验（TR-11.6），写入 schema_validated 标志位。
    """
    extract_payload = _read_json(paths.extract_list_path(enterprise_id, project_id), None)
    if extract_payload is None:
        raise ParseError("规则粗分结果缺失，请先从 extract:coarse 重试")

    # 收集评分章节 matches（tech_score + business_score）
    score_matches: list[dict[str, Any]] = []
    for item in extract_payload.get("items", []):
        if item.get("key") in ("tech_score", "business_score") and item.get("matches"):
            score_matches.extend(item["matches"])

    payload = await asyncio.to_thread(
        scoring_extract.extract_score_table, score_matches, generated_at=_now()
    )

    # TR-11.6：Schema 硬校验门禁（通过写标志位，失败标红进修复循环）
    ok, errors = await asyncio.to_thread(scoring_schema.validate_score_table, payload)
    if not ok:
        payload.setdefault("red_flags", []).append(
            {
                "type": "schema_invalid",
                "detail": "score_table.json 未通过 Schema 硬校验，需人工修正",
                "errors": errors[:20],
            }
        )
    _write_json(paths.score_table_path(enterprise_id, project_id), payload)

    total = payload["total_score_check"]["actual"]
    return {
        "categories": len(payload["categories"]),
        "total_score": total,
        "score_ok": payload["total_score_check"]["ok"],
        "red_flags": len(payload["red_flags"]),
        "schema_validated": ok,
    }


async def _run_score_llm(
    factory: sessionmaker[Session],
    enterprise_id: str,
    project_id: str,
    store: CheckpointStore,
    api_key: str | None,
) -> dict[str, Any]:
    """评分表 LLM 专项校验（TR-11.7）：完整性/合计/门槛遗漏。失败抛异常由调用方标记。"""
    with factory() as session:
        kv = ConfigKVRepository(session)
        base_url = kv.get_value("system", "llm.base_url")
        model = kv.get_value("system", "llm.model")
    if not api_key:
        raise ParseError("已启用 LLM 校验模式，但未提供 API Key（请在模型配置中保存后重试）")
    if not base_url or not model:
        raise ParseError("已启用 LLM 校验模式，但模型配置不完整（base_url/model 未设置）")

    score_path = paths.score_table_path(enterprise_id, project_id)
    score_payload = _read_json(score_path, None)
    if score_payload is None:
        raise ParseError("评分表结果缺失，请先从 score:extract 重试")

    # 评分办法原文片段（取 extract_list.json 中评分章节 snippet 拼接）
    extract_payload = _read_json(paths.extract_list_path(enterprise_id, project_id), {})
    snippets = [
        str(m.get("snippet", ""))
        for item in extract_payload.get("items", [])
        if item.get("key") in ("tech_score", "business_score")
        for m in (item.get("matches") or [])
    ]
    score_snippet = "\n\n".join(snippets)[:4000]

    result = await asyncio.to_thread(
        score_llm.validate_score,
        score_payload,
        score_snippet,
        base_url,
        model,
        api_key,
        factory,
        project_id,
    )
    score_payload["llm"] = {
        "enabled": True,
        "mode": parse_config.LLM_VALIDATE,
        "status": "done" if result["status"] == "ok" else "error",
        "check": result.get("data"),
        "error": result.get("error"),
    }
    _write_json(score_path, score_payload)
    return {"status": result["status"]}


def _safe_transition(
    factory: sessionmaker[Session],
    eid: str,
    pid: str,
    target: state.ParseStatus,
    reason: str,
) -> None:
    """失败/取消回退状态；非法转换（如 INIT 态）只记录事件，不掩盖原始异常。"""
    try:
        _transition(factory, eid, pid, target, reason=reason)
    except Exception:
        pass


# ---------- Task 12：投标文件格式章节化 docx ----------


def _plan_docx(
    enterprise_id: str, project_id: str, store: CheckpointStore
) -> list[docx_build.SourcePlan]:
    """读 chapters.json + MinerU content_list 制定逐章计划，并动态注册 checkpoint 项。"""
    chapters_payload = _read_json(_chapters_path(enterprise_id, project_id), {"sources": []})
    content_lists = _content_lists_from_store(store, enterprise_id, project_id)
    plans = docx_build.plan_all_sources(chapters_payload, content_lists)
    labels: dict[str, str] = {}
    for plan in plans:
        for section in plan.sections:
            labels[section.checkpoint_key] = (
                "投标文件封面导出（docx）"
                if section.kind == "cover"
                else f"格式章节导出（docx）：{section.title}"
            )
    store._add_new_items(labels)
    return plans


def _write_docx_manifest(
    enterprise_id: str,
    project_id: str,
    plans: list[docx_build.SourcePlan],
    store: CheckpointStore,
) -> dict[str, Any]:
    """按 checkpoint 实际状态回填文件清单并写 manifest.json（断点可重建）。"""
    manifest = docx_build.assemble_manifest(plans, _now())
    completed = True
    for src in manifest["sources"]:
        files: list[dict[str, Any]] = []
        for section in src["sections"]:
            key = str(section["checkpoint_key"])
            item = store.items.get(key)
            entry: dict[str, Any] = {k: v for k, v in section.items() if k != "checkpoint_key"}
            if item is not None and item.state == "success" and item.output:
                entry.update({"state": "success", **item.output})
            else:
                completed = False
                entry["state"] = item.state if item is not None else "idle"
                entry["error"] = item.error if item is not None else None
            files.append(entry)
        src["files"] = files
    manifest["completed"] = completed
    _write_json(paths.docx_manifest_path(enterprise_id, project_id), manifest)
    return manifest


def _w_between(start: int, end: int, done: int, total: int) -> int:
    if total <= 0:
        return end
    return min(end, start + round((end - start) * done / total))


def _verify_message(verify_output: dict[str, Any]) -> str:
    if not verify_output:
        return "同内容验证完成"
    dropped = verify_output.get("dropped", 0)
    mismatches = verify_output.get("mismatches", 0)
    parts = ["同内容验证完成"]
    if dropped:
        parts.append(f"去重 {dropped} 个同名副本")
    if mismatches:
        parts.append(f"{mismatches} 组同名内容不一致（已保留并披露）")
    return "，".join(parts)


async def _verify_groups(
    eid: str,
    pid: str,
    plan: dict[str, Any],
    store: CheckpointStore,
    src_dir: Path,
    work: Path,
) -> dict[str, Any]:
    """逐组做同内容判定，确定最终解析输入，动态注册 mineru/chapters item。"""

    def _fingerprint(stored: str, ext: str) -> dict[str, Any]:
        if ext == ".pdf":
            return dedupe_mod.pdf_text_fingerprint(src_dir / stored)
        pre_item = store.get(f"preprocess:{stored}")
        if not pre_item.output or not pre_item.output.get("pdf"):
            raise ParseError(f"预处理结果缺失：{stored}")
        return dedupe_mod.pdf_text_fingerprint(work / str(pre_item.output["pdf"]))

    report_groups: list[dict[str, Any]] = []
    all_dropped: list[dict[str, Any]] = []
    all_mismatches: list[dict[str, Any]] = []
    # 最终送入 MinerU 的文件（持久化进 checkpoint，保证续跑一致）：
    # {key, stored_name, input(相对项目目录), label}
    proj_dir = paths.project_dir(eid, pid)
    parse_files: list[dict[str, str]] = []
    mm_index = 0

    for group in plan["groups"]:
        g_members = [SourceFile(path=src_dir / name, stored_name=name) for name in group["members"]]
        primary = next(m for m in g_members if m.stored_name == group["primary"])
        candidates = [m for m in g_members if m.stored_name != primary.stored_name]

        dropped: list[dict[str, Any]] = []
        mismatch_members: list[str] = []
        if candidates:
            fp_primary = await asyncio.to_thread(_fingerprint, primary.stored_name, primary.ext)
            kept_candidates: list[SourceFile] = []
            for cand in candidates:
                fp_cand = await asyncio.to_thread(_fingerprint, cand.stored_name, cand.ext)
                if dedupe_mod.same_content(fp_primary, fp_cand):
                    record = dedupe_mod.make_drop_record(
                        cand, primary, "同名多格式同内容文件，保留主格式（docx>doc>pdf）"
                    )
                    dropped.append(asdict(record))
                else:
                    kept_candidates.append(cand)
                    mismatch_members.append(cand.stored_name)
            all_dropped.extend(dropped)
            if kept_candidates:
                all_mismatches.append(
                    {
                        "stem": group["stem"],
                        "members": mismatch_members + [primary.stored_name],
                        "reason": "同名文件内容不一致，全部保留待人工确认",
                    }
                )
        else:
            kept_candidates = []

        # 主格式输入：pdf/docx 用源文件，doc 用 work 中转换出的 PDF
        primary_input = (
            work / _work_pdf_name(primary.stored_name) if primary.ext == ".doc" else primary.path
        )
        parse_files.append(
            {
                "key": primary_input.stem,
                "stored_name": primary.stored_name,
                "input": str(primary_input.resolve().relative_to(proj_dir)),
                "label": primary.stored_name,
            }
        )
        # 内容不一致的候选：复制到 work 唯一名后解析（避免 MinerU 同名输出目录冲突）
        for cand in kept_candidates:
            mm_index += 1
            target = work / f"{cand.path.stem}-mm{mm_index}.pdf"
            if cand.ext == ".pdf":
                if not target.is_file():
                    shutil.copy2(cand.path, target)
            else:
                # doc/docx 候选在 preprocess 已产出 <stem>.pdf；改名为 mm 版
                pre_pdf = work / _work_pdf_name(cand.stored_name)
                if pre_pdf.is_file() and not target.is_file():
                    pre_pdf.rename(target)
            parse_files.append(
                {
                    "key": target.stem,
                    "stored_name": cand.stored_name,
                    "input": str(target.resolve().relative_to(proj_dir)),
                    "label": f"{cand.stored_name}（同名内容不一致）",
                }
            )

        report_groups.append(
            {
                "stem": group["stem"],
                "primary": primary.stored_name,
                "members": group["members"],
                "dropped": dropped,
                "mismatch_members": mismatch_members,
            }
        )

    # 动态注册 mineru/chapters checkpoint 项
    labels: dict[str, str] = {}
    for item in parse_files:
        labels[f"mineru:{item['key']}"] = f"MinerU 解析：{item['label']}"
        labels[f"chapters:{item['key']}"] = f"章节切分：{item['label']}"
    store._add_new_items(labels)

    report = {
        "generated_at": _now(),
        "groups": report_groups,
        "dropped": all_dropped,
        "mismatches": all_mismatches,
        "note": "去重项内部消化，不入解析清单/风险清单；同名内容不一致者全部保留待人工确认",
    }
    output = {
        "groups": len(report_groups),
        "dropped": len(all_dropped),
        "mismatches": len(all_mismatches),
        "parse_files": parse_files,
    }
    return {"report": report, "output": output}


def _merge_chapters(eid: str, pid: str, source_stem: str, result: dict[str, Any]) -> None:
    """把单个源文件的章节切分结果汇总进 chapters.json（断点可重入）。"""
    path = _chapters_path(eid, pid)
    payload = _read_json(path, {"sources": []})
    payload["sources"] = [s for s in payload["sources"] if s.get("source_stem") != source_stem]
    payload["sources"].append(result)
    payload["updated_at"] = _now()
    _write_json(path, payload)


# ---------- 状态查询 ----------


def _extract_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    items = payload.get("items") or []
    selected = [i for i in items if i.get("selected")]
    return {
        "doc_type": payload.get("doc_type", {}).get("type"),
        "items_total": len(selected),
        "items_extracted": sum(1 for i in selected if i.get("status") == "found"),
        "red_flags": len(payload.get("red_flags", [])),
        "llm": payload.get("llm"),
    }


def _score_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return {
        "categories": len(payload.get("categories", [])),
        "total_score": payload.get("total_score_check", {}).get("actual"),
        "score_ok": payload.get("total_score_check", {}).get("ok"),
        "red_flags": len(payload.get("red_flags", [])),
        "schema_validated": payload.get("schema_validated"),
        "llm": payload.get("llm"),
    }


def _docx_summary(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    sources = payload.get("sources", [])
    files = [f for src in sources for f in src.get("files", [])]
    return {
        "sources": len(sources),
        "files": len(files),
        "cover": any(f.get("kind") == "cover" and f.get("state") == "success" for f in files),
        "completed": payload.get("completed"),
        "errors": sum(1 for f in files if f.get("state") == "error"),
        "red_flags": sum(int(f.get("red_flags", 0)) for f in files if f.get("state") == "success"),
        "missing_format_sources": [
            str(s.get("source_stem")) for s in sources if not s.get("found")
        ],
    }


def get_status(
    factory: sessionmaker[Session],
    enterprise_id: str,
    project_id: str,
) -> dict[str, Any]:
    with factory() as session:
        try:
            project = ProjectRepository(session, Scope(enterprise_id=enterprise_id)).get(project_id)
        except NotFoundError:
            raise ParseError("项目不存在") from None
        parse_status = project.parse_status

    ckpt_path = paths.checkpoints_dir(enterprise_id, project_id) / f"{JOB_TYPE}.json"
    checkpoint = None
    if ckpt_path.is_file():
        checkpoint = CheckpointStore.load_or_create(
            ckpt_path, JOB_TYPE, {"dedupe": "同名多格式去重分析"}
        ).summary()
    return {
        "parse_status": parse_status,
        "running": job_manager.is_running(enterprise_id, project_id),
        "sources": _read_json(_sources_path(enterprise_id, project_id), {"files": []}),
        "dedupe": _read_json(_dedupe_path(enterprise_id, project_id), None),
        "chapters": _read_json(_chapters_path(enterprise_id, project_id), None),
        "extraction": _extract_summary(
            _read_json(paths.extract_list_path(enterprise_id, project_id), None)
        ),
        "score": _score_summary(
            _read_json(paths.score_table_path(enterprise_id, project_id), None)
        ),
        "docx": _docx_summary(
            _read_json(paths.docx_manifest_path(enterprise_id, project_id), None)
        ),
        "checkpoint": checkpoint,
    }


def reset_item(enterprise_id: str, project_id: str, item: str | None) -> None:
    """单项重试：重置 checkpoint 项并按依赖级联清除下游产物。

    - mineru:<k>     → 同时重置 chapters:<k> + extract 项（要素层依赖章节）
    - chapters:<k>   → 重置 extract 项
    - dedupe-verify  → 重置全部 preprocess（work PDF 可能已被改名）+ 删 mineru/chapters/extract
    - preprocess:<f> → 删 verify/mineru/chapters/extract（指纹与解析输入可能变化）
    - dedupe         → 以上全部（分组计划可能变化）
    - extract:coarse → 连带重置 extract:llm（校验依赖粗分结果）
    """
    ckpt_path = paths.checkpoints_dir(enterprise_id, project_id) / f"{JOB_TYPE}.json"
    if not ckpt_path.is_file():
        raise ParseError("尚无解析任务，无法重试")
    store = CheckpointStore.load_or_create(ckpt_path, JOB_TYPE, {"dedupe": "同名多格式去重分析"})
    if item is None:
        store.reset_pending()
        return
    if item not in store.items:
        raise ParseError(f"checkpoint 项不存在：{item}")

    # 动态项（mineru/chapters/preprocess 的具体集合由上游产出决定）用 delete，
    # 固定项（dedupe/dedupe-verify）用 reset
    def _delete_all(prefixes: tuple[str, ...]) -> None:
        for key in [k for k in list(store.items) if k.startswith(prefixes)]:
            store.delete(key)

    def _reset_extract() -> None:
        for key in ("extract:coarse", "extract:llm"):
            if key in store.items:
                store.reset(key)
        stale = paths.extract_list_path(enterprise_id, project_id)
        if stale.is_file():
            stale.unlink()

    def _reset_score() -> None:
        for key in ("score:extract", "score:llm"):
            if key in store.items:
                store.reset(key)
        stale = paths.score_table_path(enterprise_id, project_id)
        if stale.is_file():
            stale.unlink()

    def _reset_docx_source(source_stem: str) -> None:
        """单源章节/解析重跑：删该源的 docx checkpoint 项、产物子目录、manifest。"""
        prefix = f"docx:{source_stem}:"
        for key in [k for k in list(store.items) if k.startswith(prefix)]:
            store.delete(key)
        sub = paths.docx_dir(enterprise_id, project_id) / paths.safe_filename(source_stem)
        if sub.is_dir():
            shutil.rmtree(sub)
        manifest = paths.docx_manifest_path(enterprise_id, project_id)
        if manifest.is_file():
            manifest.unlink()

    def _reset_docx_all() -> None:
        _delete_all(("docx:",))
        root = paths.docx_dir(enterprise_id, project_id)
        if root.is_dir():
            shutil.rmtree(root)

    # docx 单项重试：reset 会清空 output，先取出文件路径，稍后删除
    docx_file_to_delete: Path | None = None
    if item.startswith("docx:"):
        output = store.get(item).output or {}
        file_rel = output.get("file")
        if isinstance(file_rel, str):
            target = paths.docx_dir(enterprise_id, project_id) / file_rel
            try:
                paths.ensure_within_project(paths.project_dir(enterprise_id, project_id), target)
                docx_file_to_delete = target
            except paths.PathEscapeError:
                docx_file_to_delete = None
        manifest = paths.docx_manifest_path(enterprise_id, project_id)
        if manifest.is_file():
            manifest.unlink()

    if item == "extract:coarse":
        if "extract:llm" in store.items:
            store.reset("extract:llm")
        for key in ("extract:coarse", "extract:llm"):
            if key in store.items:
                store.reset(key)
        _p = paths.extract_list_path(enterprise_id, project_id)
        if _p.is_file():
            _p.unlink()
        _reset_score()  # 评分依赖粗分产出的评分章节
    elif item == "extract:llm":
        pass
    elif item == "score:extract":
        if "score:llm" in store.items:
            store.reset("score:llm")
    elif item == "score:llm":
        pass
    elif item.startswith("docx:"):
        pass  # 章节化仅依赖 chapters，与要素/评分层无关
    elif item.startswith("mineru:"):
        stem = item.split(":", 1)[1]
        store.reset(f"chapters:{stem}")
        _reset_extract()
        _reset_score()
        _reset_docx_source(stem)
    elif item.startswith("chapters:"):
        stem = item.split(":", 1)[1]
        _reset_extract()
        _reset_score()
        _reset_docx_source(stem)
    elif item == "dedupe-verify":
        for key in [k for k in store.items if k.startswith("preprocess:")]:
            store.reset(key)
        _delete_all(("mineru:", "chapters:"))
        _reset_extract()
        _reset_score()
        _reset_docx_all()
    elif item.startswith("preprocess:"):
        store.reset("dedupe-verify")
        _delete_all(("mineru:", "chapters:"))
        _reset_extract()
        _reset_score()
        _reset_docx_all()
    elif item == "dedupe":
        store.reset("dedupe-verify")
        for key in [k for k in store.items if k.startswith("preprocess:")]:
            store.reset(key)
        _delete_all(("mineru:", "chapters:"))
        _reset_extract()
        _reset_score()
        _reset_docx_all()
    store.reset(item)

    if docx_file_to_delete is not None and docx_file_to_delete.is_file():
        docx_file_to_delete.unlink()

    # 上游重来时，汇总报告与章节总表作废（重跑后重新生成）
    if item in ("dedupe", "dedupe-verify") or item.startswith("preprocess:"):
        for stale in (
            _dedupe_path(enterprise_id, project_id),
            _chapters_path(enterprise_id, project_id),
        ):
            if stale.is_file():
                stale.unlink()
    elif item.startswith(("mineru:", "chapters:")):
        # 单文件重跑期间避免暴露该源的旧章节
        _remove_chapter_source(enterprise_id, project_id, item.split(":", 1)[1])


def _remove_chapter_source(enterprise_id: str, project_id: str, source_stem: str) -> None:
    path = _chapters_path(enterprise_id, project_id)
    if not path.is_file():
        return
    payload = _read_json(path, {"sources": []})
    remaining = [s for s in payload.get("sources", []) if s.get("source_stem") != source_stem]
    if len(remaining) != len(payload.get("sources", [])):
        payload["sources"] = remaining
        payload["updated_at"] = _now()
        _write_json(path, payload)
