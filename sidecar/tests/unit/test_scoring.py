"""Task 11 评分表规则子集单元测试（TR-11.1~11.6）。

覆盖：评分表抽取（大类/评分项/分值）、所需证明材料、门槛条件三类、
多来源合并、合计校验标红不阻断、Schema 硬校验标志位。
"""

from __future__ import annotations

import pytest

from app.rules.scoring import extract as scoring_extract
from app.rules.scoring import schema as scoring_schema
from app.rules.scoring import thresholds as thresholds_mod

_SAMPLE_SNIPPET = """商务评分部分 40分
1. 企业业绩 20分 提供近3年类似项目业绩证明、合同复印件
2. 人员力量 10分 具备不少于5名监理工程师，提供职称证书
3. 财务状况 10分 提供近3年财务审计报告
技术评分部分 60分
1. 监理大纲 30分 提供监理大纲
2. 技术方案 30分
"""


def _mk_match(snippet: str, chapter: str, stem: str = "tender", page: int = 5):
    return {
        "chapter_path": chapter,
        "source": stem,
        "snippet": snippet,
        "anchor": {"page_idx": page},
    }


# ---------- TR-11 集成修复：带编号前缀的大类行 ----------


def test_prefixed_category_lines_recognized_and_normalized() -> None:
    """真实标书常见写法"一、商务评分（满分40分）"应识别为大类，且标题行不被当成评分项。"""
    snippet = (
        "一、商务评分（满分40分）\n"
        "1. 企业业绩 20分\n"
        "2. 人员力量 10分\n"
        "3. 财务状况 10分\n"
        "二、技术评分（满分60分）\n"
        "1. 监理大纲 30分\n"
        "2. 技术方案 30分\n"
    )
    payload = scoring_extract.extract_score_table(
        [_mk_match(snippet, "第三章 评标办法")], generated_at="t"
    )
    cats = payload["categories"]
    assert len(cats) == 2
    assert cats[0]["name"] == "商务评分"
    assert cats[1]["name"] == "技术评分"
    # 大类标题行不得变成评分项；合计 100
    assert payload["total_score_check"]["actual"] == 100.0
    assert payload["total_score_check"]["ok"] is True
    assert all("满分" not in item["name"] for c in cats for item in c["items"])
    # "技术方案 30分" 虽是编号行且含"技术"，但无总分信号，不得误判为大类
    tech_cat = cats[1]
    assert [i["name"] for i in tech_cat["items"]] == [
        "监理大纲",
        "技术方案",
    ]


# ---------- TR-11.3 门槛条件 ----------


def test_thresholds_date_amount_quantity():
    th = thresholds_mod.find_thresholds("提供近3年业绩，合同金额≥100万元，不少于3个")
    kinds = {t.kind for t in th}
    assert kinds == {"date", "amount", "quantity"}
    assert any(t.value == "3年" for t in th if t.kind == "date")
    assert any(t.value == "100万元" for t in th if t.kind == "amount")
    assert any(t.value == "3个" for t in th if t.kind == "quantity")


def test_thresholds_empty_on_plain():
    assert thresholds_mod.find_thresholds("本项无门槛") == []


# ---------- TR-11.1/11.2/11.4 抽取与合并 ----------


def test_extract_categories_and_items():
    matches = [_mk_match(_SAMPLE_SNIPPET, "第三章 评分办法")]
    payload = scoring_extract.extract_score_table(matches, generated_at="2026-09-29T00:00:00")
    cats = payload["categories"]
    assert len(cats) == 2
    names = {c["name"] for c in cats}
    assert any("商务" in n for n in names) and any("技术" in n for n in names)

    biz = next(c for c in cats if "商务" in c["name"])
    assert biz["subtotal"] == 40.0
    assert len(biz["items"]) == 3
    perf = next(i for i in biz["items"] if "企业业绩" in i["name"])
    assert perf["score"] == 20.0
    # TR-11.2：材料名称抽取
    assert any("业绩证明" in m or "合同" in m for m in perf["materials"])
    # TR-11.3：门槛
    assert any(t["kind"] == "date" for t in perf["thresholds"])

    tech = next(c for c in cats if "技术" in c["name"])
    assert tech["subtotal"] == 60.0


def test_extract_multi_source_merge():
    """多来源合并：两段评分办法合并为单一 payload，category 标识来源章节。"""
    m1 = _mk_match("商务评分 30分\n1. 业绩 30分 提供业绩证明", "第三章 商务评分", "a", 1)
    m2 = _mk_match("技术评分 70分\n1. 监理大纲 70分", "第四章 技术评分", "b", 2)
    payload = scoring_extract.extract_score_table([m1, m2], generated_at="t")
    assert len(payload["categories"]) == 2
    srcs = {c["source_stem"] for c in payload["categories"]}
    assert srcs == {"a", "b"}
    assert payload["total_score_check"]["actual"] == 100.0
    assert payload["total_score_check"]["ok"] is True


def test_extract_sum_mismatch_red_flag_not_blocking():
    """合计≠100 标红但不阻断产出（TR-11.5）。"""
    m = _mk_match("商务评分 30分\n1. 业绩 30分", "第三章 评分", "a", 1)
    payload = scoring_extract.extract_score_table([m], generated_at="t")
    assert payload["categories"]  # 仍产出
    assert payload["total_score_check"]["ok"] is False
    assert payload["total_score_check"]["actual"] == 30.0
    assert any(f["type"] == "score_sum_mismatch" for f in payload["red_flags"])


def test_extract_unrecognized_threshold_flagged():
    """含"须/提供"但无法结构化门槛 → 存原文 + 标红（TR-11.3 兜底）。"""
    m = _mk_match("商务评分 20分\n1. 特殊要求 20分 须提供某种无法解析的资质条件", "第x章", "a", 1)
    payload = scoring_extract.extract_score_table([m], generated_at="t")
    items = payload["categories"][0]["items"]
    target = next(i for i in items if "特殊要求" in i["name"])
    assert target["unrecognized"] != ""
    assert any(f["type"] == "threshold_unrecognized" for f in payload["red_flags"])


def test_extract_deterministic():
    """TR-11.6 前置：同输入固定输出（可重复）。"""
    matches = [_mk_match(_SAMPLE_SNIPPET, "第三章 评分办法")]
    p1 = scoring_extract.extract_score_table(matches, generated_at="t")
    p2 = scoring_extract.extract_score_table(matches, generated_at="t")
    assert p1 == p2


# ---------- TR-11.6 Schema 硬校验 ----------


def test_schema_valid_marks_flag():
    matches = [_mk_match(_SAMPLE_SNIPPET, "第三章 评分办法")]
    payload = scoring_extract.extract_score_table(matches, generated_at="t")
    ok, errors = scoring_schema.validate_score_table(payload)
    assert ok, errors
    assert payload["schema_validated"] is True


def test_schema_invalid_marks_flag_and_errors():
    payload = {"version": 1}  # 缺字段
    ok, errors = scoring_schema.validate_score_table(payload)
    assert not ok
    assert payload["schema_validated"] is False
    assert errors


# ---------- FT-6：空内容评分章节（公告声明行/纯流程节）不静默，红标披露 ----------


def test_ft6_version_bumped():
    assert scoring_extract.SCORING_VERSION == "1.1.0"


def test_ft6_empty_snippet_match_red_flagged_but_real_match_still_extracts():
    """公告行"评标办法：综合评分法"（空 snippet）+ 真实评审章 → 正常产出 + 空章红标。

    真实证据：和县老旧小区走查样本 tech_score 唯一命中是采购公告内的空声明行，
    真正评分表在「（六）评审」章。
    """
    empty_decl = _mk_match("", "第一章采购公告 / 7.评标办法：综合评分法", page=2)
    real = _mk_match(
        "商务评分 40分\n1. 企业业绩 40分 提供业绩证明\n技术评分 60分\n1. 监理大纲 60分",
        "第七章附件 / （六）评审",
        page=11,
    )
    payload = scoring_extract.extract_score_table([empty_decl, real], generated_at="t")
    assert payload["categories"]
    assert payload["total_score_check"]["ok"] is True
    empty_flags = [f for f in payload["red_flags"] if f["type"] == "score_section_empty"]
    assert len(empty_flags) == 1
    assert "评标办法" in empty_flags[0]["source_chapter"]


def test_ft6_all_empty_matches_only_red_flags_no_categories():
    """全部评分章节均无评分内容 → 不产 category，逐章红标（service 层硬门禁据此阻断）。"""
    payload = scoring_extract.extract_score_table(
        [
            _mk_match("", "第七章 / 1.评标办法"),
            _mk_match("评审小组按程序评审，无分值表。", "第七章 / 2.评审标准"),
        ],
        generated_at="t",
    )
    assert payload["categories"] == []
    empty_flags = [f for f in payload["red_flags"] if f["type"] == "score_section_empty"]
    assert len(empty_flags) == 2


# ---------- FT-5：多分值评分行取满分值而非首值 ----------


def test_ft5_multi_score_line_takes_max_not_first() -> None:
    """「每项5分，满分20分」应取 20（满分值），非首值 5。"""
    snippet = "技术评分 100分\n1. 技术方案 每项5分，满分20分\n2. 监理大纲 80分"
    payload = scoring_extract.extract_score_table(
        [_mk_match(snippet, "第三章 评标办法")], generated_at="t"
    )
    items = payload["categories"][0]["items"]
    target = next(i for i in items if "技术方案" in i["name"])
    assert target["score"] == 20.0


def test_ft5_multi_score_line_variants() -> None:
    """满分/共/总计/合计 后的数值应被取为评分项分值。"""
    cases = [
        ("1. 业绩评分 每项5分，满分20分", 20.0),
        ("1. 业绩评分 每项5分，共20分", 20.0),
        ("1. 业绩评分 每项5分，总计20分", 20.0),
        ("1. 业绩评分 每项5分，合计20分", 20.0),
    ]
    for line, expected in cases:
        snippet = f"商务评分 40分\n{line}"
        payload = scoring_extract.extract_score_table(
            [_mk_match(snippet, "第三章")], generated_at="t"
        )
        items = payload["categories"][0]["items"]
        assert items[0]["score"] == expected, f"Failed for: {line}"


def test_ft5_simple_score_unchanged() -> None:
    """简单行「企业业绩 20分」不受 FT-5 改动影响，仍取 20。"""
    snippet = "商务评分 40分\n1. 企业业绩 20分\n2. 人员力量 20分"
    payload = scoring_extract.extract_score_table([_mk_match(snippet, "第三章")], generated_at="t")
    items = payload["categories"][0]["items"]
    assert items[0]["score"] == 20.0
    assert items[1]["score"] == 20.0


def test_ft5_name_excludes_full_score_marker() -> None:
    """满分标记不应残留在评分项名称中。"""
    snippet = "技术评分 100分\n1. 技术方案评分 每项5分，满分20分\n2. 其他 80分"
    payload = scoring_extract.extract_score_table([_mk_match(snippet, "第三章")], generated_at="t")
    items = payload["categories"][0]["items"]
    name = items[0]["name"]
    assert "满分" not in name
    assert "每项" not in name
    assert "技术方案" in name


def test_schema_rejects_bad_threshold_kind():
    payload = {
        "version": 1,
        "scoring_version": "1.0.0",
        "generated_at": "t",
        "categories": [
            {
                "name": "商务",
                "source_chapter": "第三章",
                "source_stem": "a",
                "subtotal": 10.0,
                "items": [
                    {
                        "name": "业绩",
                        "score": 10.0,
                        "materials": [],
                        "thresholds": [{"kind": "bad", "text": "x", "value": "y"}],
                    }
                ],
            }
        ],
        "total_score_check": {"expected": 100, "actual": 10, "ok": False},
        "red_flags": [],
    }
    ok, errors = scoring_schema.validate_score_table(payload)
    assert not ok
    assert any("kind" in e or "enum" in e for e in errors)


# 防 pytest 未用告警
_ = pytest
