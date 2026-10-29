from datetime import datetime
from pydantic import BaseModel, Field


class FAQRequest(BaseModel):
    document_id: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1, max_length=255)
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=10000)
    account_id: int | None = Field(default=None, ge=1)
    platform_code: str | None = None


class ChunkSuggestion(BaseModel):
    strategy: str = 'semantic'
    target_chars: int = Field(default=800, ge=200, le=4000)
    overlap_chars: int = Field(default=100, ge=0, le=1000)


class ChunkEdit(BaseModel):
    section: str = Field(default='', max_length=255)
    content: str = Field(min_length=1, max_length=8000)
    tags: dict[str, str] = Field(default_factory=dict)


class ChunkSave(BaseModel):
    chunks: list[ChunkEdit] = Field(min_length=1, max_length=200)


class PublicationRequest(BaseModel):
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    auto_revert_on_expiry: bool = False
    allow_lexical_only: bool = False
