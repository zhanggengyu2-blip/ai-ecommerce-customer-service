from datetime import datetime
from typing import Literal
from pydantic import Field, SecretStr, ConfigDict, field_validator, model_validator
from .schemas import Input


class ModelRole(Input):
    provider: Literal['deepseek','dashscope']
    model_id: str = Field(min_length=1,max_length=100)
    api_key: SecretStr | None = None
    dimension: int | None = Field(default=None,strict=True)

    @field_validator('api_key')
    @classmethod
    def key_input(cls,value):
        if value is None:return value
        key=value.get_secret_value().strip()
        if key and (len(key)<16 or len(key)>512 or any(c.isspace() for c in key) or '•' in key or '*' in key):
            raise ValueError('请填写有效 API Key，或留空保留原 Key')
        return SecretStr(key)


class ModelsSave(Input):
    expected_version: int = Field(ge=0,strict=True)
    dialogue: ModelRole
    embedding: ModelRole
    rerank: ModelRole


class ModelCheck(Input):
    role: Literal['dialogue','embedding','rerank']
    config: ModelRole


class RetrievalSave(Input):
    expected_version: int = Field(ge=0,strict=True)
    final_top_k: int = Field(ge=1,le=10,strict=True)
    min_score: float = Field(ge=0,le=1,allow_inf_nan=False,strict=True)

    @field_validator('min_score',mode='before')
    @classmethod
    def real_score(cls,value):
        if isinstance(value,bool) or not isinstance(value,(int,float)):raise ValueError('Score 必须为 0–1 的数值')
        return value


class EnableReception(Input):
    enabled: bool = Field(strict=True)
    expected_version: int = Field(ge=0,strict=True)


class CategoryInput(Input):
    name: str = Field(min_length=1,max_length=100)
    description: str = Field(default='',max_length=2000)


class CategoryEdit(CategoryInput):
    expected_revision: int = Field(ge=1,strict=True)


class ChunkSettings(Input):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=False)
    separator: str = Field(default='\n\n',min_length=1,max_length=20)
    target_chars: int = Field(default=500,ge=100,le=4000,strict=True)
    overlap_chars: int = Field(default=50,ge=0,strict=True)

    @model_validator(mode='after')
    def overlap(self):
        if self.overlap_chars>=self.target_chars:raise ValueError('重叠长度必须小于分段长度')
        return self


class PreviewInput(Input):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=False)
    content: str = Field(min_length=1,max_length=2*1024*1024)
    settings: ChunkSettings = Field(default_factory=ChunkSettings)

    @field_validator('content')
    @classmethod
    def text_file(cls,value):
        if not value.strip() or '\0' in value or len(value.encode())>2*1024*1024:raise ValueError('正文应为 2 MB 以内的有效纯文本')
        return value


class PublishInput(PreviewInput):
    document_id: int | None = Field(default=None,gt=0,strict=True)
    expected_revision: int = Field(default=0,ge=0,strict=True)
    category_id: int = Field(gt=0,strict=True)
    title: str = Field(min_length=1,max_length=255)
    purpose: str | None = Field(default=None,max_length=1000)
    effective_from: datetime | None = None
    effective_until: datetime | None = None

    @field_validator('title')
    @classmethod
    def nonempty_title(cls,value):
        if not value.strip():raise ValueError('标题不能为空')
        return value.strip()

    @model_validator(mode='after')
    def dates(self):
        for value in (self.effective_from,self.effective_until):
            if value and value.tzinfo is None:raise ValueError('有效时间必须包含时区')
        if self.effective_from and self.effective_until and self.effective_until<=self.effective_from:
            raise ValueError('失效时间必须晚于生效时间')
        return self


class DocumentToggle(Input):
    expected_revision: int = Field(ge=1,strict=True)
    enabled: bool = Field(strict=True)


class Restore(Input):
    expected_revision: int = Field(ge=1,strict=True)


class Recall(Input):
    query: str = Field(min_length=1,max_length=2000)
    category_id: int | None = Field(default=None,gt=0,strict=True)


class RouteOutput(Input):
    action: Literal['KNOWLEDGE','CLARIFY','HANDOFF','OUT_OF_SCOPE']
    query: str = Field(min_length=1,max_length=2000)
    document_ids: list[int] = Field(default_factory=list,max_length=100)


class AnswerOutput(Input):
    supported: bool = Field(strict=True)
    answer: str = Field(min_length=1,max_length=3000)
    source_ids: list[int] = Field(default_factory=list,max_length=10)
