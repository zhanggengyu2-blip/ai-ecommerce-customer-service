from pydantic import BaseModel, Field


class StaffCreateRequest(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=128)
    username: str | None = Field(default=None, min_length=1, max_length=128)
    display_name: str = Field(default="", max_length=128)
    user_type: str = "B"
    password: str = Field(min_length=12, max_length=128)
    role: str


class StaffUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    active: bool | None = None
    role: str | None = None
    password: str | None = Field(default=None,min_length=12,max_length=128)
