from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Login(Input):
    account: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=128)
    model_config = ConfigDict(extra='forbid')  # Password whitespace is significant.


class Guest(Input):
    entry_code: str = Field(min_length=3, max_length=32, pattern=r'^[a-z0-9_-]+$')
    visitor_id: str = Field(min_length=8, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    visitor_proof: str | None = Field(default=None, min_length=32, max_length=128)


class Presence(Input):
    status: Literal['ONLINE', 'OFFLINE']


class StaffCreate(Input):
    username: str = Field(min_length=3, max_length=128, pattern=r'^[A-Za-z0-9_@.\-]+$')
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=128)
    model_config = ConfigDict(extra='forbid')


class StaffUpdate(Input):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    active: bool | None = None


class Send(Input):
    client_message_id: str = Field(min_length=8, max_length=64, pattern=r'^[A-Za-z0-9_\-]+$')
    content: str = Field(min_length=1, max_length=10000)

    @field_validator('content')
    @classmethod
    def meaningful(cls, value):
        if not value.strip():
            raise ValueError('消息不能为空')
        return value.strip()


class Transition(Input):
    expected_epoch: int = Field(ge=1, strict=True)


class Reopen(Transition):
    request_id: str = Field(min_length=8, max_length=64, pattern=r'^[A-Za-z0-9_\-]+$')


class End(Transition):
    conversation_id: int = Field(gt=0, strict=True)
