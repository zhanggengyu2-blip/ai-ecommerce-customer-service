from datetime import timezone
from sqlalchemy import select
from app.models import User


def iso(value):
    return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat() if value else None


def user_view(user):
    return {'id': user.id, 'tenant_id': user.tenant_id, 'kind': user.kind,
            'role': user.role, 'username': user.username or user.email,
            'display_name': user.display_name, 'active': user.active,
            'work_status': user.work_status}


def conversation_view(db, c):
    person = db.get(User, c.user_id)
    agent = db.get(User, c.current_agent_id) if c.current_agent_id else None
    return {'id': c.id, 'thread_id': c.thread_id, 'user_id': c.user_id,
            'customer_name': person.display_name if person else '',
            'account_id': c.account_id, 'status': c.status,
            'current_agent_id': c.current_agent_id,
            'agent_name': agent.display_name if agent else None,
            'reception_epoch': c.reception_epoch, 'revision': c.revision,
            'handoff_reason': c.handoff_reason, 'handoff_requested_at': iso(c.handoff_requested_at),
            'started_at': iso(c.started_at), 'closed_at': iso(c.closed_at),
            'last_message_at': iso(c.last_message_at),
            'consultation_summary': c.consultation_summary, 'summary_status': c.summary_status}


def message_view(db, message):
    sender = db.get(User, message.sender_user_id) if message.sender_user_id else None
    return {'id': message.id, 'conversation_id': message.conversation_id,
            'thread_id': message.thread_id, 'sender_type': message.sender_type,
            'sender_name': sender.display_name if sender else 'AI 客服' if message.sender_type=='AI' else '',
            'sender_user_id': message.sender_user_id, 'content': message.content,
            'content_type': message.content_type, 'created_at': iso(message.created_at),
            'client_message_id': message.client_message_id,'citations':message.citations or [],'trace_id':message.trace_id}
