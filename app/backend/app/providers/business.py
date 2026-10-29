import time
from urllib.parse import urljoin
import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.config.settings import settings
from app.services.tracing import step, safe_url
from app.services.mock_commerce import MockBusinessError, run_mock_tool
from app.providers.ai import ProviderError


READ_TOOLS = {"search_products": "products", "list_orders": "orders", "get_order": "orders/{order_id}", "get_shipping": "orders/{order_id}/shipping",
              "get_refund_status": "orders/{order_id}/refund", "get_product": "products/{order_id}",
              "get_inventory": "products/{order_id}/inventory", "get_refund_eligibility": "orders/{order_id}/refund-eligibility"}


WRITE_TOOLS = {"cancel_order": "orders/{order_id}/cancel", "apply_refund": "orders/{order_id}/refund"}


def business_tool(db: Session, trace_id: str, conversation_id: int, user_id: int,
                  name: str, order_id: str, idempotency_key: str | None = None) -> dict:
    if name not in READ_TOOLS and name not in WRITE_TOOLS:
        raise HTTPException(400, "Unknown tool")
    if name == "search_products" and (not order_id.strip() or len(order_id) > 128):
        raise HTTPException(400, "Invalid product query")
    if name not in ("list_orders", "search_products") and (not order_id or len(order_id) > 128 or not all(c.isalnum() or c in "-_" for c in order_id)):
        raise HTTPException(400, "Invalid identifier")
    s = settings()
    if s.business_mode == "http" and not s.business_api_url:
        raise ProviderError("Business API not configured")
    node_context = step('business.tool', name, 'mysql' if s.business_mode == 'mock' else 'http_api',
        input={'tool': name, 'identifier': order_id, 'user_id': user_id, 'conversation_id': conversation_id,
               'idempotency_key': idempotency_key, 'mode': s.business_mode},
        sources=[{'field': 'user_id', 'origin': 'authenticated_user'},
                 {'field': 'identifier', 'origin': 'validated_route_or_pending_action'}])
    node = node_context.__enter__()
    result = {}
    error = None
    try:
        if s.business_mode == "mock":
            from app.models import Conversation
            conversation = db.get(Conversation, conversation_id)
            if not conversation or conversation.user_id != user_id:
                raise ProviderError("Conversation unavailable")
            result = run_mock_tool(db, user_id, name, order_id, idempotency_key,
                                   tenant_id=conversation.tenant_id, account_id=conversation.account_id)
            node.output({'adapter': 'run_mock_tool', 'resource_tables': ['eshop_product'] if name in ('search_products', 'get_product', 'get_inventory')
                else ['eshop_order'],
                'parameters': {'identifier': order_id, 'user_id': user_id,
                               'tenant_id': conversation.tenant_id, 'account_id': conversation.account_id},
                'ownership': 'active C user and matching conversation; orders filtered by user_id'}, 'request')
        elif s.business_mode == "http":
            from app.models import Conversation
            conversation = db.get(Conversation, conversation_id)
            if not conversation or conversation.user_id != user_id:
                raise ProviderError('Conversation unavailable')
            path = (READ_TOOLS | WRITE_TOOLS)[name].format(order_id=order_id)
            headers = {"Authorization": f"Bearer {s.business_api_token}", "X-User-Id": str(user_id),
                       "X-Account-Id": str(conversation.account_id),
                       "X-Trace-Id": trace_id}
            if name in WRITE_TOOLS:
                if not idempotency_key:
                    raise HTTPException(400, "Idempotency key required")
                headers["Idempotency-Key"] = idempotency_key
            with httpx.Client(timeout=httpx.Timeout(8, connect=2)) as client:
                node.output({'method': 'POST' if name in WRITE_TOOLS else 'GET',
                    'url': safe_url(urljoin(s.business_api_url.rstrip('/') + '/', path)),
                    'headers': headers, 'body': {} if name in WRITE_TOOLS else None,
                    'params': {'q': order_id} if name == 'search_products' else {}}, 'request')
                response = client.post(urljoin(s.business_api_url.rstrip("/") + "/", path), headers=headers, json={}) if name in WRITE_TOOLS else client.get(urljoin(s.business_api_url.rstrip("/") + "/", path), headers=headers, params={"q": order_id} if name == "search_products" else None)
                node.output({'status_code': response.status_code, 'body': response.text}, 'raw_response')
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict):
                    raise ValueError("Invalid business response")
        else:
            raise ProviderError("Unknown business mode")
        if result.get("success") is not True:
            raise ProviderError(result.get("code", "Business API rejected request"))
        node.output(result)
        return result
    except MockBusinessError as exc:
        error = exc
        raise ProviderError(str(exc), code=str(exc)) from exc
    except (httpx.HTTPError, ValueError) as exc:
        error = exc
        raise ProviderError("Business API unavailable") from exc
    except Exception as exc:
        error = exc
        raise
    finally:
        products = (result.get("data", {}).get("products", []) if name == "search_products" else [])
        context_products = [{k: row[k] for k in ("sku", "name") if k in row} for row in products[:5] if isinstance(row, dict)]
        if name in ("get_product", "get_inventory") and result.get("success"):
            context_products = [{"sku": order_id, "name": result.get("data", {}).get("name", "")}]
        node.summary = {'tool': name, 'products': context_products, 'code': result.get('code'),
                        'request_id': result.get('request_id')}
        node_context.__exit__(type(error) if error else None, error, None)
        db.commit()
