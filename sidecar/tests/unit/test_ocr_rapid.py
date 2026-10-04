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
