"""素材库转图片工具（FR-4 第 5 点）。

规则：素材库只存图片（.png / .jpg），上传时转换为图片。
- PDF：PyMuPDF (fitz) 渲染每页为 PNG，多页以 _P0/_P1... 区分
- Word（.doc/.docx）：LibreOffice headless 转 PDF → 再渲染为 PNG
- 图片（.png/.jpg/.jpeg/.bmp/.tiff）：直接复制

分辨率标准：150 DPI（A4 全幅证件清晰度足够）
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

# ---------- 转图片函数 ----------


def pdf_to_pngs(pdf_path: Path, dpi: int = 150) -> list[bytes]:
    """将 PDF 各页渲染为 PNG 字节列表。

    Args:
        pdf_path: PDF 文件路径
        dpi: 渲染分辨率，默认 150 DPI

    Returns:
        每页一张的 PNG 字节列表

    Raises:
        RuntimeError: PyMuPDF 不可用或渲染失败
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError("PyMuPDF (fitz) 未安装，无法渲染 PDF") from None

    doc = fitz.open(str(pdf_path))
    try:
        pages: list[bytes] = []
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            pages.append(pix.tobytes("png"))
        return pages
    finally:
        doc.close()


def word_to_pdf(docx_path: Path, timeout: int = 60) -> Path:
    """用 LibreOffice headless 将 Word 文档转 PDF。

    Args:
        docx_path: .doc/.docx 文件路径
        timeout: 转换超时（秒）

    Returns:
        临时 PDF 文件路径（调用方负责清理）

    Raises:
        RuntimeError: LibreOffice 不可用或转换失败
    """
    # 查找 LibreOffice 可执行文件
    lo_path = _find_libreoffice()
    with tempfile.TemporaryDirectory() as tmp_dir:
        cmd = [
            lo_path,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            tmp_dir,
            str(docx_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"LibreOffice 转换失败: {proc.stderr}")
        out_dir = Path(tmp_dir)
        for f in out_dir.iterdir():
            if f.suffix.lower() == ".pdf":
                return f  # 注意：tmp_dir 退出后文件会被删除
        raise RuntimeError("LibreOffice 未生成 PDF 输出")


def image_copy(src: Path, dest: Path) -> Path:
    """直接复制图片文件（已是 .png/.jpg/.jpeg/.bmp/.tiff）。"""
    import shutil

    shutil.copy2(src, dest)
    return dest


# ---------- 工具函数 ----------


def _find_libreoffice() -> str:
    """查找 LibreOffice 可执行文件路径。"""
    candidates = [
        # Linux
        "/usr/bin/libreoffice",
        "/usr/bin/soffice",
        # macOS
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        # Windows
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # 尝试 PATH
    for name in ("libreoffice", "soffice"):
        import shutil as _sh

        found = _sh.which(name)
        if found:
            return found
    raise RuntimeError("未找到 LibreOffice；请安装后配置 PATH 或修改 _find_libreoffice()")
