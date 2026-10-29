"""Import all models so migrations see the complete metadata."""
from .base import Base, utcnow
from .user import Tenant, User
from .channel import ChannelAccount, StaffAccountAccess, ExternalCustomerIdentity
from .conversation import ChatThread, Conversation, Message, PendingAction, Feedback, ReceptionRequest
from .knowledge import Document, DocumentVersion, Chunk, KnowledgeCategory
from .generation import AiGeneration, KnowledgeJob
from .trace import QuestionTrace, QuestionTraceNode, QuestionTracePayload
from .system import AuditLog, ConfigVersion, PromptTemplate
from .eshop import EshopCustomer, EshopProduct, EshopOrder, EshopOrderItem, EshopPayment, EshopShipment, EshopRefund, EshopInventoryLog, EshopOperation
