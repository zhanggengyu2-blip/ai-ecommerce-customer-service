from fastapi import APIRouter
from app.api.v1 import eshop
from app.api.v1 import identity
from app.api.v1 import health
from app.api.v1 import auth
from app.api.v1 import customer
from app.api.v1 import support
from app.api.v1 import knowledge
from app.api.v1 import integrations
from app.api.v1 import analytics
from app.api.v1 import users
from app.api.v1 import configuration
from app.api.v1 import websocket
from app.api.v1 import traces
from app.api.v1 import accounts

router = APIRouter()
router.include_router(eshop.router)
router.include_router(identity.router)
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(customer.router)
router.include_router(support.router)
router.include_router(knowledge.router)
router.include_router(integrations.router)
router.include_router(analytics.router)
router.include_router(users.router)
router.include_router(configuration.router)
router.include_router(websocket.router)
router.include_router(traces.router)
router.include_router(accounts.router)
