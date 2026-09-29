"""素材库 schema（Task 15）。"""

from pydantic import BaseModel


class MaterialOut(BaseModel):
    """素材输出。"""

    id: str
    enterprise_id: str
    project_id: str | None
    category: str
    name: str
    filename: str
    file_path: str
    ocr_text: str | None
    valid_until: str | None
    version: int
    status: str
    created_at: str
    updated_at: str


class MaterialListOut(BaseModel):
    """素材列表。"""

    items: list[MaterialOut]
    total: int


class MaterialCreateIn(BaseModel):
    """创建/上传素材入参。"""

    name: str | None = None
    category: str
    filename: str | None = None
    valid_until: str | None = None
    # 命名字段（OCR 识别后填充）
    fields: dict[str, str] | None = None


class MaterialUpdateIn(BaseModel):
    """更新素材属性（重命名/修改有效期等）。"""

    name: str | None = None
    filename: str | None = None
    ocr_text: str | None = None
    valid_until: str | None = None


class MaterialDeleteOut(BaseModel):
    deleted: str
