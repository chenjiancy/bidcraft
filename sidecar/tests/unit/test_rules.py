"""规则库单测（TR-10.1~10.5）：分类 / 锚定校验 / 确定性 / 术语 / 子节性质。"""

from typing import Any

from app.rules import catalog, extract, nature, terms
from app.rules.anchor import normalize, verify_anchor

# ---------- TR-10.1：规则库分类 ----------


def test_rules_cover_all_18_config_keys_with_categories() -> None:
    from app.parse.config import ALL_KEYS

    assert {r.key for r in catalog.RULES} == set(ALL_KEYS)
    by_key = {r.key: r for r in catalog.RULES}
    assert by_key["qualification_review"].category == "资格条款"
    assert by_key["bid_bond"].category == "资格条款"
    assert by_key["invalid_bid"].category == "废标条款"
    assert by_key["compliance_review"].category == "废标条款"
    assert by_key["business_score"].category == "商务评分"
    assert by_key["tech_score"].category == "技术要求"
    assert by_key["procurement_list"].category == "技术要求"
    assert by_key["project_overview"].category == "通用"


def test_find_constraints_page_amount_period_social_quantity() -> None:
    text = (
        "监理大纲页数不超过50页。\n"
        "投标保证金为人民币2万元。\n"
        "服务期限365个日历日。\n"
        "拟投入人员须连续6个月的社保证明。\n"
        "投标文件正本1份、副本4份。\n"
    )
    kinds = {c.kind for c in catalog.find_constraints(text, page_idx=3)}
    assert kinds == {"page_limit", "amount", "period", "social_security", "quantity"}
    page = next(c for c in catalog.find_constraints(text) if c.kind == "page_limit")
    assert page.value == "50页"
    social = next(c for c in catalog.find_constraints(text) if c.kind == "social_security")
    assert social.value == "6个月"


# ---------- TR-10.2：原文锚定校验 ----------


def test_verify_anchor_normalizes_whitespace() -> None:
    source = "投标文件 正本　1 份\n副本 4 份"
    assert verify_anchor("投标文件正本1份", source) is True
    assert verify_anchor("正本 2 份", source) is False
    assert verify_anchor("", source) is False
    assert normalize("a　 b\nc") == "abc"


# ---------- TR-10.3：确定性可重复 ----------


def _fixture_chapters() -> dict[str, Any]:
    return {
        "sources": [
            {
                "source_stem": "招标文件",
                "chapters": [
                    {
                        "id": "ch1",
                        "seq": 1,
                        "number": "第一章",
                        "title": "投标人须知",
                        "level": 1,
                        "start_page": 0,
                        "end_page": 1,
                        "anchor": {"page_idx": 0, "bbox": [1.0, 2.0, 3.0, 4.0]},
                        "children": [
                            {
                                "id": "ch1.1",
                                "seq": 1,
                                "number": "一、",
                                "title": "投标保证金",
                                "level": 2,
                                "start_page": 0,
                                "end_page": 0,
                                "anchor": {"page_idx": 0, "bbox": [1.0, 5.0, 3.0, 6.0]},
                                "children": [],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _fixture_blocks() -> list[dict[str, Any]]:
    return [
        {"type": "text", "text": "第一章 投标人须知", "page_idx": 0},
        {"type": "text", "text": "一、投标保证金", "page_idx": 0},
        {"type": "text", "text": "投标保证金为人民币5万元，投标截止前3日缴纳。", "page_idx": 0},
        {"type": "text", "text": "其他正文。", "page_idx": 1},
    ]


def test_extraction_deterministic_for_fixed_input() -> None:
    kwargs = {
        "selected_keys": {"bid_bond"},
        "generated_at": "2026-09-29T00:00:00+00:00",
    }
    r1 = extract.run_extraction(_fixture_chapters(), {"招标文件": _fixture_blocks()}, **kwargs)
    r2 = extract.run_extraction(_fixture_chapters(), {"招标文件": _fixture_blocks()}, **kwargs)
    assert r1 == r2
    item = next(i for i in r1["items"] if i["key"] == "bid_bond")
    assert item["status"] == "found"
    assert item["category"] == "资格条款"
    match = item["matches"][0]
    assert match["anchor"]["page_idx"] == 0
    assert match["anchor_verified"] is True
    assert any(c["kind"] == "amount" and c["value"] == "5万元" for c in match["constraints"])
    assert all(c["anchor_verified"] for c in match["constraints"])


def test_unselected_item_off_and_missing_item_red_flag() -> None:
    result = extract.run_extraction(
        _fixture_chapters(),
        {"招标文件": _fixture_blocks()},
        selected_keys={"invalid_bid"},  # 文中无废标章节
        generated_at="t",
    )
    off_item = next(i for i in result["items"] if i["key"] == "bid_bond")
    assert off_item["status"] == "off" and off_item["matches"] == []
    missing = next(i for i in result["items"] if i["key"] == "invalid_bid")
    assert missing["status"] == "missing"
    assert any(
        f["type"] == "item_missing" and f["item"] == "invalid_bid" for f in result["red_flags"]
    )


# ---------- TR-10.4：术语识别 ----------


def test_detect_doc_type_tender_procurement_inquiry() -> None:
    assert terms.detect_doc_type("本项目为公开招标，投标人应提交投标文件与投标函。") == "招标"
    assert terms.detect_doc_type("政府采购文件，供应商应提交响应文件与报价函。") == "采购"
    assert terms.detect_doc_type("询比价采购邀请，请提交询比价响应文件。") == "询比价"
    assert terms.detect_doc_type("没有任何特征词的文本。") == "未知"


def test_term_systems_and_no_source_rewrite() -> None:
    tender = terms.term_set_for("招标")
    assert tender.words["主体"] == "投标人"
    assert tender.words["文件"] == "投标文件"
    inquiry = terms.term_set_for("询比价")
    assert inquiry.words["文件"] == "询比价响应文件"
    # 未知回退招标体系；原文不在术语模块中被改写（模块只读）
    assert terms.term_set_for(None).doc_type == "招标"
    assert terms.build_dict_payload("采购")["主体"] == "供应商"


# ---------- TR-10.5：混合章节子节性质标注 ----------


def test_nature_annotation_business_tech_general() -> None:
    nodes: list[dict[str, Any]] = [
        {
            "id": "ch5",
            "title": "服务方案",
            "anchor": {"page_idx": 10, "bbox": None},
            "children": [
                {
                    "id": "ch5.1",
                    "title": "供应商介绍与人员力量",
                    "anchor": {"page_idx": 10, "bbox": None},
                    "children": [],
                },
                {
                    "id": "ch5.2",
                    "title": "监理大纲",
                    "anchor": {"page_idx": 12, "bbox": None},
                    "children": [],
                },
                {
                    "id": "ch5.3",
                    "title": "其他说明",
                    "anchor": {"page_idx": 20, "bbox": None},
                    "children": [],
                },
            ],
        }
    ]
    records = nature.annotate_tree(nodes)
    by_id = {r.section_id: r for r in records}
    assert by_id["ch5"].nature == "tech"  # 服务方案 → 技术
    assert by_id["ch5.1"].nature == "business"
    assert by_id["ch5.2"].nature == "tech"
    assert by_id["ch5.3"].nature == "general"
    assert by_id["ch5.1"].chapter_id == "ch5"
    # 每个子节都有记录（状态机按子节记录状态的结构基础）
    assert {r.section_id for r in records} == {"ch5", "ch5.1", "ch5.2", "ch5.3"}


def test_extraction_contains_sections_nature() -> None:
    result = extract.run_extraction(
        _fixture_chapters(),
        {"招标文件": _fixture_blocks()},
        selected_keys=set(),
        generated_at="t",
    )
    records = result["sections_nature"]["招标文件"]
    assert {r["section_id"] for r in records} == {"ch1", "ch1.1"}
    assert all(r["nature"] in ("business", "tech", "general") for r in records)
    # 全部未勾选时无 red flag
    assert result["red_flags"] == []
