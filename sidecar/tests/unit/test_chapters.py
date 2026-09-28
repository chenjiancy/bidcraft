"""章节切分单元测试（TR-8.4 结构正确 / TR-8.6 噪声容错）。

直接构造 MinerU content_list 风格的 block，不依赖真实解析产物；
真实 MinerU 字段名一致性由 tests/engine 真实样本测试把关。
"""

from app.parse.chapters import (
    build_tree,
    detect_toc_pages,
    extract_headings,
    split_chapters,
)


def _block(text: str, page: int, *, level: int | None = None, bbox=None) -> dict:
    block: dict = {"type": "text", "text": text, "page_idx": page}
    if level is not None:
        block["text_level"] = level
    if bbox is not None:
        block["bbox"] = bbox
    return block


def _para(page: int, text: str) -> dict:
    return {"type": "text", "text": text, "page_idx": page}


def _sample_blocks() -> list[dict]:
    blocks: list[dict] = []
    # page 0：目录页（"目录"标题 + 点线引导页码；故意列一个正文没有的第三章——噪声）
    blocks.append(_block("目录", 0, level=1))
    blocks.append(_block("第一章 招标公告 ............ 1", 0))
    blocks.append(_block("一、项目概况 ............ 1", 0))
    blocks.append(_block("第二章 投标人须知 ............ 5", 0))
    blocks.append(_block("第三章 评标办法 ............ 9", 0))  # 正文缺失
    # page 1：第一章正文
    blocks.append(_block("第一章 招标公告", 1, level=1, bbox=[100, 80, 400, 120]))
    blocks.append(_para(1, "受采购人委托，现就有关项目公开招标。" * 3))
    blocks.append(_block("一、项目概况", 1, level=2))
    blocks.append(_para(1, "本项目位于某市某区。"))
    blocks.append(_block("（一）项目背景", 2))  # 编号模式识别，无 text_level
    blocks.append(_para(2, "背景情况说明。"))
    # page 2 页眉重复第一章标题（噪声，应被过滤）
    blocks.append(_block("第一章 招标公告", 2, level=1))
    blocks.append(_block("（二）建设规模", 3))
    # page 4：第二章（编号故意跳号，只有"四、"，切分不受影响）
    blocks.append(_block("第二章 投标人须知", 4, level=1, bbox=[90, 80, 420, 120]))
    blocks.append(_block("四、招标文件组成", 4))
    blocks.append(_para(4, "招标文件包括下列内容。"))
    return blocks


def test_detect_toc_pages() -> None:
    toc = detect_toc_pages(_sample_blocks())
    assert toc == {0}


def test_body_headings_exclude_toc_and_page_header() -> None:
    blocks = _sample_blocks()
    toc = detect_toc_pages(blocks)
    body, toc_headings, _ = extract_headings(blocks, toc)
    body_titles = [(h.title, h.level, h.page_idx) for h in body]
    # 目录条目不进正文
    assert all(h.page_idx != 0 for h in body)
    # 页眉重复的第一章（page 2）被过滤：正文只剩 page1 一个第一章
    assert body_titles.count(("招标公告", 1, 1)) == 1
    assert ("招标公告", 1, 2) not in body_titles
    # 中文编号识别
    assert ("项目概况", 2, 1) in body_titles
    assert ("项目背景", 3, 2) in body_titles
    assert ("招标文件组成", 2, 4) in body_titles  # "四、"为二级标题，跳号仍识别
    assert toc_headings  # 目录条目有抽取


def test_build_tree_hierarchy_and_pages() -> None:
    blocks = _sample_blocks()
    body, _, _ = extract_headings(blocks, detect_toc_pages(blocks))
    roots = build_tree(body, page_count=10)
    assert [r.title for r in roots] == ["招标公告", "投标人须知"]

    ch1, ch2 = roots
    assert ch1.id == "ch1" and ch1.seq == 1
    assert ch1.start_page == 1
    assert ch1.end_page == ch2.start_page - 1  # 章起止页
    assert ch2.end_page == 9  # 最后一章到文档末页（page_count-1）

    # 章 → 子节层级
    sec1 = ch1.children[0]
    assert sec1.title == "项目概况"
    assert sec1.id == "ch1.1"
    sub = sec1.children[0]
    assert sub.title == "项目背景"
    assert sub.id == "ch1.1.1"

    # 原文锚定：页码 + bbox
    assert ch1.page_idx == 1
    assert ch1.bbox == [100, 80, 400, 120]


def test_split_chapters_full_result_and_toc_noise() -> None:
    result = split_chapters(_sample_blocks(), "招标文件正文")
    assert result["source_stem"] == "招标文件正文"
    assert result["page_count"] == 5
    assert result["stats"]["chapter_count"] == 2
    assert result["stats"]["section_count"] >= 3

    cross = result["toc_crosscheck"]
    # 目录第三章正文缺失 → 记为噪声而非错误
    joined = "\n".join(cross["noise"])
    assert "第三章" in joined or "评标办法" in joined
    assert cross["matched"] >= 2  # 第一章/第二章按顺序匹配


def test_bare_title_and_numbering_noise() -> None:
    """无编号常见标题 + 编号跳号/重复不阻断切分。"""
    blocks = [
        _block("投标函", 0),
        _para(0, "致：采购人" * 5),
        _block("一、报价说明", 1),
        _block("一、报价说明", 2),  # 紧邻重复（页眉窗口内被过滤）
        _block("二、其他", 4),
    ]
    body, _, _ = extract_headings(blocks, set())
    roots = build_tree(body, page_count=5)

    def _titles(nodes) -> list[str]:
        out: list[str] = []
        for n in nodes:
            out.append(n.title)
            out.extend(_titles(n.children))
        return out

    titles = _titles(roots)
    assert "投标函" in titles
    assert titles.count("报价说明") == 1  # 重复项被页眉规则消化
    assert "其他" in titles


def test_spaced_toc_title_and_form_noise() -> None:
    """真实样本：'目 录'（含空格）仍判目录页；表单误标 text_level 被消化。"""
    blocks = [
        _block("目 录", 0, level=1),
        _block("第一章 总则 ........ 3", 0),
        _block("第一章 总则", 3, level=1),
        _block("本项目履约保证金：", 4, level=2),
        _block("□免收", 4, level=3),
        _block("（1）金额：", 4, level=3),
        _block("合同价的2%", 4, level=3),
    ]
    toc = detect_toc_pages(blocks)
    assert toc == {0}
    body, _, noise = extract_headings(blocks, toc)
    titles = [h.title for h in body]
    assert "总则" in titles
    assert not {"本项目履约保证金：", "□免收", "（1）金额：", "合同价的2%"} & set(titles)
    assert noise >= 4


def test_bare_l1_stack_on_same_page_dropped() -> None:
    """同页 4 个无编号一级标题（'采购文件包括'式文件名列举）整组丢弃。"""
    blocks = [
        _block("第三章 供应商须知", 2, level=1),
        _block("采购公告", 5, level=1),
        _block("供应商须知前附表", 5, level=1),
        _block("采购合同格式", 5, level=1),
        _block("采购内容及总体要求", 5, level=1),
    ]
    body, _, noise = extract_headings(blocks, set())
    titles = [h.title for h in body]
    assert "供应商须知" in titles
    assert "采购公告" not in titles
    assert noise == 4
    roots = build_tree(body, page_count=8)
    assert [r.title for r in roots] == ["供应商须知"]


def test_numbered_chapter_stack_on_same_page_dropped() -> None:
    """真实回归：'采购文件包括'清单中 7 个'第X章'挤在同一页，整组丢弃。"""
    blocks = [
        _block("第一章 采购公告", 5, level=1),
        _block("第二章 供应商须知前附表", 5, level=1),
        _block("第三章 供应商须知", 5, level=1),
        _block("第四章 采购合同格式", 5, level=1),
        _block("第五章 采购内容及总体要求", 5, level=1),
        _block("第六章 响应文件格式", 5, level=1),
        _block("第七章 系统提交要求", 5, level=1),
        _block("采购公告", 12, level=1),  # 正文真实章（远离清单页，保留）
    ]
    body, _, noise = extract_headings(blocks, set())
    titles = [h.title for h in body]
    assert "采购公告" in titles
    assert sum(1 for t in titles if t in {"供应商须知前附表", "采购合同格式", "系统提交要求"}) == 0
    assert noise == 7
    roots = build_tree(body, page_count=14)
    assert [r.title for r in roots] == ["采购公告"]


def test_same_page_headings_endpage_not_inverted() -> None:
    """同页连续标题的 end_page 不得倒挂到 start_page 之前。"""
    blocks = [
        _block("第一章 总则", 3, level=1),
        _block("一、适用范围", 3, level=2),
        _block("二、定义", 3, level=2),
    ]
    roots = build_tree(extract_headings(blocks, set())[0], page_count=6)
    ch1 = roots[0]
    assert ch1.start_page == 3 and ch1.end_page == 5
    assert all(c.end_page >= c.start_page for c in ch1.children)


def test_empty_document_does_not_crash() -> None:
    result = split_chapters([_para(0, "没有任何标题的文档。")], "x")
    assert result["chapters"] == []
    assert result["stats"]["chapter_count"] == 0
