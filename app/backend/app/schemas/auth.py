from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str | None = None
    account: str | None = Field(default=None,max_length=255)
    password: str = Field(min_length=1,max_length=128)


class CustomerTokenRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    display_name: str = Field(default="", max_length=128)


class GuestRequest(BaseModel):
    visitor_id: str = Field(pattern=r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$')
    visitor_proof: str | None = Field(default=None,min_length=32,max_length=128)
    fingerprint: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')
