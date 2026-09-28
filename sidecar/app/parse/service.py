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
from app.parse import dedupe as dedupe_mod
from app.parse import engine, paths, preprocess, state
from app.parse.checkpoint import CheckpointStore
from app.parse.dedupe import SourceFile
from app.repositories.app_event import AppEventRepository
from app.repositories.base import NotFoundError, Scope
from app.repositories.project import ProjectRepository

JOB_TYPE = "document_parse"
_SOURCES_FILE = "sources.json"
_DEDUPE_FILE = "dedupe.json"
_CHAPTERS_FILE = "chapters.json"

# 阶段进度权重（累计百分比）
_W_DEDUPE = 5
_W_PREPROCESS_END = 20
_W_VERIFY_END = 25
_W_MINERU_END = 85
# chapters 收尾到 100

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

    # 新文件使既有解析产物失效：清 checkpoint/dedupe/chapters（raw/work 重跑覆盖）
    ckpt = paths.checkpoints_dir(e_dir, p_dir) / f"{JOB_TYPE}.json"
    for stale in (ckpt, _dedupe_path(e_dir, p_dir), _chapters_path(e_dir, p_dir)):
        if stale.is_file():
            stale.unlink()

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
) -> None:
    """执行（或断点续跑）解析。emit 推送 SSE 事件 dict；终态由本函数推送。"""
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
                        "percent": _w_between(_W_MINERU_END, 100, i + 1, len(chapter_items)),
                        "message": f"章节切分完成：{source_stem}"
                        f"（{chapter_result['stats']['chapter_count']} 章）",
                    }
                )
            except Exception as exc:
                store.mark_error(key, str(exc))
                raise

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
        "checkpoint": checkpoint,
    }


def reset_item(enterprise_id: str, project_id: str, item: str | None) -> None:
    """单项重试：重置 checkpoint 项并按依赖级联清除下游产物。

    - mineru:<k>     → 同时重置 chapters:<k>
    - dedupe-verify  → 重置全部 preprocess（work PDF 可能已被改名）+ 删 mineru/chapters
    - preprocess:<f> → 删 verify/mineru/chapters（指纹与解析输入可能变化）
    - dedupe         → 以上全部（分组计划可能变化）
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

    if item.startswith("mineru:"):
        store.reset(f"chapters:{item.split(':', 1)[1]}")
    elif item.startswith("chapters:"):
        pass
    elif item == "dedupe-verify":
        for key in [k for k in store.items if k.startswith("preprocess:")]:
            store.reset(key)
        _delete_all(("mineru:", "chapters:"))
    elif item.startswith("preprocess:"):
        store.reset("dedupe-verify")
        _delete_all(("mineru:", "chapters:"))
    elif item == "dedupe":
        store.reset("dedupe-verify")
        for key in [k for k in store.items if k.startswith("preprocess:")]:
            store.reset(key)
        _delete_all(("mineru:", "chapters:"))
    store.reset(item)

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
