import re
import json
from sqlalchemy import select
from app.config.settings import settings
from app.models import Message, QuestionTrace, QuestionTraceNode, Conversation
from app.services.tracing import event, step, mark
from app.providers.ai import ProviderError
from app.providers.routing import classify
from app.schemas.routing import RoutingDecision

AMBIGUOUS_ORDER_WORDS = ("有个订单", "一个订单", "某个订单", "这两个订单", "两笔订单", "多个订单", "几个订单")
LATEST_ORDER_CUES = ("刚下单", "刚刚下单", "刚才下单", "刚买", "刚刚买", "最近下单", "最新订单", "最近订单")


def latest_order_query(text: str) -> bool:
    """Whether the customer clearly refers to their newest order."""
    t = text.lower()
    return any(cue in t for cue in LATEST_ORDER_CUES)


def merchant_address_query(text: str) -> bool:
    """Route generic store/return-address questions to published knowledge."""
    t = text.lower()
    if not any(word in t for word in ("收货地址", "收件地址", "退货地址", "寄回地址", "寄件地址", "地址")):
        return False
    # Personal/order-specific delivery details are a separate business question.
    if any(word in t for word in ("我的订单", "订单地址", "订单收货", "订单上的", "我填写的", "我填的", "我下单时")):
        return False
    if any(word in t for word in ("我的收货地址", "我的收件地址", "我的地址")):
        return False
    return True


def order_ids_from(text: str) -> list[str]:
    ids = list(dict.fromkeys(value.upper() for value in re.findall(
        r'(?<![A-Za-z0-9_-])(?:ESH|DEMO|PDD)-[A-Za-z0-9_-]{3,64}(?![A-Za-z0-9_-])', text, re.I)))
    if ids:
        return ids
    match = re.search(r"(?:订单[号#：:\s]*|order[\s#:]*)([A-Za-z0-9_-]{3,64})", text, re.I)
    return [match.group(1)] if match else []


def order_id_from(text: str) -> str | None:
    ids = order_ids_from(text)
    return ids[0] if len(ids) == 1 else None


def product_id_from(text: str) -> str | None:
    match = re.search(r"(?:商品(?:编号|号|ID)?|SKU)[#：:\s]*([A-Za-z0-9_-]{3,64})", text, re.I)
    if match:
        # Preserve the SKU- prefix for ordinary catalog SKUs.
        full = re.search(r"(?<![A-Za-z0-9_-])SKU-[A-Za-z0-9_-]+", text, re.I)
        return full.group(0) if full else match.group(1)
    return None


def requested_action(text: str) -> str | None:
    if re.search(r"不要|别(?:帮我)?|不想|不需要|是否|能否|能不能|吗|如何|怎么|假如|如果|想了解|政策|规则|条件", text):
        return None
    if any(word in text for word in ("取消", "退掉订单")):
        return "cancel_order"
    if any(word in text for word in ("申请退款", "申请退货", "办理退款", "办理退货",
                                     "帮我办理退款", "帮我办理退货", "帮我退货", "帮我退款", "给我退款",
                                     "我要退款", "我要退货", "想退款", "想退货", "把钱退")):
        return "apply_refund"
    return None


def action_is_authorized(text: str, history: list[dict], action: str | None) -> bool:
    """Independently validate a write action, including a clear contextual confirmation."""
    if requested_action(text) == action and action is not None:
        return True
    if action != "apply_refund":
        return False
    t = text.strip()
    if any(word in t for word in ("不想", "不要", "别", "吗", "能否", "能不能", "是否", "如果", "假如")):
        return False
    confirmation = any(phrase in t for phrase in (
        "好的，我现在申请", "好，我现在申请", "我现在申请", "现在申请", "那我申请", "好的，申请", "好，申请",
    ))
    if not confirmation:
        return False
    previous_assistant = next((str(item.get("content", "")) for item in reversed(history)
                               if item.get("role") == "assistant"), "")
    offered_refund = any(phrase in previous_assistant for phrase in (
        "提交退款申请", "申请退款", "提交退货申请", "申请退货", "办理退款",
    ))
    return offered_refund


def purchase_query_from(text: str) -> str | None:
    """Recognize a direct request to buy a named product, without selecting an old SKU."""
    value = text.strip().lower()
    match = re.match(r"^(?:我)?(?:想要|想|要|打算|准备)?买", value)
    if not match:
        return None
    rest = value[match.end():].strip()
    if rest.startswith(("的", "过", "了")):
        return None
    rest = re.sub(r"^(?:一个|一件|一台|一部|一些|个|件|台|部|点)", "", rest)
    rest = re.split(r"[，,。！？?!]|多少钱|价格|有货|库存", rest, maxsplit=1)[0].strip()
    return rest[:128]


def local_decision(text: str) -> RoutingDecision:
    """Deterministic mock mode and provider failure fallback; no dynamic prices in RAG."""
    t = text.lower().strip()
    oid, sku, action = order_id_from(text), product_id_from(text), requested_action(text)
    if t in ("人工", "真人", "转人工", "转人工客服", "找人工客服", "客服接管") or t.startswith("请转人工"):
        return RoutingDecision(route="human", intent="human")
    if t in ("你好", "您好", "谢谢", "hi", "hello"):
        return RoutingDecision(route="chitchat", intent="chitchat")
    if merchant_address_query(text):
        return RoutingDecision(route="knowledge", intent="knowledge", knowledge_query=text)
    if action:
        return RoutingDecision(route="business", intent="business_action", order_id=oid, action=action)
    if (oid or any(w in t for w in ("这笔", "这个订单", "我的订单"))) and any(w in t for w in ("能退", "可以退", "还能退", "能不能退", "可退", "退货政策", "退货条件")):
        return RoutingDecision(route="hybrid", intent="refund_eligibility", order_id=oid, knowledge_query="退货政策")
    if any(w in t for w in ("政策", "规则", "教程", "使用说明", "保修", "退货条件")) and not oid:
        return RoutingDecision(route="knowledge", intent="knowledge")
    if any(w in t for w in ("物流", "快递", "运单", "发货", "到哪", "什么时候到")):
        return RoutingDecision(route="business", intent="shipping_query", order_id=oid)
    if "退款" in t and any(w in t for w in ("状态", "进度", "到账", "为什么", "多久",
                                           "处理", "完成", "成功", "了吗", "了没", "没有")):
        return RoutingDecision(route="business", intent="refund_query", order_id=oid)
    payment_question = any(w in t for w in ("付款", "支付", "付钱", "扣款")) and any(
        w in t for w in ("状态", "是否", "了吗", "了没", "没有", "成功", "到账", "收到"))
    if payment_question and (any(w in t for w in ("订单", "下单", "购买", "买了", "买的"))
                             or latest_order_query(text)):
        return RoutingDecision(route="business", intent="order_query", order_id=oid)
    purchase = purchase_query_from(text)
    if purchase is not None:
        if not purchase:
            return RoutingDecision(route="clarify", intent="clarify", question="您想买哪件商品？请提供商品名称或型号。")
        field = "inventory" if any(w in t for w in ("库存", "有货")) else "price" if any(w in t for w in ("多少钱", "价格", "售价")) else "info"
        return RoutingDecision(route="business", intent="product_query", product_sku=sku,
                               product_query=None if sku else purchase, product_field=field)
    if any(w in t for w in ("多少钱", "价格", "售价", "价钱", "库存", "有货", "还有货", "商品信息", "查询商品", "查看商品")) or sku:
        field = "inventory" if any(w in t for w in ("库存", "有货", "还有货")) else "price" if any(w in t for w in ("多少钱", "价格", "售价", "价钱")) else "info"
        name = re.sub(r"[？?！!，,。\s]", "", text)
        name = re.sub(r"^(请问|你们的?|这个|这款|那个|那款|帮我查一下|查一下)", "", name)
        name = re.sub(r"(大概)?(多少钱|价格|售价|价钱|库存|还有货|有货|商品信息|查询商品|查看商品)(是多少|多少|怎么|吗|呢)?$", "", name).strip("的")
        if name in ("", "它", "这个", "这款", "那个", "那款", "多少") or sku:
            name = None
        return RoutingDecision(route="business", intent="product_query", product_sku=sku, product_query=name, product_field=field)
    if "订单" in t or "购买记录" in t or order_ids_from(text) or t in ("这个", "这笔", "那个"):
        return RoutingDecision(route="business", intent="order_query", order_id=oid)
    return RoutingDecision(route="knowledge", intent="knowledge")


def intent_for(text: str) -> str:
    return local_decision(text).intent


def _entity_state(db, conversation, current_message_id):
    """Extract durable identifiers without sending old conversation text to the model."""
    state = {"active_order_id": None, "order_message_id": None,
             "active_product_sku": None, "product_message_id": None,
             "pending_order_clarification": False, "last_processed_message_id": 0}
    # The preceding question trace is a compact checkpoint. If trace capture failed,
    # replay this conversation's customer messages to reconstruct the same state.
    snapshots = db.scalars(select(QuestionTrace.context_sources).where(
        QuestionTrace.conversation_id == conversation.id, QuestionTrace.kind == 'question')
        .order_by(QuestionTrace.id.desc()).limit(5)).all()
    for snapshot in snapshots:
        saved = (snapshot or {}).get('entity_state')
        if isinstance(saved, dict) and isinstance(saved.get('last_processed_message_id'), int):
            state.update({key: saved[key] for key in state if key in saved})
            break
    rows = db.execute(select(Message.id, Message.content).where(
        Message.conversation_id == conversation.id, Message.sender_type == "CUSTOMER",
        Message.id > state['last_processed_message_id'], Message.id < current_message_id)
        .order_by(Message.id).execution_options(yield_per=100))
    for message_id, content in rows:
        state['last_processed_message_id'] = message_id
        order_ids = order_ids_from(content)
        if len(order_ids) == 1:
            state.update(active_order_id=order_ids[0], order_message_id=message_id,
                         pending_order_clarification=False)
        elif len(order_ids) > 1 or any(word in content for word in AMBIGUOUS_ORDER_WORDS):
            state.update(active_order_id=None, order_message_id=None,
                         pending_order_clarification=True)
        sku = product_id_from(content)
        if sku:
            state.update(active_product_sku=sku, product_message_id=message_id)
    return state


def context_for(db, conversation, text):
    # Read only this conversation; route_question checks its owner first.
    rows = db.scalars(select(Message).where(Message.conversation_id == conversation.id,
        Message.sender_type.in_(["CUSTOMER", "AI"])).order_by(Message.id.desc())
        .limit(max(1, min(settings().routing_history_messages, 6)) + 1)).all()
    if rows and rows[0].sender_type == "CUSTOMER" and rows[0].content.strip() == text.strip():
        rows = rows[1:]
    current_message_id = db.scalar(select(Message.id).where(Message.conversation_id == conversation.id,
        Message.sender_type == "CUSTOMER").order_by(Message.id.desc()).limit(1)) or 2**63
    state = _entity_state(db, conversation, current_message_id)
    tools = db.scalars(select(QuestionTraceNode).where(QuestionTraceNode.conversation_id == conversation.id,
        QuestionTraceNode.status == "SUCCESS", QuestionTraceNode.node_type == 'business.tool',
        QuestionTraceNode.name.in_(["search_products", "get_product", "get_inventory"]))
        .order_by(QuestionTraceNode.id.desc()).limit(1)).all()
    products = [{"sku": str(p.get("sku", ""))[:128], "name": str(p.get("name", ""))[:80]}
                for p in (tools[0].summary or {}).get("products", [])[:5]
                if isinstance(p, dict) and p.get("sku")] if tools else []
    if not products and state["active_product_sku"]:
        products = [{"sku": state["active_product_sku"]}]
    budget = max(400, min(getattr(settings(), "routing_context_characters", 1600), 4000))
    context = {"question": text, "history": [], "entity_state": state,
               "confirmed_products": products}
    sources = {'history': [], 'entity_state': state, 'products_node_id': tools[0].id if tools else None,
               'confirmed_products': products,
               'limits': {'history_messages': min(settings().routing_history_messages, 6),
                          'context_characters': budget, 'message_characters': 300}}
    # Keep recent relevant turns only; the current question is passed separately and never truncated.
    domain_terms = ("订单", "商品", "sku", "快递", "发货", "退款", "退货", "价格", "库存",
                    "售后", "运单", "收货", "发错", "物流", "这个", "这笔", "那个")
    for position, row in enumerate(rows):
        if row.content.strip().lower() in ("你好", "您好", "谢谢", "hi", "hello"):
            continue
        if position >= 2 and not any(term in row.content.lower() for term in domain_terms):
            continue
        item = {"role": "customer" if row.sender_type == "CUSTOMER" else "assistant",
                "content": row.content[:300]}
        candidate = [item] + context["history"]
        if len(json.dumps({**context, "question": "", "history": candidate}, ensure_ascii=False)) > budget:
            break
        context["history"] = candidate
        sources['history'].insert(0, {'message_id': row.id, 'role': row.sender_type,
            'original_length': len(row.content), 'included_length': len(item['content']),
            'truncated': len(row.content) > 300, 'content': item['content']})
    event('local.context', '组装当前会话上下文', input={'conversation_id': conversation.id, 'question': text},
          output={**context, 'provenance': sources}, location='mysql')
    mark(context_sources=sources)
    return context


def route_question(db, conversation, customer, text, model, prompt_config=None):
    live = db.get(Conversation, conversation.id)
    if not live or live.user_id != customer.id:
        raise ProviderError("Conversation unavailable")
    fallback = local_decision(text)
    context = context_for(db, conversation, text)
    strong = (fallback.intent in ("human", "chitchat") or bool(order_id_from(text) or product_id_from(text))
              or purchase_query_from(text) is not None or merchant_address_query(text))
    if strong and fallback.intent not in ("human", "chitchat", "business_action", "refund_eligibility"):
        # Mixed entity/policy questions still benefit from semantic classification.
        strong = not any(w in text for w in ("政策", "规则", "保修", "以及", "同时"))
    source = "rule"
    decision = fallback
    event('local.rule', '本地规则判断', input={'question': text},
          output={'decision': fallback.model_dump(), 'strong_match': strong})
    if not strong and settings().semantic_routing_enabled and settings().llm_mode != "mock":
        mark(used_context=bool(context['history'] or context['confirmed_products'] or context['entity_state']['active_order_id']))
        try:
            with step('local.route_parse', '语义分类与解析', input=context) as node:
                decision = classify(context, model, instruction=(prompt_config or {}).get("routing_instruction"))
                node.output(decision.model_dump())
            mark(used_context=bool(context['history'] or context['confirmed_products'] or context['entity_state']['active_order_id']))
            source = "llm"
        except ProviderError as exc:
            source = "fallback:" + exc.code
            mark(fallback=True)
            event('local.fallback', '分类失败后使用规则', input={'code': exc.code}, output=fallback.model_dump())
    elif not strong:
        source = "mock" if settings().llm_mode == "mock" else "rule"
    proposed = decision.model_dump()
    # Current explicit identifiers win. Prior customer identifiers are routing hints only;
    # business tools still verify ownership and fetch live facts on every read or write.
    state = context["entity_state"]
    if len(order_ids_from(text)) > 1:
        decision.order_id = None
    elif order_id_from(text):
        decision.order_id = order_id_from(text)
    elif any(word in text for word in ("这个", "这笔", "那个", "我的订单", *AMBIGUOUS_ORDER_WORDS)):
        # A demonstrative does not identify one of several orders mentioned in history.
        decision.order_id = (state["active_order_id"] if not state["pending_order_clarification"]
                             and not any(word in text for word in (*AMBIGUOUS_ORDER_WORDS, "我的订单"))
                             else None)
    elif decision.order_id and decision.order_id != state["active_order_id"]:
        decision.order_id = None
    elif not decision.order_id and decision.intent in ("order_query", "shipping_query", "refund_query", "refund_eligibility", "business_action"):
        decision.order_id = state["active_order_id"] if not state["pending_order_clarification"] else None
    if fallback.intent == "order_query" and text.strip() in ("这个", "这笔", "那个"):
        decision = RoutingDecision(route="business", intent="order_query", order_id=decision.order_id)
    if product_id_from(text):
        decision.product_sku = product_id_from(text)
    elif decision.product_sku:
        known = {row.get("sku") for row in context["confirmed_products"]}
        if decision.product_sku not in text and decision.product_sku not in known:
            decision.product_sku = None
    # Dynamic-fact questions must not fall into knowledge even if the model misroutes.
    if fallback.intent == "product_query" and decision.route in ("knowledge", "chitchat"):
        decision = fallback
        source += ":dynamic_fact_guard"
    if fallback.intent in ("order_query", "shipping_query", "refund_query") and decision.route in ("knowledge", "chitchat"):
        decision = fallback
        source += ":dynamic_fact_guard"
    if decision.intent == "business_action":
        if not action_is_authorized(text, context["history"], decision.action):
            decision = RoutingDecision(route="clarify", intent="clarify", question="您是想了解售后规则，还是需要办理取消订单或申请退款？")
    if len(order_ids_from(text)) > 1:
        decision = RoutingDecision(route="clarify", intent="clarify",
                                   question="您提到了多笔订单，请回复要查询或处理的一个订单号。")
    if decision.intent == "product_query" and not decision.product_sku and not decision.product_query:
        products = context["confirmed_products"]
        if len(products) == 1:
            decision.product_sku = products[0]["sku"]
            mark(used_context=True)
        elif not products:
            decision = RoutingDecision(route="clarify", intent="clarify", question="您想了解哪件商品？请提供商品名称、型号或 SKU。")
    event('local.route_validate', '后端校验与最终路由', input={'proposed': proposed, 'question': text,
          'confirmed_products': context['confirmed_products'], 'history': context['history'],
          'entity_state': state},
          output={'decision': decision.model_dump(), 'source': source, 'changed': proposed != decision.model_dump(),
                  'corrections': [{'field': k, 'before': proposed.get(k), 'after': value} for k, value in decision.model_dump().items()
                                  if proposed.get(k) != value],
                  'checks': ['当前标识优先', 'SKU来源校验', '订单归属由工具核验', '动态事实保护', '写操作需明确请求', '商品上下文消歧', '压缩实体状态消歧']},
          sources=[{'field': 'product_sku', 'origin': 'current_question_or_confirmed_products'},
                   {'field': 'order_id', 'origin': 'current_question_or_entity_state; ownership checked by business'}])
    mark(route=decision.route, intent=decision.intent)
    return decision, source, context
