from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    account_id: int = Field(default=1, ge=1)


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class FeedbackRequest(BaseModel):
    rating: int = Field(ge=-1, le=1)
    reason: str = Field(default="", max_length=32)


class ConfirmRequest(BaseModel):
    confirm: bool
