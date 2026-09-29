"""企业/项目 Pydantic schemas。

委托代理人优先级（TR-5.2）：
- 企业 agent 必填（min_length=1）；
- 项目 agent 选填，API 层返回时缺省回退企业 agent。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ========== 企业 ==========


class EnterpriseBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    legal_person: str | None = Field(default=None, max_length=100)
    agent: str = Field(..., min_length=1, max_length=100)  # 必填
    contact: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=50)
    intro: str | None = None


class EnterpriseCreate(EnterpriseBase):
    pass


class EnterpriseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    legal_person: str | None = Field(default=None, max_length=100)
    agent: str | None = Field(default=None, min_length=1, max_length=100)
    contact: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=50)
    intro: str | None = None


class EnterpriseOut(EnterpriseBase):
    id: str
    status: str
    model_config = ConfigDict(from_attributes=True)


# ========== 项目 ==========


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=100)
    agent: str | None = Field(default=None, max_length=100)  # 选填


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=100)
    agent: str | None = Field(default=None, max_length=100)


class ProjectOut(BaseModel):
    """agent 为回退后的值（项目优先，缺省取企业）。"""

    id: str
    enterprise_id: str
    name: str
    code: str | None
    agent: str
    status: str
    parse_status: str = "INIT"
    model_config = ConfigDict(from_attributes=True)


# ========== 回收站 ==========


class RecycleBinItemOut(BaseModel):
    id: str
    item_type: str
    enterprise_id: str | None
    ref_id: str
    name: str | None = None
    status: str
    file_path: str | None = None
    deleted_at: datetime
    purge_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SystemRecycleBinItemOut(RecycleBinItemOut):
    """系统回收站条目（被删除的企业，跨企业可见）。"""

    pass
