from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RoutingDecision(BaseModel):
    """Allowlisted routing advice; identities and permissions are supplied by the server."""
    model_config = ConfigDict(extra="forbid")
    route: Literal["business", "knowledge", "hybrid", "clarify", "human", "chitchat"]
    intent: Literal["order_query", "shipping_query", "refund_query", "product_query", "business_action",
                    "refund_eligibility", "knowledge", "clarify", "human", "chitchat"]
    order_id: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    product_sku: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    product_query: str | None = Field(default=None, max_length=128)
    product_field: Literal["price", "inventory", "info"] = "info"
    action: Literal["cancel_order", "apply_refund"] | None = None
    question: str | None = Field(default=None, max_length=200)
    knowledge_query: str | None = Field(default=None, max_length=500)

    @field_validator("product_field", mode="before")
    @classmethod
    def default_missing_product_field(cls, value):
        # Some routing models emit an explicit null for an irrelevant field.
        return "info" if value is None else value

    @model_validator(mode="after")
    def consistent_route(self):
        allowed = {
            "business": {"order_query", "shipping_query", "refund_query", "product_query", "business_action", "refund_eligibility"},
            "knowledge": {"knowledge"}, "hybrid": {"refund_eligibility", "order_query", "shipping_query", "product_query"},
            "clarify": {"clarify"}, "human": {"human"}, "chitchat": {"chitchat"},
        }
        if self.intent not in allowed[self.route]:
            raise ValueError("Route and intent disagree")
        if self.intent == "business_action" and not self.action:
            raise ValueError("Write advice needs an allowlisted action")
        if self.intent != "business_action" and self.action is not None:
            raise ValueError("Only explicit business actions may carry write advice")
        return self
