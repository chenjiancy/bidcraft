"""RapidOcrBackend 适配器单测（TS-4 选定：RapidOCR PP-OCRv6 ONNX）。

真实引擎的端到端识别在 tests/engine 下另测；此处对第三方边界注入假引擎，
验证适配器本身的行拼接、低分过滤与字节透传。
"""

from app.materials.ocr import OcrBackend, OcrResult, RapidOcrBackend


class _FakeOutput:
    def __init__(self, txts: tuple[str, ...], scores: tuple[float, ...]) -> None:
        self.txts = txts
        self.scores = scores


class _FakeEngine:
    def __init__(self, output: _FakeOutput) -> None:
        self._output = output
        self.calls: list[bytes] = []

    def __call__(self, img_content: bytes, **_kw: object) -> _FakeOutput:
        self.calls.append(img_content)
        return self._output


def test_recognize_joins_lines_and_passes_bytes() -> None:
    engine = _FakeEngine(_FakeOutput(("营业执照", "名称：某某公司"), (0.99, 0.98)))
    result = RapidOcrBackend(engine=engine).recognize(b"png-bytes")
    assert isinstance(result, OcrResult)
    assert result.text == "营业执照\n名称：某某公司"
    assert engine.calls == [b"png-bytes"]


def test_recognize_filters_lines_below_min_score() -> None:
    engine = _FakeEngine(_FakeOutput(("清晰行", "模糊行"), (0.99, 0.3)))
    result = RapidOcrBackend(engine=engine, min_score=0.5).recognize(b"x")
    assert result.text == "清晰行"


def test_recognize_empty_output_returns_empty_text() -> None:
    engine = _FakeEngine(_FakeOutput((), ()))
    result = RapidOcrBackend(engine=engine).recognize(b"x")
    assert result.text == ""


def test_rapidocr_backend_is_ocr_backend() -> None:
    assert isinstance(
        RapidOcrBackend(
            engine=_FakeEngine(_FakeOutput((), ())),
        ),
        OcrBackend,
    )


# ---------- FT-1：扫描水印/页眉重复行过滤 ----------


def test_ft1_watermark_stripped_from_multi_page() -> None:
    """跨页重复短行（如「汉王扫描王」）应被剥离。"""
    from app.materials.ocr import strip_watermark_lines

    pages = [
        "汉王扫描王\n名称：某某公司\n统一社会信用代码：123",
        "汉王扫描王\n法定代表人：张三\n注册资本：100万",
        "汉王扫描王\n成立日期：2020年\n经营范围：监理",
    ]
    result = strip_watermark_lines(pages)
    assert "汉王扫描王" not in result
    assert "名称：某某公司" in result
    assert "法定代表人：张三" in result


def test_ft1_short_header_repeated_stripped() -> None:
    """短页眉行跨页重复应被剥离（非水印关键词也可）。"""
    from app.materials.ocr import strip_watermark_lines

    pages = [
        "某某监理有限公司\n正文内容A",
        "某某监理有限公司\n正文内容B",
        "某某监理有限公司\n正文内容C",
    ]
    result = strip_watermark_lines(pages)
    assert "某某监理有限公司" not in result
    assert "正文内容A" in result


def test_ft1_legitimate_long_lines_preserved() -> None:
    """较长行即使跨页重复也保留（可能是正常内容）。"""
    from app.materials.ocr import strip_watermark_lines

    long_line = "本章节适用于所有投标供应商须严格按照招标文件要求执行"
    pages = [f"{long_line}\n内容A", f"{long_line}\n内容B"]
    result = strip_watermark_lines(pages)
    assert long_line in result


def test_ft1_single_page_not_stripped() -> None:
    """仅出现在 1 页的行不剥离（不够成水印模式）。"""
    from app.materials.ocr import strip_watermark_lines

    pages = ["扫描王\n内容A", "内容B"]
    result = strip_watermark_lines(pages)
    assert "扫描王" in result


def test_ft1_empty_pages() -> None:
    """空页列表返回空字符串。"""
    from app.materials.ocr import strip_watermark_lines

    assert strip_watermark_lines([]) == ""
    assert strip_watermark_lines([""]) == ""
