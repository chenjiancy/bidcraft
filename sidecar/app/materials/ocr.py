"""OCR 后端抽象接口（TS-4）与默认实现。

Task 15：落地抽象接口 + MinerU 内置 OCR 实现。
开发时可用真实证件对比 MinerU vs PaddleOCR，决定默认后端后关闭 TS-4。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class OcrResult:
    """OCR 识别结果。"""

    text: str
    fields: dict[str, str] | None = None  # 可提取的结构化字段（姓名、有效期等）


class OcrBackend(ABC):
    """OCR 后端统一接口（TS-4 抽象）。"""

    @abstractmethod
    def recognize(self, image_bytes: bytes) -> OcrResult:
        """对图片字节执行 OCR，返回文本结果。"""

    def extract_fields(self, text: str, keywords: list[str]) -> dict[str, str]:
        """从 OCR 文本中按关键词列表提取字段（默认简单包含匹配）。"""
        result: dict[str, str] = {}
        for kw in keywords:
            # 取关键词后 30 个字符作为字段值
            idx = text.find(kw)
            if idx >= 0:
                result[kw] = text[idx : idx + len(kw) + 20].strip()
        return result


class MinerUOcr(OcrBackend):
    """使用 MinerU 内置 OCR 引擎的适配器。

    MinerU 在解析阶段已被引入，其 text extraction 可复用为 OCR 后端。
    生产环境调用需经 MinerU REST 服务或本地推理。
    """

    def __init__(self, mineru_url: str = "http://localhost:3000"):
        self._mineru_url = mineru_url

    def recognize(self, image_bytes: bytes) -> OcrResult:
        """调用 MinerU OCR 服务识别图片文本。

        注意：MinerU 主要处理 PDF/Markdown 而非原始图片 OCR，
        实际使用时应先经 PyMuPDF 将图片转 PDF 再传给 MinerU。
        当前实现抛出 NotImplementedError，由上层归档管线处理。
        """
        raise NotImplementedError(
            "MinerU OCR 不适用于裸图片；请先用 PyMuPDF 将图片封装为单页 PDF 再调用"
        )


class StubOcr(OcrBackend):
    """开发/测试用 Stub OCR 实现：直接返回固定文本。

    用于 CI 测试和未接入真实 OCR 引擎的开发环境。
    """

    def __init__(self, fixed_text: str = ""):
        self._fixed_text = fixed_text

    def recognize(self, image_bytes: bytes) -> OcrResult:
        return OcrResult(text=self._fixed_text, fields={})


class RapidOcrBackend(OcrBackend):
    """RapidOCR（PP-OCRv6 small，ONNX Runtime）进程内 OCR 后端。

    TS-4 决策（2026-10）：素材归档为高频交互，选用进程内、CPU 秒级、
    模型随包内置（约 32MB）的 RapidOCR，而非 MinerU 子进程。

    Args:
        engine: 注入用引擎（测试边界）；生产使用时惰性构建 ``RapidOCR``。
        min_score: 文本行置信度下限，低于该值的行丢弃。
    """

    def __init__(
        self,
        engine: Any = None,
        *,
        min_score: float = 0.5,
    ) -> None:
        self._engine = engine
        self._min_score = min_score

    def _get_engine(self) -> Any:
        if self._engine is None:
            from rapidocr import RapidOCR

            self._engine = RapidOCR()
        return self._engine

    def recognize(self, image_bytes: bytes) -> OcrResult:
        output = self._get_engine()(image_bytes)
        lines: list[str] = []
        txts = getattr(output, "txts", None) or ()
        scores = getattr(output, "scores", None) or ()
        for text, score in zip(txts, scores, strict=False):
            if score is not None and float(score) < self._min_score:
                continue
            lines.append(str(text))
        return OcrResult(text="\n".join(lines), fields={})


def build_default_ocr() -> OcrBackend:
    """归档管线默认 OCR 后端工厂（API 层统一经此注入，便于切换/测试）。"""
    return RapidOcrBackend()


def strip_watermark_lines(
    pages_text: list[str],
    *,
    min_repeat_pages: int = 2,
    max_line_len: int = 20,
) -> str:
    """跨页重复短行（扫描水印/页眉）过滤（FT-1）。

    扫描软件水印（如「汉王扫描王」）和页眉行在每页重复出现，
    混入 ocr_text 后干扰命名提取和 FTS5 检索。此函数按跨页频率
    识别并剥离这类行。

    Args:
        pages_text: 每页 OCR 文本列表（元素为一页的完整文本）。
        min_repeat_pages: 触发剥离的最少出现页数（默认 2）。
        max_line_len: 剥离的最大行长度（超过则视为正常内容保留）。

    Returns:
        过滤后的合并文本（页间用空行分隔）。
    """
    if not pages_text:
        return ""

    # 按页拆行，归一化后统计跨页出现次数（每页最多计 1 次）
    page_lines: list[list[str]] = []
    line_page_count: dict[str, int] = {}

    for page_text in pages_text:
        lines = page_text.split("\n")
        page_lines.append(lines)
        seen_on_page: set[str] = set()
        for line in lines:
            norm = line.strip()
            if norm and norm not in seen_on_page:
                seen_on_page.add(norm)
                line_page_count[norm] = line_page_count.get(norm, 0) + 1

    # 标记需剥离的行：跨页重复且短
    stripped: set[str] = set()
    for norm, count in line_page_count.items():
        if count >= min_repeat_pages and len(norm) <= max_line_len:
            stripped.add(norm)

    # 输出：跳过被标记的行
    result_pages: list[str] = []
    for lines in page_lines:
        kept = [line for line in lines if line.strip() not in stripped]
        result_pages.append("\n".join(kept))

    return "\n\n".join(result_pages)
