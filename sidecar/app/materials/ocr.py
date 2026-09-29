"""OCR 后端抽象接口（TS-4）与默认实现。

Task 15：落地抽象接口 + MinerU 内置 OCR 实现。
开发时可用真实证件对比 MinerU vs PaddleOCR，决定默认后端后关闭 TS-4。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


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
