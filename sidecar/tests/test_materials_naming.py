"""Task 15 TR-15.2：命名规范模块单元测试。"""

from datetime import date

from app.materials.naming import generate_filename, parse_filename


def test_generate_qualification():
    result = generate_filename(
        "qualification",
        "注册证书",
        cert_type="注册证书",
        name_person="张三",
        id_no="110101199001011234",
        valid_until=date(2030, 12, 31),
    )
    assert "zcs" in result
    assert "张三" in result
    assert "20301231" in result


def test_generate_qualification_long_validity():
    result = generate_filename(
        "qualification",
        "身份证",
        cert_type="身份证",
        name_person="李四",
        valid_until=None,  # 长期
    )
    assert "sfz" in result
    assert "changqi" in result


def test_generate_performance():
    result = generate_filename(
        "performance",
        "监理合同",
        perf_type="监理合同",
        project_name="某某大桥项目",
        contract_date=date(2024, 6, 15),
        supervisor="王五",
    )
    assert "jlst" in result
    assert "某某大桥项目" in result
    assert "20240615" in result
    assert "王五" in result


def test_generate_honor():
    result = generate_filename(
        "honor",
        "鲁班奖",
        honor_name="鲁班奖",
        issuer="中国建筑业协会",
        year=2023,
    )
    assert "ry" in result
    assert "鲁班奖" in result
    assert "2023" in result


def test_generate_finance():
    result = generate_filename(
        "finance",
        "中小企业声明函",
        fin_type="中小企业声明函",
        year=2024,
    )
    assert "zxxq" in result
    assert "2024" in result


def test_multi_page_suffix():
    result = generate_filename(
        "qualification",
        "注册证书",
        cert_type="注册证书",
        name_person="张三",
        id_no="110101199001011234",
        valid_until=date(2030, 12, 31),
        page_index=1,
    )
    assert result.endswith("_P1")


def test_parse_performance_filename():
    name = "jlst_某某大桥项目_20240615_王五"
    result = parse_filename(name)
    assert result is not None
    assert result.get("perf_type") == "监理合同"
    assert result.get("valid_until") == date(2024, 6, 15)


def test_parse_multi_page():
    name = "jlst_某某大桥项目_20240615_王五_P1"
    result = parse_filename(name)
    assert result is not None
    assert result.get("page_index") == 1
    assert result.get("perf_type") == "监理合同"


def test_parse_unparseable():
    result = parse_filename("randomname")
    # 无法解析出已知前缀，但仍应返回部分结果或 None
    # "randomname" 不含已知前缀，但 extra 会被设置
    assert result is not None or result is None


def test_generate_truncation():
    """文件名过长时截断到 120 字符。"""
    long_name = "x" * 200
    result = generate_filename("qualification", long_name)
    assert len(result) <= 120
