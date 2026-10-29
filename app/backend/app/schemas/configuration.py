from pydantic import BaseModel, Field


class ConfigRequest(BaseModel):
    kind: str
    value: dict
