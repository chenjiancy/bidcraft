"""Task 8 解析流水线集成测试（TR-8.3/8.5/8.7/8.8/8.9）。

MinerU 与 LibreOffice 均以 fake 替换，CI 无需 GPU/模型；
真实端到端样本验证见 tests/engine（marker: engine）。
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.deps import get_engine
from app.models.app_event import AppEvent
from app.parse import engine as engine_mod
from app.parse import service as parse_service
from app.parse.engine import RawResult

# ---------- 最小文本 PDF 工厂（pypdf 可提取，供去重指纹使用） ----------


def make_text_pdf(path: Path, pages: list[str]) -> Path:
    page_nums = [3 + 2 * i for i in range(len(pages))]
    content_nums = [4 + 2 * i for i in range(len(pages))]
    font_num = 3 + 2 * len(pages)
    kids = " ".join(f"{n} 0 R" for n in page_nums)
    body = b"%PDF-1.4\n"
    offsets: dict[int, int] = {}

    def emit(num: int, content: bytes) -> None:
        nonlocal body
        offsets[num] = len(body)
        body += f"{num} 0 obj\n".encode() + content + b"\nendobj\n"

    emit(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    emit(2, f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    streams = []
    for i, text in enumerate(pages):
        safe = text.replace("(", " ").replace(")", " ")
        stream = f"BT /F1 12 Tf 50 740 Td ({safe}) Tj ET".encode("latin-1", "replace")
        streams.append(stream)
        emit(
            page_nums[i],
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_num} 0 R >> >> "
            f"/Contents {content_nums[i]} 0 R >>".encode(),
        )
        emit(
            content_nums[i],
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
        )
    emit(font_num, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    xref_pos = len(body)
    body += f"xref\n0 {font_num + 1}\n".encode()
    body += b"0000000000 65535 f \n"
    for i in range(1, font_num + 1):
        body += f"{offsets[i]:010d} 00000 n \n".encode()
    body += (
        f"trailer\n<< /Size {font_num + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def _content_blocks(stem: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": f"{stem} chapter one notice",
            "page_idx": 0,
            "text_level": 1,
            "bbox": [10.0, 20.0, 300.0, 60.0],
        },
        {"type": "text", "text": "1. overview section", "page_idx": 0, "text_level": 2},
        {"type": "text", "text": "ordinary paragraph body text " * 20, "page_idx": 0},
        {"type": "text", "text": "2. second section", "page_idx": 1, "text_level": 2},
    ]


class FakeMineru:
    """替换 engine.run_mineru：按输入 stem 在 out_dir 写出 3.4.x 风格产物。

    wait_cancel=True 时在事件循环内 0.5s 后自动置位取消信号（等价用户点取消，
    规避 TestClient portal 下跨线程调度不稳定；取消 HTTP 端点另由
    test_test_stream 覆盖）。
    """

    def __init__(
        self,
        *,
        fail_stems: set[str] | None = None,
        wait_cancel: bool = False,
        cancel_after: float = 0.5,
    ) -> None:
        self.fail_stems = fail_stems or set()
        self.wait_cancel = wait_cancel
        self.cancel_after = cancel_after
        self.calls: list[str] = []

    async def __call__(
        self,
        input_file: Path,
        out_dir: Path,
        *,
        method: str = "auto",
        language: str = "ch",
        cancel_event: asyncio.Event | None = None,
        timeout: int = 3600,
        on_log: Any = None,
    ) -> RawResult:
        self.calls.append(input_file.stem)
        if on_log:
            on_log(f"fake processing {input_file.stem}")
        if self.wait_cancel and cancel_event is not None:
            loop = asyncio.get_running_loop()
            loop.call_later(self.cancel_after, cancel_event.set)
            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=5)
                raise asyncio.CancelledError("用户取消解析")
            except TimeoutError:
                pass
        if input_file.stem in self.fail_stems:
            raise engine_mod.MinerUError(f"simulated failure: {input_file.stem}")
        base = out_dir / input_file.stem
        base.mkdir(parents=True, exist_ok=True)
        stem = input_file.stem
        md = base / f"{stem}.md"
        md.write_text(f"# {stem}\n", encoding="utf-8")
        cl = base / f"{stem}_content_list.json"
        cl.write_text(json.dumps(_content_blocks(stem)), encoding="utf-8")
        return RawResult(base, md, cl, None, None, [])


# ---------- 夹具与辅助 ----------


@pytest.fixture
def project(db_client: TestClient) -> tuple[str, str]:
    ent = db_client.post("/api/v1/enterprises", json={"name": "测试企业", "agent": "张三"}).json()
    proj = db_client.post(
        f"/api/v1/enterprises/{ent['id']}/projects", json={"name": "测试项目"}
    ).json()
    return ent["id"], proj["id"]


def _register(client: TestClient, eid: str, pid: str, files: list[tuple[str, Path]]) -> Any:
    return client.post(
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/sources",
        json={"files": [{"name": name, "path": str(path)} for name, path in files]},
    )


def _start_sse(
    client: TestClient, eid: str, pid: str, *, reparse: bool = False
) -> tuple[Any, list[dict[str, Any]], str]:
    """发起 SSE 并收集全部事件，返回 (response, events, task_id)。"""
    events: list[dict[str, Any]] = []
    with client.stream(
        "POST",
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/start",
        json={"reparse": reparse},
    ) as resp:
        task_id = resp.headers["x-task-id"]
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return resp, events, task_id


def _terminal(events: list[dict[str, Any]]) -> dict[str, Any]:
    return events[-1]


def _patch_engine(
    monkeypatch: pytest.MonkeyPatch, fake: FakeMineru, convert_pages: dict[str, list[str]]
) -> None:
    async def _fake_convert(src: Path, out_dir: Path, **_kw: Any) -> Path:
        pdf = out_dir / f"{src.stem}.pdf"
        make_text_pdf(pdf, convert_pages.get(src.name, [f"converted from {src.name} " * 30]))
        return pdf

    monkeypatch.setattr(parse_service.engine, "run_mineru", fake)
    monkeypatch.setattr(parse_service.preprocess, "convert_to_pdf", _fake_convert)


# ---------- TR：引擎检测 ----------


def test_engine_endpoint_reports_shape(db_client: TestClient) -> None:
    resp = db_client.get("/api/v1/parse/engine")
    assert resp.status_code == 200
    data = resp.json()
    # CI 无 MinerU：available 可能为 False，但字段形态固定
    assert set(data) >= {
        "available",
        "python_path",
        "version",
        "cuda_available",
        "cuda_device",
        "error",
        "libreoffice_available",
    }
    assert isinstance(data["libreoffice_available"], bool)


# ---------- TR-8.9：登记 + 隔离 ----------


def test_register_sources_uploaded_and_copied(
    db_client: TestClient, project: tuple[str, str], tmp_path: Path
) -> None:
    eid, pid = project
    pdf = tmp_path / "招标文件正文.pdf"
    make_text_pdf(pdf, ["notice content " * 20])
    resp = _register(db_client, eid, pid, [("招标文件正文.pdf", pdf)])
    assert resp.status_code == 201, resp.text
    assert resp.json()["total"] == 1

    status = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/status").json()
    assert status["parse_status"] == "UPLOADED"
    assert status["sources"]["files"][0]["stored_name"] == "招标文件正文.pdf"


def test_register_rejects_missing_and_unsupported(
    db_client: TestClient, project: tuple[str, str], tmp_path: Path
) -> None:
    eid, pid = project
    missing = tmp_path / "nope.pdf"
    resp = _register(db_client, eid, pid, [("nope.pdf", missing)])
    assert resp.status_code == 400

    txt = tmp_path / "x.txt"
    txt.write_text("hi", encoding="utf-8")
    resp = _register(db_client, eid, pid, [("x.txt", txt)])
    assert resp.status_code == 400


def test_cross_enterprise_project_invisible(
    db_client: TestClient, project: tuple[str, str]
) -> None:
    eid, pid = project
    other = db_client.post("/api/v1/enterprises", json={"name": "别家企业", "agent": "李四"}).json()
    resp = db_client.get(f"/api/v1/enterprises/{other['id']}/projects/{pid}/parse/status")
    assert resp.status_code == 404
    resp2 = db_client.post(f"/api/v1/enterprises/{other['id']}/projects/{pid}/parse/start", json={})
    assert resp2.status_code == 404


# ---------- TR-8.1/8.4：完整 happy path（两个独立 PDF） ----------


def test_full_parse_pipeline_success(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    f1 = tmp_path / "招标文件正文.pdf"
    f2 = tmp_path / "资格证明.pdf"
    make_text_pdf(f1, ["main document content " * 20, "page two text " * 20])
    make_text_pdf(f2, ["qualification cert content " * 20])
    _register(db_client, eid, pid, [("招标文件正文.pdf", f1), ("资格证明.pdf", f2)])

    fake = FakeMineru()
    _patch_engine(monkeypatch, fake, convert_pages={})

    resp, events, task_id = _start_sse(db_client, eid, pid)
    assert resp.status_code == 200
    assert _terminal(events)["stage"] == "completed"
    assert sorted(fake.calls) == ["招标文件正文", "资格证明"]

    status = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/status").json()
    assert status["parse_status"] == "PARSED"
    assert status["running"] is False
    items = {i["key"]: i for i in status["checkpoint"]["items"]}
    assert all(i["state"] == "success" for i in items.values())
    # 两源章节均落盘（TR-8.4），带页码锚点
    sources = status["chapters"]["sources"]
    assert {s["source_stem"] for s in sources} == {"招标文件正文", "资格证明"}
    ch = sources[0]["chapters"][0]
    assert ch["anchor"]["page_idx"] == 0
    assert ch["anchor"]["bbox"] == [10.0, 20.0, 300.0, 60.0]
    # TR-8.1 产物：md + content_list 按项目隔离落在 parse/raw/<stem>/ 下
    raw_dir = parse_service.paths.raw_dir(eid, pid)
    assert (raw_dir / "招标文件正文" / "招标文件正文.md").is_file()
    assert (raw_dir / "资格证明" / "资格证明_content_list.json").is_file()
    # 任务结束后取消接口返回 404（任务已注销）
    cancel = db_client.post(f"/api/v1/tasks/{task_id}/cancel")
    assert cancel.status_code == 404


# ---------- TR-8.3：.doc 经 LibreOffice 转换（转换本身 fake，真实转换见 engine 测试） ----------


def test_doc_file_converted_before_mineru(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    doc = tmp_path / "老旧小区改造.doc"
    doc.write_bytes(b"fake-legacy-doc-binary")
    _register(db_client, eid, pid, [("老旧小区改造.doc", doc)])

    converted: list[str] = []
    fake = FakeMineru()

    async def _convert(src: Path, out_dir: Path, **_kw: Any) -> Path:
        converted.append(src.name)
        pdf = out_dir / f"{src.stem}.pdf"
        make_text_pdf(pdf, ["legacy doc converted body " * 20])
        return pdf

    monkeypatch.setattr(parse_service.engine, "run_mineru", fake)
    monkeypatch.setattr(parse_service.preprocess, "convert_to_pdf", _convert)

    _, events, _ = _start_sse(db_client, eid, pid)
    assert _terminal(events)["stage"] == "completed"
    assert converted == ["老旧小区改造.doc"]
    # MinerU 输入是 work 中转换出的 PDF，而非原始 .doc
    assert fake.calls == ["老旧小区改造"]
    status = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/status").json()
    item = next(i for i in status["checkpoint"]["items"] if i["key"] == "mineru:老旧小区改造")
    assert item["output"]["input"] == "老旧小区改造.pdf"


# ---------- TR-8.5：同名多格式去重（合成夹具） ----------


def test_dedupe_same_name_same_content_keeps_docx(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    docx = tmp_path / "技术规范书.docx"
    docx.write_bytes(b"fake-docx-binary")
    pdf = tmp_path / "技术规范书.pdf"
    same_text = "identical tender technical spec content " * 20
    make_text_pdf(pdf, [same_text])
    _register(db_client, eid, pid, [("技术规范书.docx", docx), ("技术规范书.pdf", pdf)])

    fake = FakeMineru()
    _patch_engine(monkeypatch, fake, {"技术规范书.docx": [same_text]})

    _, events, _ = _start_sse(db_client, eid, pid)
    assert _terminal(events)["stage"] == "completed"
    # 只解析 docx 主格式，pdf 同内容被内部消化
    assert fake.calls == ["技术规范书"]

    status = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/status").json()
    dropped = status["dedupe"]["dropped"]
    assert len(dropped) == 1
    assert dropped[0]["stored_name"] == "技术规范书.pdf"
    assert dropped[0]["kept_as"] == "技术规范书.docx"


def test_dedupe_same_name_different_content_keeps_both(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    docx = tmp_path / "技术规范书.docx"
    docx.write_bytes(b"fake-docx-binary")
    pdf = tmp_path / "技术规范书.pdf"
    make_text_pdf(pdf, ["totally different PDF edition content alpha " * 20])
    _register(db_client, eid, pid, [("技术规范书.docx", docx), ("技术规范书.pdf", pdf)])

    fake = FakeMineru()
    _patch_engine(
        monkeypatch, fake, {"技术规范书.docx": ["different docx edition content beta " * 20]}
    )

    _, events, _ = _start_sse(db_client, eid, pid)
    assert _terminal(events)["stage"] == "completed"
    # 两份都送入 MinerU（docx 原名 + pdf 的 -mm1 唯一名，避免输出目录冲突）
    assert sorted(fake.calls) == ["技术规范书", "技术规范书-mm1"]

    status = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/status").json()
    assert len(status["dedupe"]["mismatches"]) == 1
    stems = {s["source_stem"] for s in status["chapters"]["sources"]}
    assert stems == {"技术规范书", "技术规范书-mm1"}


# ---------- TR-8.7：断点续跑 + 单项重试 ----------


def test_resume_skips_successful_items(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    names = ["a文件.pdf", "b文件.pdf", "c文件.pdf"]
    files = []
    for i, name in enumerate(names):
        p = tmp_path / name
        make_text_pdf(p, [f"document {i} body text " * 20])
        files.append((name, p))
    _register(db_client, eid, pid, files)

    fake1 = FakeMineru(fail_stems={"b文件"})
    _patch_engine(monkeypatch, fake1, {})
    _, events1, _ = _start_sse(db_client, eid, pid)
    assert _terminal(events1)["stage"] == "failed"
    assert fake1.calls == ["a文件", "b文件"]

    # 续跑：a 已 success 不重跑；b 恢复；c 首跑
    fake2 = FakeMineru()
    _patch_engine(monkeypatch, fake2, {})
    _, events2, _ = _start_sse(db_client, eid, pid)
    assert _terminal(events2)["stage"] == "completed"
    assert fake2.calls == ["b文件", "c文件"]

    status = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/status").json()
    assert status["parse_status"] == "PARSED"
    # 失败信息曾留痕：checkpoint attempts 反映重试过
    items = {i["key"]: i for i in status["checkpoint"]["items"]}
    assert items["mineru:b文件"]["attempts"] == 2


def test_single_item_retry(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    f1 = tmp_path / "a文件.pdf"
    make_text_pdf(f1, ["body a " * 20])
    _register(db_client, eid, pid, [("a文件.pdf", f1)])
    fake = FakeMineru()
    _patch_engine(monkeypatch, fake, {})
    _start_sse(db_client, eid, pid)
    assert fake.calls == ["a文件"]

    # 单项重试 mineru → 关联 chapters 一并重置
    retry = db_client.post(
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/retry",
        json={"item": "mineru:a文件"},
    )
    assert retry.status_code == 200
    _start_sse(db_client, eid, pid)
    assert fake.calls == ["a文件", "a文件"]

    # 未知 item → 400
    bad = db_client.post(
        f"/api/v1/enterprises/{eid}/projects/{pid}/parse/retry",
        json={"item": "mineru:不存在"},
    )
    assert bad.status_code == 400


# ---------- TR-8.8：取消 + 状态回退 + 事件留痕 ----------


def test_cancel_marks_uploaded_and_can_resume(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    f1 = tmp_path / "a文件.pdf"
    make_text_pdf(f1, ["body a " * 20])
    _register(db_client, eid, pid, [("a文件.pdf", f1)])
    fake = FakeMineru(wait_cancel=True)
    _patch_engine(monkeypatch, fake, {})

    # FakeMineru(wait_cancel) 在事件循环内 0.5s 自动置位取消信号
    _, events, _ = _start_sse(db_client, eid, pid)
    assert _terminal(events)["stage"] == "cancelled"
    status = db_client.get(f"/api/v1/enterprises/{eid}/projects/{pid}/parse/status").json()
    assert status["parse_status"] == "UPLOADED"
    item = next(i for i in status["checkpoint"]["items"] if i["key"] == "mineru:a文件")
    assert item["state"] == "error" and "取消" in (item["error"] or "")

    # 续跑成功
    fake2 = FakeMineru()
    _patch_engine(monkeypatch, fake2, {})
    _, ev2, _ = _start_sse(db_client, eid, pid)
    assert _terminal(ev2)["stage"] == "completed"


def test_concurrent_start_rejected(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同项目任务运行中：job_manager 判定运行态（路由据此返回 409）。

    TestClient 不支持同客户端并发 HTTP，故在服务端回调中断言运行态；
    路由层为 is_running → 409 的薄包装。
    """
    eid, pid = project
    f1 = tmp_path / "a文件.pdf"
    make_text_pdf(f1, ["body a " * 20])
    _register(db_client, eid, pid, [("a文件.pdf", f1)])

    running_seen: list[bool] = []

    class _Probe(FakeMineru):
        async def __call__(self, input_file: Path, out_dir: Path, **kw: Any) -> RawResult:
            running_seen.append(parse_service.job_manager.is_running(eid, pid))
            return await super().__call__(input_file, out_dir, **kw)

    _patch_engine(monkeypatch, _Probe(wait_cancel=True), {})
    _, events, _ = _start_sse(db_client, eid, pid)
    # 任务被自动取消（仅为制造"运行中"窗口）
    assert _terminal(events)["stage"] == "cancelled"
    assert running_seen == [True]
    # 任务结束后运行态解除（可再次启动）
    assert parse_service.job_manager.is_running(eid, pid) is False


def test_state_change_events_recorded(
    db_client: TestClient,
    project: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eid, pid = project
    f1 = tmp_path / "a文件.pdf"
    make_text_pdf(f1, ["body a " * 20])
    _register(db_client, eid, pid, [("a文件.pdf", f1)])
    _patch_engine(monkeypatch, FakeMineru(), {})
    _start_sse(db_client, eid, pid)

    from app.db.session import session_factory

    with session_factory(get_engine())() as session:
        rows = session.scalars(
            select(AppEvent)
            .where(AppEvent.project_id == pid)
            .where(AppEvent.type == "parse_state_change")
        ).all()
    transitions = [((r.payload or {})["from"], (r.payload or {})["to"]) for r in rows]
    assert ("INIT", "UPLOADED") in transitions
    assert ("UPLOADED", "PARSING") in transitions
    assert ("PARSING", "PARSED") in transitions
