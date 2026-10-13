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


# ---------- FT-3：印章/签名区域误识降噪 ----------


def test_ft3_short_mid_confidence_line_filtered() -> None:
    """短行（≤2字）中置信度（0.5~0.7）视为印章/签名噪声，过滤。"""
    engine = _FakeEngine(_FakeOutput(("签", "名称：某某公司"), (0.55, 0.95)))
    result = RapidOcrBackend(engine=engine).recognize(b"x")
    assert "签" not in result.text
    assert "名称：某某公司" in result.text


def test_ft3_short_high_confidence_line_kept() -> None:
    """短行高置信度（≥0.8）保留（可能是真实短文本如姓名）。"""
    engine = _FakeEngine(_FakeOutput(("张三", "名称：某某公司"), (0.85, 0.95)))
    result = RapidOcrBackend(engine=engine).recognize(b"x")
    assert "张三" in result.text
    assert "名称：某某公司" in result.text


def test_ft3_seal_artifact_chars_filtered() -> None:
    """印章/签名产生的噪声字符（〇○●★☆）无论置信度都过滤。"""
    engine = _FakeEngine(_FakeOutput(("〇○●", "名称：某某公司"), (0.95, 0.90)))
    result = RapidOcrBackend(engine=engine).recognize(b"x")
    assert "〇○●" not in result.text
    assert "名称：某某公司" in result.text


def test_ft3_normal_long_line_mid_confidence_kept() -> None:
    """正常长行中置信度（0.5~0.7）保留（非印章噪声）。"""
    engine = _FakeEngine(_FakeOutput(("统一社会信用代码：1234567890",), (0.55,)))
    result = RapidOcrBackend(engine=engine).recognize(b"x")
    assert "统一社会信用代码：1234567890" in result.text


def test_ft3_single_char_mid_confidence_filtered() -> None:
    """单字符中置信度行视为签名噪声，过滤。"""
    engine = _FakeEngine(_FakeOutput(("字", "名称：某某公司"), (0.6, 0.95)))
    result = RapidOcrBackend(engine=engine).recognize(b"x")
    assert "字" not in result.text


def test_ft3_is_seal_noise_line_pure_artifact() -> None:
    """is_seal_noise_line 识别纯印章/几何噪声字符行。"""
    from app.materials.ocr import is_seal_noise_line

    assert is_seal_noise_line("〇○●")
    assert is_seal_noise_line("★☆")
    assert not is_seal_noise_line("名称：某某公司")
    assert not is_seal_noise_line("张三")
