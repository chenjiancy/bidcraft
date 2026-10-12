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


# ---------- FT-2：多专业/多字段断行合并 ----------


def test_ft2_basic_continuation_merged() -> None:
    """注册专业值跨行时合并为「、」分隔。"""
    from app.materials.ocr import merge_continuation_lines

    text = "注册专业:房屋建筑工程\n市政公用工程"
    result = merge_continuation_lines(text)
    assert "注册专业:房屋建筑工程、市政公用工程" in result


def test_ft2_multi_continuation_merged() -> None:
    """多行续行全部合并。"""
    from app.materials.ocr import merge_continuation_lines

    text = "注册专业:房屋建筑工程\n市政公用工程\n公路工程"
    result = merge_continuation_lines(text)
    assert "注册专业:房屋建筑工程、市政公用工程、公路工程" in result


def test_ft2_new_field_stops_merge() -> None:
    """含分隔符的新字段行终止续行合并。"""
    from app.materials.ocr import merge_continuation_lines

    text = "注册专业:房屋建筑工程\n市政公用工程\n有效期至:2025-12-31"
    result = merge_continuation_lines(text)
    assert "注册专业:房屋建筑工程、市政公用工程" in result
    assert "有效期至:2025-12-31" in result


def test_ft2_empty_line_stops_merge() -> None:
    """空行终止续行合并。"""
    from app.materials.ocr import merge_continuation_lines

    text = "注册专业:房屋建筑工程\n\n市政公用工程"
    result = merge_continuation_lines(text)
    assert "注册专业:房屋建筑工程" in result
    assert "市政公用工程" in result
    assert "注册专业:房屋建筑工程、市政公用工程" not in result


def test_ft2_non_multi_field_not_merged() -> None:
    """非多值字段（如姓名）后的行不合并。"""
    from app.materials.ocr import merge_continuation_lines

    text = "姓名:张三\n李四"
    result = merge_continuation_lines(text)
    assert "姓名:张三" in result
    assert "李四" in result
    assert "姓名:张三、李四" not in result


def test_ft2_no_continuation_unchanged() -> None:
    """无续行时文本不变。"""
    from app.materials.ocr import merge_continuation_lines

    text = "注册专业:房屋建筑工程\n有效期至:2025-12-31"
    result = merge_continuation_lines(text)
    assert result == text


def test_ft2_fullwidth_colon_supported() -> None:
    """全角冒号（：）也触发续行合并。"""
    from app.materials.ocr import merge_continuation_lines

    text = "注册专业：房屋建筑工程\n市政公用工程"
    result = merge_continuation_lines(text)
    assert "注册专业：房屋建筑工程、市政公用工程" in result
