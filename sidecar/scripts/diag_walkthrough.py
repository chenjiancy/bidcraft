"""快速诊断步骤7/8的500错误。"""

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).parent.parent.parent
SAMPLE_ROOT = ROOT / "samples-local"
REPORT_FILE = ROOT / "docs" / "walkthrough-diag.json"

# 先启动 sidecar
sidecar_dir = ROOT / "sidecar"
uvicorn = sidecar_dir / ".venv" / "Scripts" / "uvicorn.exe"
env = {**__import__("os").environ, "BIDCRAFT_SIDECAR_TOKEN": "", "PYTHONUNBUFFERED": "1"}
proc = __import__("subprocess").Popen(
    [str(uvicorn), "app.main:app", "--host", "127.0.0.1", "--port", "0"],
    cwd=str(sidecar_dir),
    env=env,
    stdout=__import__("subprocess").PIPE,
    stderr=__import__("subprocess").STDOUT,
    text=True,
)
port = None
for line in iter(proc.stdout.readline, ""):
    print(f"  [sidecar] {line.rstrip()}")
    if "Uvicorn running on" in line:
        port = int(line.split(":")[-1].split()[0])
        break
if not port:
    print("FAIL: sidecar 启动失败")
    sys.exit(1)
print(f"Sidecar 端口: {port}")
BASE = f"http://127.0.0.1:{port}/api/v1"

for _ in range(20):
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
        if r.status_code == 200:
            print("Sidecar 就绪")
            break
    except Exception:
        pass
    time.sleep(0.5)
else:
    print("FAIL: sidecar 健康检查超时")
    sys.exit(1)

diag: dict = {}


def api(method, path, **kwargs):
    url = f"{BASE}{path}"
    try:
        resp = httpx.request(method.upper(), url, **kwargs)
        return resp.status_code, resp.text[:2000]
    except Exception as e:
        return 0, str(e)


# Step A: 创建企业+项目+上传文件
print("\n=== A. 创建数据 ===")
s, b = api("POST", "/enterprises", json={"name": "diag-test", "agent": "test"})
ent = json.loads(b)
eid = ent["id"]
print(f"企业: {eid}")

s, b = api("POST", f"/enterprises/{eid}/projects", json={"name": "diag-project"})
proj = json.loads(b)
pid = proj["id"]
print(f"项目: {pid}")

BID_PDF = (
    SAMPLE_ROOT / "和县2026年老旧小区改造项目（EPC总承包）监理采购" / "投标文件" / "投标文件.pdf"
)
s, b = api(
    "POST",
    f"/enterprises/{eid}/projects/{pid}/parse/sources",
    json={"files": [{"path": str(BID_PDF), "name": BID_PDF.name}]},
)
print(f"上传源文件: HTTP {s}")

# 等待解析完成
print("\n=== B. 等待解析 ===")
for i in range(60):
    time.sleep(3)
    s, b = api("GET", f"/enterprises/{eid}/projects/{pid}/parse/status")
    data = json.loads(b) if b else {}
    st = data.get("parse_status", "?")
    print(f"  [{i + 1}] {st}")
    if st in ("SCORE_PARSED", "PARSED", "PARSE_CONFIRMED"):
        break
else:
    print("超时")
    sys.exit(1)

# 进入 review & confirm
print("\n=== C. 进入复核 ===")
s, b = api("POST", f"/enterprises/{eid}/projects/{pid}/parse/review")
print(f"review: HTTP {s}, body={b[:300]}")

s, b = api("GET", f"/enterprises/{eid}/projects/{pid}/parse/checklist")
cl = json.loads(b) if b else {}
items = cl.get("items", [])
print(f"清单条目: {len(items)}")

if items:
    s, b = api("POST", f"/enterprises/{eid}/projects/{pid}/parse/confirm", json={"items": items})
    print(f"confirm: HTTP {s}, body={b[:300]}")

# Step D: 测试素材归档
print("\n=== D. 素材归档测试 ===")
DOCX = list((SAMPLE_ROOT / "和县柳庄路综合停车场工程监理" / "投标文件").glob("*.docx"))
if DOCX:
    sample = str(DOCX[0])
    print(f"测试归档: {sample}")
    s, b = api(
        "POST",
        f"/enterprises/{eid}/materials/from_path",
        json={"file_paths": [sample], "category": "qualification", "name": DOCX[0].stem},
    )
    print(f"  HTTP {s}, body={b[:500]}")
    diag["material_from_path"] = {"status": s, "body": b[:500]}

# Step E: 测试 material-extract/generate
print("\n=== E. 素材提取清单生成 ===")
s, b = api("POST", f"/enterprises/{eid}/projects/{pid}/material-extract/generate", json={})
print(f"  HTTP {s}, body={b[:500]}")
diag["material_extract_generate"] = {"status": s, "body": b[:500]}

# Step F: 查看数据目录
print("\n=== F. 检查数据目录 ===")
data_root = Path(__import__("os").environ.get("BIDCRAFT_DATA_ROOT") or Path.home() / ".bidcraft")
proj_dir = data_root / "enterprises" / eid / "projects" / pid
print(f"项目数据目录: {proj_dir}")
for p in sorted(proj_dir.rglob("*")):
    if p.is_file():
        print(f"  {p.relative_to(proj_dir)} ({p.stat().st_size} bytes)")
diag["data_files"] = [
    str(p.relative_to(proj_dir)) for p in sorted(proj_dir.rglob("*")) if p.is_file()
]

# 保存诊断报告
REPORT_FILE.write_text(
    json.dumps(diag, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
)
print(f"\n诊断报告: {REPORT_FILE}")
