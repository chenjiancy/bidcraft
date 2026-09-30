"""走查脚本 - 修复 page_from/page_to 字段名，更新样本为招标文件。"""

# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent.parent
SAMPLE_ROOT = ROOT / "samples-local"
REPORT_FILE = ROOT / "docs" / "walkthrough-report.json"

TOKEN = os.environ.get("BIDCRAFT_SIDECAR_TOKEN", "")
BASE_URL: str | None = None

REPORT: list[dict] = []
STEP = 0

# ── 路径 ──────────────────────────────────────
# 招标文件（tender），包含评分办法，可完整走查 FR-1~FR-5
TENDER_FILE = (
    ROOT
    / "samples"
    / "和县2026年老旧小区改造项目（EPC总承包）监理采购"
    / "和县2026年老旧小区改造项目（EPC总承包）监理采购文件.doc"
)
# 投标 docx 作素材归档演示
SAMPLE_DIR = SAMPLE_ROOT / "和县柳庄路综合停车场工程监理"
DOCX_FILES = (
    list((SAMPLE_DIR / "投标文件").glob("*.docx")) if (SAMPLE_DIR / "投标文件").exists() else []
)


def step(title: str) -> None:
    global STEP
    STEP += 1
    print(f"\n{'=' * 60}")
    print(f"  步骤 {STEP}: {title}")
    print(f"{'=' * 60}")


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")
    REPORT.append({"step": STEP, "status": "OK", "msg": msg})


def warn(msg: str) -> None:
    print(f"  ⚠️  {msg}")
    REPORT.append({"step": STEP, "status": "WARN", "msg": msg})


def fail(msg: str, detail: str = "") -> None:
    print(f"  ❌ {msg}" + (f"\n     详情：{detail}" if detail else ""))
    REPORT.append({"step": STEP, "status": "FAIL", "msg": msg, "detail": detail})


def api(method: str, path: str, **kwargs) -> dict:
    url = f"{BASE_URL}{path}"
    kwargs.setdefault("timeout", 30.0)
    if TOKEN:
        kwargs.setdefault("headers", {"Authorization": f"Bearer {TOKEN}"})
    try:
        resp = httpx.request(method.upper(), url, **kwargs)
        resp.raise_for_status()
        if resp.text:
            return resp.json()
        return {}
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500] if e.response.text else str(e)
        fail(f"API {method.upper()} {path} → HTTP {e.response.status_code}", detail)
        return {}
    except Exception as e:
        fail(f"API {method.upper()} {path} 异常", str(e))
        return {}


def save_report() -> None:
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📄 报告已保存: {REPORT_FILE}")


# ── Step 1 ────────────────────────────────────
def step1_health() -> None:
    step("Sidecar 健康检查 & 引擎检测")
    r = api("get", "/parse/engine")
    if not r:
        return
    ok(f"MinerU available={r.get('available')}, version={r.get('version', '?')}")
    ok(f"LibreOffice available={r.get('libreoffice_available')}")
    if r.get("cuda_available"):
        ok(f"CUDA device={r.get('cuda_device')}")
    if r.get("error"):
        warn(f"MinerU error: {r['error']}")
    # 清理旧数据
    r2 = api("get", "/enterprises")
    if r2 and isinstance(r2, list) and len(r2) > 0:
        print("\n  发现已有数据，清理中...")
        for ent in r2:
            projs = api("get", f"/enterprises/{ent['id']}/projects") or []
            for p in projs:
                api("delete", f"/enterprises/{ent['id']}/projects/{p['id']}")
            api("delete", f"/enterprises/{ent['id']}")
        ok("旧数据已清理")
    else:
        ok("环境干净")


# ── Step 2 ────────────────────────────────────
def step2_create_enterprise() -> tuple[str, str]:
    step("创建企业")
    r = api("post", "/enterprises", json={"name": "走查测试企业", "agent": "测试代理人"})
    if not r or "id" not in r:
        fail("创建企业失败")
        return "", ""
    ok(f"企业: id={r['id']}, name=走查测试企业")
    return r["id"], "走查测试企业"


# ── Step 3 ────────────────────────────────────
def step3_create_project(eid: str) -> tuple[str, str]:
    step("创建项目")
    pname = "和县2026年老旧小区改造项目（EPC总承包）监理"
    r = api("post", f"/enterprises/{eid}/projects", json={"name": pname})
    if not r or "id" not in r:
        fail("创建项目失败")
        return "", ""
    ok(f"项目: id={r['id']}, name={pname}, status={r.get('parse_status')}")
    return r["id"], pname


# ── Step 4 ────────────────────────────────────
def step4_upload(eid: str, pid: str) -> bool:
    step("上传招标文件（登记源文件）")
    if not TENDER_FILE.exists():
        fail(f"样本文件不存在: {TENDER_FILE}")
        return False
    api(
        "post",
        f"/enterprises/{eid}/projects/{pid}/parse/sources",
        json={"files": [{"path": str(TENDER_FILE), "name": TENDER_FILE.name}]},
    )
    ok(f"源文件登记成功: {TENDER_FILE.name}")
    r2 = api("get", f"/enterprises/{eid}/projects/{pid}/parse/status")
    if r2 and r2.get("parse_status") in ("UPLOADED", "INIT"):
        ok(f"parse_status: {r2.get('parse_status')}")
        return True
    warn(f"parse_status 异常: {r2.get('parse_status') if r2 else '?'}")
    return True


# ── Step 5 ────────────────────────────────────
def step5_parse(eid: str, pid: str) -> bool:
    step("启动解析并轮询等待完成")
    # 触发解析
    try:
        resp = httpx.post(
            f"{BASE_URL}/enterprises/{eid}/projects/{pid}/parse/start", json={}, timeout=10.0
        )
        resp.raise_for_status()
        ok("解析任务已启动（SSE stream）")
    except Exception as e:
        warn(f"SSE 连接异常（任务后台运行）: {e}")
    # 轮询
    for i in range(60):
        time.sleep(5)
        r = api("get", f"/enterprises/{eid}/projects/{pid}/parse/status")
        if not r:
            continue
        st = r.get("parse_status", "?")
        print(f"  [{i + 1}/60] {st}")
        if st in ("SCORE_PARSED", "PARSED", "PARSE_CONFIRMED"):
            ok(f"解析完成，状态: {st}")
            chapters = r.get("chapters") or {}
            sources = chapters.get("sources", [])
            if sources:
                ok(f"源文件数: {len(sources)}")
                for src in sources[:3]:
                    c_list = src.get("chapters", [])
                    ok(f"  - {src.get('name', '?')}: {len(c_list)} 章节")
                    for ch in c_list[:5]:
                        sp = ch.get("start_page", ch.get("page_from"))
                        ep = ch.get("end_page", ch.get("page_to"))
                        ok(f"    [{ch.get('seq', '?')}] {ch.get('title', '')[:50]} (p{sp}-{ep})")
                    if len(c_list) > 5:
                        print(f"      ... 共 {len(c_list)} 章，仅显示前5个")
            return True
        if st == "PARSING_ERROR":
            fail("解析失败")
            return False
    fail("解析超时（60轮×5s=300s）")
    return False


# ── Step 6 ────────────────────────────────────
def step6_confirm(eid: str, pid: str) -> bool:
    step("进入清单复核 & 确认")
    r = api("get", f"/enterprises/{eid}/projects/{pid}/parse/status")
    if not r:
        return False
    st = r.get("parse_status", "")
    if st == "PARSE_CONFIRMED":
        ok("已是 PARSE_CONFIRMED，跳过")
        return True
    if st in ("SCORE_PARSED", "PARSED"):
        r2 = api("post", f"/enterprises/{eid}/projects/{pid}/parse/review", json={})
        if not r2:
            fail("进入复核失败")
            return False
        ok("进入 PARSE_REVIEW 成功")
    else:
        warn(f"unexpected status: {st}")
        return False
    r3 = api("get", f"/enterprises/{eid}/projects/{pid}/parse/checklist")
    if not r3:
        fail("获取清单失败")
        return False
    items = r3.get("items", [])
    total = len(items)
    confirmed = sum(1 for it in items if it.get("confirmed"))
    ok(f"清单总条目: {total}, 已确认: {confirmed}")
    for it in items[:5]:
        tag = "✅" if it.get("confirmed") else "⬜"
        red = "🔴" if it.get("red_flag") else ""
        print(f"  {tag} {red} [{it.get('category', '?')}] {it.get('name', '?')}")
    if total > 5:
        print(f"  ... 共 {total} 条，仅显示前5条")
    if confirmed < total:
        r4 = api("post", f"/enterprises/{eid}/projects/{pid}/parse/confirm", json={})
        if r4 and r4.get("parse_status") == "PARSE_CONFIRMED":
            ok("解析确认成功 → PARSE_CONFIRMED")
            return True
        fail("确认提交失败", str(r4))
        return False
    else:
        ok("已全部确认")
        return True


# ── Step 7 ────────────────────────────────────
def step7_materials(eid: str, pid: str) -> bool:
    step("素材库状态 & 归档演示")
    r = api("get", f"/enterprises/{eid}/materials")
    count = len(r) if isinstance(r, list) else 0
    ok(f"素材库素材数: {count}")
    if count > 0:
        for m in r[:3]:
            ok(f"  - {m.get('name')} ({m.get('category')})")
    if DOCX_FILES:
        sample = DOCX_FILES[0]
        print(f"\n  演示：归档 [{sample.name}] 到资质类")
        r2 = api(
            "post",
            f"/enterprises/{eid}/materials/from_path",
            json={"file_paths": [str(sample)], "category": "qualification", "name": sample.stem},
            timeout=60.0,
        )
        if r2 and isinstance(r2, list) and r2:
            ok(
                f"素材归档成功: id={r2[0].get('id')}, name={r2[0].get('name')}, cat={r2[0].get('category')}"
            )
        else:
            warn(f"归档响应异常: {r2}")
    else:
        warn(f"无演示素材: {SAMPLE_DIR / '投标文件'}")
    return True


# ── Step 8 ────────────────────────────────────
def step8_extract(eid: str, pid: str) -> bool:
    step("素材提取清单生成 & FTS5 查询")
    r = api("post", f"/enterprises/{eid}/projects/{pid}/material-extract/generate", json={})
    if not r:
        warn("生成清单失败")
        return False
    req_count = r.get("requirement_count", 0)
    ok(f"素材需求项数: {req_count}")
    if req_count > 0:
        items = r.get("items", [])
        for it in items[:5]:
            ok(f"  - {it.get('requirement_name')} (来源={it.get('source')})")
        if len(items) > 5:
            print(f"    ... 共 {len(items)} 条")
        r2 = api(
            "post",
            f"/enterprises/{eid}/projects/{pid}/material-extract/query",
            json={"keyword": "", "requirement_name": None},
        )
        if r2:
            results = r2.get("candidates", [])
            ok(f"FTS5 查询返回候选组: {len(results)} 组")
            for g in results[:3]:
                ok(f"  组 [{g.get('group_key')}] → {len(g.get('items', []))} 个候选")
    else:
        warn("需求项为 0 — 请确认是否使用了招标文件（tender）")
    return True


# ── Step 9 ────────────────────────────────────
def step9_render(eid: str, pid: str) -> bool:
    step("格式清单 & 渲染状态检查")
    r = api("get", f"/enterprises/{eid}/projects/{pid}/parse/format/list")
    if r:
        items = r.get("items", [])
        ok(f"格式清单条目数: {len(items)}")
        for it in items[:8]:
            ext = "✅" if it.get("status") == "CONFIRMED" else "⬜"
            print(f"  {ext} #{it.get('seq', '?')} {it.get('title', '?')}")
        if len(items) > 8:
            print(f"    ... 共 {len(items)} 条")
    else:
        warn("格式清单无响应（需先进入 FORMAT_REVIEW）")
    r2 = api("get", f"/enterprises/{eid}/templates")
    tpl_count = len(r2) if isinstance(r2, list) else 0
    ok(f"模板库模板数: {tpl_count}")
    r3 = api("get", f"/enterprises/{eid}/projects/{pid}/render/status")
    if r3:
        ok(f"渲染状态: {r3.get('render_status')}")
    else:
        warn("渲染状态无响应（可能未进入渲染阶段）")
    return True


def main() -> int:
    print("=" * 60)
    print("  BidCraft 和县2026年老旧小区改造项目 · 9步业务走查")
    print("=" * 60)
    print(f"  样本: {TENDER_FILE}")
    print(f"  样本存在: {TENDER_FILE.exists()}")
    print()

    global BASE_URL
    # 启动 sidecar
    sidecar_dir = ROOT / "sidecar"
    uvicorn = sidecar_dir / ".venv" / "Scripts" / "uvicorn.exe"
    if not uvicorn.exists():
        fail("uvicorn.exe 不存在，请先 uv sync")
        return 1
    env = {**os.environ, "BIDCRAFT_SIDECAR_TOKEN": "", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [str(uvicorn), "app.main:app", "--host", "127.0.0.1", "--port", "0"],
        cwd=str(sidecar_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    port = None
    for line in iter(proc.stdout.readline, ""):
        print(f"  [sidecar] {line.rstrip()}")
        if "Uvicorn running on" in line:
            port = int(line.split(":")[-1].split()[0])
            break
    if not port:
        proc.terminate()
        fail("无法获取端口")
        return 1
    BASE_URL = f"http://127.0.0.1:{port}/api/v1"
    for _ in range(20):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
                ok(f"Sidecar 就绪 port={port}")
                break
        except:
            pass
        time.sleep(0.5)

    eid, _ = step2_create_enterprise()
    if not eid:
        save_report()
        return 1
    pid, _ = step3_create_project(eid)
    if not pid:
        save_report()
        return 1

    if not step4_upload(eid, pid):
        save_report()
        return 1
    if not step5_parse(eid, pid):
        save_report()
        return 1
    if not step6_confirm(eid, pid):
        save_report()
        return 1
    step7_materials(eid, pid)
    step8_extract(eid, pid)
    step9_render(eid, pid)

    print(f"\n{'=' * 60}")
    print("  走查汇总")
    print(f"{'=' * 60}")
    ok_n = sum(1 for r in REPORT if r["status"] == "OK")
    warn_n = sum(1 for r in REPORT if r["status"] == "WARN")
    fail_n = sum(1 for r in REPORT if r["status"] == "FAIL")
    print(f"  ✅ 通过: {ok_n}  |  ⚠️  警告: {warn_n}  |  ❌ 失败: {fail_n}")
    if fail_n:
        print("\n  失败项：")
        for r in REPORT:
            if r["status"] == "FAIL":
                print(f"    步骤{r['step']}: {r['msg']}")
                if r.get("detail"):
                    print(f"      → {r['detail']}")
    save_report()
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
