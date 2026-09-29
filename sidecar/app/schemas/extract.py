"""素材提取清单 Schemas（Task 16）。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ExtractListItem(BaseModel):
    id: str
    requirement_name: str
    source: str
    source_anchor: str | None = None
    selected_material_id: str | None = None
    status: str
    confirmed_at: datetime | None = None
    round: int = 1

    @classmethod
    def from_model(cls, m) -> "ExtractListItem":
        return cls(
            id=m.id,
            requirement_name=m.requirement_name,
            source=m.source,
            source_anchor=m.source_anchor,
            selected_material_id=m.selected_material_id,
            status=m.status,
            confirmed_at=m.confirmed_at,
            round=m.round,
        )


class ExtractListOut(BaseModel):
    items: list[ExtractListItem]
    total: int
    pending: int = 0
    selected: int = 0
    missing: int = 0


class CandidateGroup(BaseModel):
    """证件组：多页素材按去掉 _P0/_P1 后前缀聚合。"""

    group_key: str
    items: list[dict[str, Any]]


class ExtractQueryIn(BaseModel):
    requirement_name: str | None = None
    keyword: str | None = None


class ExtractQueryOut(BaseModel):
    candidates: list[CandidateGroup]
    total: int


class GenerateOut(BaseModel):
    requirement_count: int
    round: int
    items: list[ExtractListItem]


class SaveRoundChange(BaseModel):
    item_id: str
    status: str | None = None
    selected_material_id: str | None = None


class SaveRoundIn(BaseModel):
    round: int
    changes: list[SaveRoundChange]


class ImportExternalIn(BaseModel):
    file_path: str
    category: str
    name: str | None = None
    filename: str | None = None


class AddRequirementIn(BaseModel):
    requirement_name: str
    source: str | None = None
    source_anchor: str | None = None
    round: int | None = None


class UpdateRequirementIn(BaseModel):
    requirement_name: str


class ConfirmExtractOut(BaseModel):
    confirmed_at: str
    round: int
    item_count: int
