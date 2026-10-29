import time
import uuid
from typing import Callable
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config.settings import settings
from app.models import AuditLog, Conversation, User, Document, DocumentVersion, Message, PendingAction
from app.services.tracing import trace_scope, active_trace, active_node, event, step, mark, composition
from app.providers.business import business_tool
from app.providers.ai import ProviderError, chat
from app.services.knowledge import retrieve
from app.services.runtime_config import active_config_row, active_prompt_values
from app.services.routing import intent_for, route_question, order_id_from, product_id_from, latest_order_query
from app.services.business_reply import product_reply, facts_reply, refund_reply, safe_facts, STATUS_LABELS


def handoff(db: Session, conversation: Conversation, reason: str) -> str:
    conversation.status = "WAITING_USER"
    conversation.handoff_reason = reason[:255]
    conversation.current_agent_id = None
    db.add(AuditLog(tenant_id=conversation.tenant_id, actor="system", action="handoff",
                    target=f"conversation:{conversation.id}", detail={"reason": reason},
                    trace_id=active_trace.get().trace_id if active_trace.get() else None))
    event('local.handoff', '进入人工队列', input={'reason': reason},
          output={'conversation_status': 'WAITING_USER', 'agent_id': None})
    mark(handoff=True, handoff_reason=reason, outcome='HANDOFF')
    return "我暂时无法可靠处理这个问题，已为您转接人工客服。"


def answer(db: Session, conversation: Conversation, customer: User, text: str,
           on_delta: Callable[[str], None] | None = None) -> Message:
    question_id = db.scalar(select(Message.id).where(Message.conversation_id == conversation.id,
        Message.sender_type == 'CUSTOMER').order_by(Message.id.desc()).limit(1))
    with trace_scope(db, conversation, customer, text, question_message_id=question_id) as recorder:
        event('local.receive', '接收客户问题', input={'content': text, 'user_id': customer.id,
              'conversation_id': conversation.id, 'message_id': question_id}, output={'authenticated': True})
        message = _answer(db, conversation, customer, text, on_delta)
        recorder.finish(status=recorder.values.get('status', 'SUCCESS'),
            outcome=recorder.values.get('outcome', 'ANSWERED'), reply_message_id=message.id, final_reply=message.content)
        if db.get_bind().dialect.name == 'sqlite':
            db.commit()
        return message


def _answer(db: Session, conversation: Conversation, customer: User, text: str,
            on_delta: Callable[[str], None] | None = None) -> Message:
    started = time.monotonic()
    trace_id = active_trace.get().trace_id
    intent = intent_for(text)
    model_row = active_config_row(db, conversation.tenant_id, "model")
    prompt_config = active_prompt_values(db, conversation.tenant_id)
    rag_row = active_config_row(db, conversation.tenant_id, "rag")
    model_config = model_row.value if model_row else {}
    rag_config = rag_row.value if rag_row else {}
    selected_model = model_config.get("llm_model") or ("demo-extractive" if settings().llm_mode == "mock" else settings().llm_model)
    execution = SimpleNamespace(intent=intent, status='RUNNING', error=None)
    versions = {'model': model_row.id if model_row else None, 'rag': rag_row.id if rag_row else None}
    mark(model=selected_model, config_versions=versions)
    event('local.configuration', '读取本轮配置快照', input={'tenant_id': conversation.tenant_id},
        output={'versions': versions, 'prompt_keys': sorted(prompt_config),
                'model': model_config, 'prompt': prompt_config, 'rag': rag_config,
                'selected_model': selected_model})
    citations = []
    try:
        decision, route_source, routing_context = route_question(
            db, conversation, customer, text, selected_model, prompt_config)
        intent = execution.intent = decision.intent
        call = lambda name, identifier: business_tool(db, trace_id, conversation.id, customer.id, name, identifier)
        if intent == "human":
            response = handoff(db, conversation, "User requested human")
        elif intent == "chitchat":
            response = "您好，我可以帮您查询订单、物流、退款进度，或解答售后规则。"
        elif intent == "clarify":
            mark(outcome='CLARIFY')
            response = decision.question or "请补充商品名称或订单号，我会查询实际信息。"
        elif decision.route in ("business", "hybrid"):
            identifier = decision.order_id
            facts = None
            if intent == "product_query":
                response, facts = product_reply(decision, routing_context, call)
            elif not identifier:
                result = call("list_orders", "")
                orders = result.get("data", {}).get("orders", [])[:5]
                if latest_order_query(text) and orders:
                    # list_orders is scoped to the authenticated customer and account;
                    # adapters return newest orders first. Fetch live facts for that order.
                    identifier = orders[0]["order_id"]
                    event('local.latest_order', '选择客户最新订单', input={'candidate_count': len(orders)},
                          output={'selected_order_id': identifier, 'selection': 'newest_first'})
                elif len(orders) == 1:
                    identifier = orders[0]["order_id"]
                else:
                    listing = "；".join(f"{item['order_id']}：{STATUS_LABELS.get(item.get('status'), item.get('status'))}" for item in orders)
                    response = ("您说的是哪笔订单？请回复订单号。最近订单：" + listing
                                if orders else "暂未查到订单，请提供订单号以便进一步查询。")
                    mark(outcome='CLARIFY')
            if identifier and intent == "business_action":
                action = decision.action
                order = call("get_order", identifier)
                if action == "apply_refund":
                    eligibility = business_tool(db, trace_id, conversation.id, customer.id,
                                                "get_refund_eligibility", identifier)
                    if not eligibility.get("data", {}).get("eligible") or eligibility.get("data", {}).get("refundable_amount") is None:
                        response = handoff(db, conversation, "Refund not eligible or requires review")
                    else:
                        response = _prepare_action(db, conversation, customer, action, identifier, order, eligibility)
                else:
                    response = _prepare_action(db, conversation, customer, action, identifier, order, None)
            elif identifier and intent != "product_query":
                tool = {"order_query": "get_order", "shipping_query": "get_shipping",
                        "refund_query": "get_refund_status", "refund_eligibility": "get_order"}[intent]
                result = call(tool, identifier)
                data = result.get("data", {})
                safe = facts = safe_facts(data)
                if intent == "refund_eligibility":
                    eligibility = call("get_refund_eligibility", identifier).get("data", {})
                    facts = dict(safe, **{k: eligibility[k] for k in ("eligible", "refundable_amount", "requires_human_approval") if k in eligibility})
                if not safe:
                    response = handoff(db, conversation, "Business API returned no displayable facts")
                else:
                    response = (refund_reply(identifier, data) if intent == "refund_query"
                                else f"订单 {identifier}：" + facts_reply(data))
                    if intent == "refund_eligibility":
                        response += "。" + ("业务系统当前允许提交退款申请，最终退货条件需结合政策核实。" if facts.get("eligible") and not facts.get("requires_human_approval") else "业务系统当前不能直接提交退款申请，请联系人工客服核实。")
            if decision.route == "hybrid" and facts:
                composition('template', response, [{'node_id': active_trace.get().last_business_node, 'business_facts': facts}])
                policy, citations = _knowledge_answer(db, conversation, execution, text, decision.knowledge_query or text,
                    rag_config, prompt_config, selected_model, None, facts)
                response += "\n" + policy
                composition('llm_policy' if not active_trace.get().values.get('handoff') else 'handoff', policy,
                            [{'citations': citations}])
            else:
                composition('template', response, [{'node_id': active_trace.get().last_business_node, 'business_facts': facts}] if facts else [])
        else:
            response, citations = _knowledge_answer(db, conversation, execution, text, text,
                rag_config, prompt_config, selected_model, on_delta)
            composition('llm_knowledge' if not active_trace.get().values.get('handoff') else 'handoff', response,
                        [{'citations': citations}])
        execution.status = "SUCCESS" if conversation.status != "WAITING_USER" else "HANDOFF"
    except ProviderError as exc:
        if exc.code == "ORDER_NOT_FOUND_OR_FORBIDDEN":
            execution.status = "SUCCESS"
            response = "未查到属于当前用户的这笔订单。请确认订单号和当前登录身份；运营创建的订单需要切换至下单客户后查询。"
        elif exc.code == "PRODUCT_NOT_FOUND":
            execution.status = "SUCCESS"
            response = "未查到这件商品，请确认商品名称或 SKU。"
        else:
            execution.status = "FAILED"
            execution.error = str(exc)[:500]
            response = handoff(db, conversation, "Provider unavailable")
        citations = []
    execution.latency_ms = int((time.monotonic() - started) * 1000)
    mark(status=execution.status, error=execution.error)
    event('local.reply_check', '确定最终回复', input={'intent': intent, 'conversation_status': conversation.status},
        output={'content': response, 'citations': citations, 'status': execution.status})
    if not active_trace.get().values.get('composition'):
        composition('handoff' if conversation.status == 'WAITING_USER' else 'template', response)
    message = Message(conversation_id=conversation.id, sender_type="AI", content=response, citations=citations)
    db.add(message)
    db.commit()
    db.refresh(message)
    event('local.persist', '保存最终回复', input={'content': response, 'citations': citations},
        output={'reply_message_id': message.id}, location='mysql')
    return message


def _knowledge_answer(db, conversation, execution, text, query, rag_config, prompt_config, selected_model,
                      on_delta=None, facts=None):
    citations = []
    all_matches = retrieve(db, conversation.tenant_id, query, conversation.account_id)
    matches = all_matches[:rag_config.get("final_top_k", 5)]
    if not matches:
        response = handoff(db, conversation, "Knowledge not found")
    else:
        context = []
        event('local.top_k', '选择最终知识片段', input={'final_top_k': rag_config.get('final_top_k', 5),
            'candidates': [{'chunk_id': chunk.id, 'content': chunk.content, 'source': source, 'score': score}
                           for chunk, source, score in all_matches]},
            output=[{'chunk_id': chunk.id, 'rank': rank, 'used': rank <= len(matches)}
                    for rank, (chunk, source, score) in enumerate(all_matches, 1)])
        for rank, (chunk, source, score) in enumerate(matches, 1):
            version = db.get(DocumentVersion, chunk.document_version_id)
            document = db.get(Document, version.document_id)
            citation = {"document_id": document.id, "version_id": version.id,
                        "title": document.title, "chunk_id": chunk.id}
            citations.append(citation)
            context.append(f"[{rank}] {chunk.content}")
        safety_instruction = prompt_config.get("knowledge_safety_instruction")
        if not safety_instruction:
            citations = []
            return handoff(db, conversation, "Knowledge prompt not configured"), citations
        system = safety_instruction.strip()
        if prompt_config.get("knowledge_instruction"):
            system += "\n" + prompt_config["knowledge_instruction"].strip()
        if facts and prompt_config.get("knowledge_facts_instruction"):
            system += "\n" + prompt_config["knowledge_facts_instruction"].strip()
            context.append("业务系统事实：" + str(facts))
        event('local.prompt', '组装知识回答提示词', input={'question': text, 'knowledge_query': query,
            'citations': citations, 'business_facts': facts, 'history': [],
            'history_used': False, 'knowledge_safety_instruction': safety_instruction,
            'knowledge_instruction': prompt_config.get('knowledge_instruction'),
            'knowledge_facts_instruction': prompt_config.get('knowledge_facts_instruction') if facts else None},
            output={'system': system, 'user': "知识片段：\n" + "\n".join(context) + "\n用户问题：" + text},
            sources=[{'node_id': active_trace.get().node_by_type.get('local.top_k'), 'citations': citations},
                     {'node_id': active_trace.get().last_business_node if facts else None, 'business_facts_included': bool(facts)}])
        response = chat(system, "知识片段：\n" + "\n".join(context) + "\n用户问题：" + text,
                        selected_model, on_delta)
        if not response or "【知识不足】" in response:
            citations = []
            response = handoff(db, conversation, "Knowledge insufficient")
    return response, citations


def _prepare_action(db: Session, conversation: Conversation, customer: User, action: str,
                    order_id: str, order: dict, eligibility: dict | None) -> str:
    detail = order.get("data", {})
    if action == "cancel_order" and detail.get("cancellable") is not True:
        return handoff(db, conversation, "Cancellation not explicitly allowed by business API")
    amount = eligibility.get("data", {}).get("refundable_amount") if eligibility else None
    if detail.get("requires_human_approval") or (eligibility and eligibility.get("data", {}).get("requires_human_approval")):
        return handoff(db, conversation, "Business action requires human approval")
    with step('local.pending_action', '创建待确认业务动作', input={'order_id': order_id, 'action': action,
        'order': order, 'eligibility': eligibility}) as node:
        pending = PendingAction(conversation_id=conversation.id, user_id=customer.id, action=action,
                            order_id=order_id, amount_snapshot=str(amount) if amount is not None else None,
                            idempotency_key=uuid.uuid4().hex,
                            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                            origin_trace_id=active_trace.get().trace_id, origin_node_id=node.id)
        db.add(pending)
        db.flush()
        node.output({'pending_action_id': pending.id, 'status': pending.status, 'expires_at': pending.expires_at,
                     'amount_snapshot': pending.amount_snapshot})
    mark(outcome='PENDING_CONFIRMATION', pending_action_id=pending.id)
    label = "取消订单" if action == "cancel_order" else "申请退款"
    amount_text = f"，业务系统显示可退金额 {amount}" if amount is not None else ""
    return f"订单 {order_id} 可提交{label}{amount_text}。请点击确认按钮执行；确认编号：{pending.id}。"
