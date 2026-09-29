"""动态关键字词典管理（FR-4 第 4 点）。

词典文件：`<enterprise>/config/keywords.dict.json`
格式::

    {
      "certificate_types": ["注册证书", "岗位证书", ...],
      "person_names": ["张三", "李四", ...],
      "project_keywords": ["某某大桥", ...],
      "honor_types": ["鲁班奖", "国优", ...]
    }

素材重命名、归档扫描、标书制作发现"表述不一致但素材一致"时自动更新。
用户可手工维护。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class KeywordsDict:
    """关键字词典数据结构。"""

    certificate_types: list[str] = field(default_factory=list)
    person_names: list[str] = field(default_factory=list)
    project_keywords: list[str] = field(default_factory=list)
    honor_types: list[str] = field(default_factory=list)
    custom: list[str] = field(default_factory=list)

    # ---------- 序列化 ----------

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, data: str) -> KeywordsDict:
        obj = json.loads(data)
        known = {f.name for f in cls.__dataclass_fields__.values()}
        cleaned = {k: v for k, v in obj.items() if k in known}
        return cls(**cleaned)

    # ---------- 操作 ----------

    def add(self, key: str, value: str, *, category: str = "custom") -> bool:
        """向指定类别添加关键词；已存在返回 False。"""
        lst = self.custom if category == "custom" else getattr(self, category, self.custom)
        if value not in lst:
            lst.append(value)
            return True
        return False

    def remove(self, value: str, *, category: str = "custom") -> bool:
        lst = self.custom if category == "custom" else getattr(self, category, self.custom)
        if value in lst:
            lst.remove(value)
            return True
        return False

    def all_keywords(self) -> Sequence[str]:
        return tuple(
            k
            for k in self.certificate_types
            + self.person_names
            + self.project_keywords
            + self.honor_types
            + self.custom
        )


# ---------- 文件读写 ----------


def load_keywords(path: Path) -> KeywordsDict:
    """加载词典文件；文件不存在则返回空词典。"""
    if not path.is_file():
        return KeywordsDict()
    data = path.read_text(encoding="utf-8")
    return KeywordsDict.from_json(data)


def save_keywords(path: Path, kw: KeywordsDict) -> None:
    """原子写入词典文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(kw.to_json(), encoding="utf-8")
    tmp.replace(path)
