"""Concise factual replies. Values always come from the business adapter."""
from decimal import Decimal
from app.services.tracing import event, mark, active_trace


STATUS_LABELS = {"UNPAID": "待付款", "PAID": "已付款，待发货", "SHIPPED": "已发货",
    "DELIVERED": "已签收", "CANCELLED": "已取消", "REFUNDED": "已退款", "REFUNDING": "退款处理中",
    "PENDING": "待发货", "IN_TRANSIT": "运输中", "NONE": "暂无退款申请",
    "REQUESTED": "退款申请待审核", "APPROVED": "退款已批准", "REJECTED": "退款申请已拒绝",
    "RECEIVED": "退货已收到", "COMPLETED": "退款已完成", "SUCCESS": "成功"}
FIELD_LABELS = {"status": "状态", "tracking_number": "运单号", "carrier": "承运商",
    "estimated_delivery": "预计送达", "name": "商品", "price": "价格", "inventory": "可售库存",
    "refund_status": "退款状态", "updated_at": "更新时间", "amount": "订单金额",
    "quantity": "数量", "product_sku": "SKU", "payment_status": "支付状态"}


def safe_facts(data):
    return {k: v for k, v in data.items() if k in FIELD_LABELS and v is not None}


def facts_reply(data):
    return "；".join(f"{FIELD_LABELS[k]}：{STATUS_LABELS.get(str(v), v) if k.endswith('status') else v}"
                    for k, v in safe_facts(data).items())


def refund_reply(order_id: str, data: dict) -> str:
    status = data.get("refund_status")
    if status in ("COMPLETED", "REFUNDED"):
        detail = "退款已完成。"
    elif status == "REQUESTED":
        detail = "退款尚未完成，申请正在等待审核。"
    elif status == "APPROVED":
        detail = "退款尚未完成，申请已获批准。"
    elif status == "RECEIVED":
        detail = "退款尚未完成，退货已收到。"
    elif status == "REJECTED":
        detail = "退款申请已被拒绝，没有完成退款。"
    elif status == "NONE":
        detail = "目前没有退款申请，也没有完成退款。"
    else:
        detail = f"当前退款状态为 {status}，暂时无法确认是否已完成退款。"
    return f"订单 {order_id}：{detail}"


def product_reply(decision, context, call):
    sku = decision.product_sku
    if not sku:
        result = call("search_products", decision.product_query) if decision.product_query else None
        candidates = result.get("data", {}).get("products", []) if result else context["confirmed_products"]
        more = result.get("data", {}).get("has_more", False) if result else False
        if not candidates:
            mark(outcome='CLARIFY')
            event('local.product_resolve', '商品搜索无匹配', input=decision.model_dump(), output={'products': [], 'needs_clarification': True})
            return "暂未找到匹配的在售商品，请提供更准确的商品名称、型号或 SKU。", None
        if len(candidates) != 1 or more:
            mark(outcome='CLARIFY', used_context=not bool(decision.product_query))
            event('local.product_resolve', '商品存在多个候选，追问', input={'query': decision.product_query,
                  'candidates': candidates, 'from_context': result is None}, output={'needs_clarification': True})
            choices = "；".join(f"{p['name']}（{p['sku']}）" for p in candidates[:5])
            return f"找到多件商品：{choices}。请告诉我您想查询哪一件，或提供 SKU。", None
        sku = candidates[0]["sku"]
        event('local.product_resolve', '唯一商品匹配', input={'candidates': candidates}, output={'sku': sku})
    result = call("get_inventory" if decision.product_field == "inventory" else "get_product", sku)
    data = result.get("data", {})
    name = data.get("name") or sku
    if decision.product_field == "price" and data.get("price") is not None:
        text = f"{name}（{sku}）当前售价 ¥{Decimal(str(data['price'])):.2f}。"
    elif decision.product_field == "inventory" and data.get("inventory") is not None:
        text = f"{name}（{sku}）当前可售库存：{data['inventory']} 件。"
    else:
        text = f"{sku}：" + facts_reply(data)
    if data.get("status") == "OFF_SALE":
        text += "该商品已下架。"
    event('local.template', '商品回复模板', input={'field': decision.product_field, 'sku': sku, 'data': data},
        output={'content': text, 'bindings': {'name': 'business.data.name', 'price': 'business.data.price',
                                             'inventory': 'business.data.inventory'}},
        sources=[{'node_id': active_trace.get().last_business_node if active_trace.get() else None,
                  'fields': ['output.data.name', 'output.data.price', 'output.data.inventory']}])
    return text, safe_facts(data)
