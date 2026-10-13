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


def test_snippet_preserves_line_structure_for_scoring() -> None:
    """snippet 必须保留换行与足够长度：评分提取依赖按行解析（TR-11 集成修复）。"""
    long_body = "投标保证金条款说明：" + "保证金缴纳与退还规则。" * 25
    blocks = [
        {"type": "text", "text": "第一章 投标人须知", "page_idx": 0},
        {"type": "text", "text": "一、投标保证金", "page_idx": 0},
        {"type": "text", "text": long_body, "page_idx": 0},
        {"type": "text", "text": "保证金应当以支票、汇票等形式缴纳。", "page_idx": 0},
    ]
    result = extract.run_extraction(
        _fixture_chapters(),
        {"招标文件": blocks},
        selected_keys={"bid_bond"},
        generated_at="t",
    )
    match = next(i for i in result["items"] if i["key"] == "bid_bond")["matches"][0]
    snippet = match["snippet"]
    assert "\n" in snippet  # 保留行结构，供评分提取按行识别大类/评分项
    assert len(snippet) > 240  # 不再截断为 240 字符


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


# ---------- FT-6：评分标题关键词扩充（评审/评审标准类真实标题） ----------


def test_ft6_score_keywords_and_exact_keywords_extended() -> None:
    """真实监理采购文件标题实证：评审办法/评审标准/详细评审/商务评审 + 裸"评审"精确匹配。"""
    by_key = {r.key: r for r in catalog.RULES}
    tech = by_key["tech_score"]
    biz = by_key["business_score"]
    for kw in (
        "评审办法",
        "评审方法",
        "评审标准",
        "评审与磋商",
        "评审因素",
        "评分细则",
        "详细评审",
    ):
        assert kw in tech.keywords, f"tech_score 缺关键词：{kw}"
    for kw in ("商务评审", "商务部分评审"):
        assert kw in biz.keywords, f"business_score 缺关键词：{kw}"
    # 裸"评审"只允许精确匹配，不得作为子串关键词（防"评审小组/初步评审"误命中）
    assert "评审" not in tech.keywords
    assert "评审" in tech.exact_keywords
    # 规则库版本随规则扩充升级
    assert catalog.RULES_VERSION == "1.1.0"


def _ft6_chapters() -> dict[str, Any]:
    """真实结构缩影：第七章附件→（六）评审（裸标题，含评分正文）。"""
    return {
        "sources": [
            {
                "source_stem": "采购文件",
                "chapters": [
                    {
                        "id": "ch7",
                        "seq": 7,
                        "number": "第七章",
                        "title": "附件",
                        "level": 1,
                        "start_page": 11,
                        "end_page": 17,
                        "anchor": {"page_idx": 11, "bbox": None},
                        "children": [
                            {
                                "id": "ch7.6",
                                "seq": 6,
                                "number": "（六）",
                                "title": "评审",
                                "level": 3,
                                "start_page": 11,
                                "end_page": 17,
                                "anchor": {"page_idx": 11, "bbox": None},
                                "children": [],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _ft6_blocks_review() -> list[dict[str, Any]]:
    return [
        {"type": "text", "text": "第七章 附件", "page_idx": 11},
        {"type": "text", "text": "（六）评审", "page_idx": 11},
        {"type": "text", "text": "25、评审", "page_idx": 11},
        {"type": "text", "text": "由评审小组采用综合评分法评审（满分100分）。", "page_idx": 12},
        {"type": "text", "text": "商务评分 40分", "page_idx": 12},
        {"type": "text", "text": "1. 企业业绩 20分 提供业绩证明、合同复印件", "page_idx": 12},
        {"type": "text", "text": "2. 人员力量 20分 提供职称证书", "page_idx": 12},
        {"type": "text", "text": "技术评分 60分", "page_idx": 13},
        {"type": "text", "text": "1. 监理大纲 30分 提供监理大纲", "page_idx": 13},
        {"type": "text", "text": "2. 技术方案 30分", "page_idx": 13},
    ]


def test_ft6_bare_review_title_matches_tech_score_exactly() -> None:
    """竞争性磋商文件「（六）评审」裸标题经 exact_keywords 命中（4 个和县真实样本实证）。"""
    result = extract.run_extraction(
        _ft6_chapters(),
        {"采购文件": _ft6_blocks_review()},
        selected_keys={"tech_score", "business_score"},
        generated_at="t",
    )
    tech = next(i for i in result["items"] if i["key"] == "tech_score")
    assert tech["status"] == "found"
    assert tech["matches"][0]["heading"] == "（六）评审"
    snippet = tech["matches"][0]["snippet"]
    assert "综合评分法" in snippet and "监理大纲 30分" in snippet


def test_ft6_bare_review_substring_no_false_positive() -> None:
    """含"评审"但非裸标题（初步评审/评审小组类）不得经 exact 命中。"""
    chapters = {
        "sources": [
            {
                "source_stem": "采购文件",
                "chapters": [
                    {
                        "id": "ch1",
                        "seq": 1,
                        "number": "3.1",
                        "title": "初步评审",
                        "level": 3,
                        "start_page": 20,
                        "end_page": 20,
                        "anchor": {"page_idx": 20, "bbox": None},
                        "children": [],
                    }
                ],
            }
        ]
    }
    blocks = [
        {"type": "text", "text": "3.1 初步评审", "page_idx": 20},
        {"type": "text", "text": "评审小组按照初步评审标准审查。", "page_idx": 20},
    ]
    result = extract.run_extraction(
        chapters,
        {"采购文件": blocks},
        selected_keys={"tech_score"},
        generated_at="t",
    )
    tech = next(i for i in result["items"] if i["key"] == "tech_score")
    assert tech["status"] == "missing"
    assert tech["matches"] == []


def test_ft6_review_standard_and_business_review_titles_match() -> None:
    """「2.评审标准」命中 tech_score；「2.3 商务评审」命中 business_score。"""
    chapters = {
        "sources": [
            {
                "source_stem": "招标文件",
                "chapters": [
                    {
                        "id": "ch7",
                        "seq": 7,
                        "number": "第七章",
                        "title": "评标办法（综合评分法）",
                        "level": 1,
                        "start_page": 30,
                        "end_page": 35,
                        "anchor": {"page_idx": 30, "bbox": None},
                        "children": [
                            {
                                "id": "ch7.2",
                                "seq": 2,
                                "number": "2.",
                                "title": "评审标准",
                                "level": 3,
                                "start_page": 31,
                                "end_page": 34,
                                "anchor": {"page_idx": 31, "bbox": None},
                                "children": [
                                    {
                                        "id": "ch7.2.3",
                                        "seq": 3,
                                        "number": "2.3",
                                        "title": "商务评审",
                                        "level": 3,
                                        "start_page": 33,
                                        "end_page": 34,
                                        "anchor": {"page_idx": 33, "bbox": None},
                                        "children": [],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    blocks = [
        {"type": "text", "text": "第七章 评标办法（综合评分法）", "page_idx": 30},
        {"type": "text", "text": "2.评审标准", "page_idx": 31},
        {"type": "text", "text": "详细评审按评分因素打分。", "page_idx": 31},
        {"type": "text", "text": "2.3 商务评审", "page_idx": 33},
        {"type": "text", "text": "商务评分合计40分。", "page_idx": 33},
    ]
    result = extract.run_extraction(
        chapters,
        {"招标文件": blocks},
        selected_keys={"tech_score", "business_score"},
        generated_at="t",
    )
    tech = next(i for i in result["items"] if i["key"] == "tech_score")
    biz = next(i for i in result["items"] if i["key"] == "business_score")
    # 父章"评标办法"已覆盖"2.评审标准"子树 → 子节被去重，只保留祖先
    tech_headings = {m["heading"] for m in tech["matches"]}
    assert tech_headings == {"第七章评标办法（综合评分法）"}
    # business_score 未命中父章，"2.3 商务评审"子节独立保留
    assert biz["status"] == "found"
    assert biz["matches"][0]["heading"] == "2.3商务评审"


def test_ft6_ancestor_match_suppresses_descendant_duplicates() -> None:
    """同 key 命中父子章节时只保留祖先（防子树内容重复导致评分翻倍）。

    真实结构：玉带河样本"第七章 评标办法（综合评分法）"章内含子节"1.评标办法"。
    """
    chapters = {
        "sources": [
            {
                "source_stem": "招标文件",
                "chapters": [
                    {
                        "id": "ch7",
                        "seq": 7,
                        "number": "第七章",
                        "title": "评标办法（综合评分法）",
                        "level": 1,
                        "start_page": 30,
                        "end_page": 35,
                        "anchor": {"page_idx": 30, "bbox": None},
                        "children": [
                            {
                                "id": "ch7.1",
                                "seq": 1,
                                "number": "1.",
                                "title": "评标办法",
                                "level": 3,
                                "start_page": 30,
                                "end_page": 32,
                                "anchor": {"page_idx": 30, "bbox": None},
                                "children": [],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    blocks = [
        {"type": "text", "text": "第七章 评标办法（综合评分法）", "page_idx": 30},
        {"type": "text", "text": "1.评标办法", "page_idx": 30},
        {"type": "text", "text": "商务评分 40分", "page_idx": 30},
        {"type": "text", "text": "1. 企业业绩 40分", "page_idx": 31},
    ]
    result = extract.run_extraction(
        chapters,
        {"招标文件": blocks},
        selected_keys={"tech_score"},
        generated_at="t",
    )
    tech = next(i for i in result["items"] if i["key"] == "tech_score")
    assert len(tech["matches"]) == 1
    assert tech["matches"][0]["heading"] == "第七章评标办法（综合评分法）"


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
