"""OCR 后端抽象接口（TS-4）与默认实现。

Task 15：落地抽象接口 + MinerU 内置 OCR 实现。
开发时可用真实证件对比 MinerU vs PaddleOCR，决定默认后端后关闭 TS-4。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

# ---------- FT-3：印章/签名噪声字符表 ----------

_SEAL_NOISE_CHARS = frozenset("〇○●◐◑◒◓◔◕★☆✡✦✧◇◆■□▢▣▤▥▦▧▨▩▪▫")


def is_seal_noise_line(text: str) -> bool:
    """判断一行是否由印章/签名误识产生的纯噪声字符组成（FT-3）。

    印章圆框、手写签名笔画常被 OCR 误识为几何符号（〇○●★☆ 等），
    此类行全部由噪声字符构成时直接丢弃，不受置信度影响。
    """
    stripped = text.strip()
    if not stripped:
        return False
    return all(ch in _SEAL_NOISE_CHARS for ch in stripped)


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
        short_line_max_len: 短行长度上限（≤此值视为短行），印章/签名噪声
            常产生 1~2 字碎片，对短行适用更高置信度阈值。
        short_line_min_score: 短行置信度下限，低于此值的短行丢弃（FT-3）。
    """

    def __init__(
        self,
        engine: Any = None,
        *,
        min_score: float = 0.5,
        short_line_max_len: int = 2,
        short_line_min_score: float = 0.7,
    ) -> None:
        self._engine = engine
        self._min_score = min_score
        self._short_line_max_len = short_line_max_len
        self._short_line_min_score = short_line_min_score

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
            text_str = str(text)
            # FT-3：印章/签名噪声字符行直接丢弃（不受置信度影响）
            if is_seal_noise_line(text_str):
                continue
            stripped = text_str.strip()
            if score is not None:
                score_val = float(score)
                # FT-3：短行（≤2字）适用更高置信度阈值
                if len(stripped) <= self._short_line_max_len:
                    if score_val < self._short_line_min_score:
                        continue
                elif score_val < self._min_score:
                    continue
            lines.append(text_str)
        return OcrResult(text="\n".join(lines), fields={})


def build_default_ocr() -> OcrBackend:
    """归档管线默认 OCR 后端工厂（API 层统一经此注入，便于切换/测试）。"""
    return RapidOcrBackend()
