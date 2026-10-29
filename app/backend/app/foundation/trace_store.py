"""Store real model attempts separately from reception mutations and token totals."""
import hashlib
import json
import logging
import time
import uuid
from contextlib import contextmanager
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import QuestionTrace, QuestionTraceNode, QuestionTracePayload, AiGeneration, Message, utcnow


def normalize_usage(raw):
    raw = raw if isinstance(raw, dict) else {}
    def number(*keys):
        for key in keys:
            value = raw.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        return None
    return {'input_tokens': number('prompt_tokens', 'input_tokens'),
            'output_tokens': number('completion_tokens', 'output_tokens'),
            'total_tokens': number('total_tokens')}


class Trace:
    def __init__(self, engine, *, tenant_id, account_id, user_id, kind, query,
                 conversation_id=None, question_message_id=None, config_versions=None, secrets=()):
        self.engine, self.id, self.conversation_id = engine, uuid.uuid4().hex, conversation_id
        self.secrets, self.errors, self.sequence = set(secrets), [], 0
        self.started = time.monotonic()
        self._write(lambda db: db.add(QuestionTrace(trace_id=self.id, tenant_id=tenant_id,
            account_id=account_id, user_id=user_id, kind=kind, query=self.clean(query),
            conversation_id=conversation_id, question_message_id=question_message_id,
            config_versions=config_versions or {})))

    def clean(self, value):
        if isinstance(value, dict):
            return {str(k): '[REDACTED]' if any(part in str(k).lower() for part in
                ('api_key', 'authorization', 'ciphertext', 'password', 'secret')) else self.clean(v) for k,v in value.items()}
        if isinstance(value, (tuple, list)):
            return [self.clean(v) for v in value]
        if isinstance(value, str):
            for secret in sorted(self.secrets, key=len, reverse=True):
                value = value.replace(secret, '[REDACTED]')
            return value
        return value

    def _write(self, fn):
        try:
            with Session(self.engine) as db:
                fn(db); db.commit()
        except Exception as exc:
            self.errors.append(type(exc).__name__)
            logging.getLogger(__name__).error('Model trace storage failed: %s', type(exc).__name__)

    @contextmanager
    def step(self, kind, name, *, data=None, model='', remote=False, attempt=1):
        self.sequence += 1
        node = {'input': data or {}, 'output': {}, 'usage': {}, 'status': 'SUCCESS', 'error': None}
        start = time.monotonic(); began = utcnow(); sequence = self.sequence
        try:
            yield node
        except Exception as exc:
            node['status'], node['error'] = 'FAILED', getattr(exc, 'code', type(exc).__name__)
            raise
        finally:
            def save(db):
                row = QuestionTraceNode(trace_id=self.id, conversation_id=self.conversation_id,
                    sequence=sequence, node_type=kind, name=name, location='remote_ai' if remote else 'local',
                    model=model, status=node['status'], attempt=attempt,
                    summary=self.clean(node['output']), usage={'reported': node['usage'], 'normalized': normalize_usage(node['usage'])} if remote else {},
                    error=node['error'], started_at=began, ended_at=utcnow(), latency_ms=int((time.monotonic()-start)*1000))
                db.add(row); db.flush()
                for key in ('input', 'output'):
                    content=json.dumps(self.clean(node[key]), ensure_ascii=False, allow_nan=False)
                    encoded=content.encode()
                    db.add(QuestionTracePayload(node_id=row.id,kind=key,content=content,
                        byte_size=len(encoded),sha256=hashlib.sha256(encoded).hexdigest()))
            self._write(save)
            if getattr(self,'pulse',None):self.pulse()

    def finish(self, *, status='SUCCESS', outcome='ANSWERED', **fields):
        def save(db):
            row=db.scalar(select(QuestionTrace).where(QuestionTrace.trace_id==self.id))
            if row:
                row.status, row.outcome, row.ended_at = status, outcome, utcnow()
                row.latency_ms=int((time.monotonic()-self.started)*1000)
                row.capture_complete, row.capture_errors = not self.errors, self.errors
                for key,value in fields.items():setattr(row,key,self.clean(value))
        self._write(save)


def conversation_usage(db, tenant_id, conversation_id):
    # Summary, publication, verification and recall tests never enter this set.
    traces=db.scalars(select(QuestionTrace).where(QuestionTrace.tenant_id==tenant_id,
        QuestionTrace.conversation_id==conversation_id, QuestionTrace.kind.in_(('question','assist','comfort')))).all()
    nodes=db.scalars(select(QuestionTraceNode).where(QuestionTraceNode.trace_id.in_([t.trace_id for t in traces]),
        QuestionTraceNode.location=='remote_ai')).all() if traces else []
    known=0; missing=0
    for node in nodes:
        usage=node.usage or {}; total=(usage.get('normalized') or normalize_usage(usage)).get('total_tokens')
        if total is None:missing+=1
        else:known+=total
    complete=not missing and all(t.capture_complete and t.status!='RUNNING' for t in traces)
    ids={t.trace_id for t in traces}
    jobs=db.scalars(select(AiGeneration).where(AiGeneration.tenant_id==tenant_id,
        AiGeneration.conversation_id==conversation_id,AiGeneration.mode.in_(('REPLY','ASSIST','COMFORT')))).all()
    # A missing trace is missing evidence, never a confirmed zero-token call.
    if any(j.status in ('PENDING','RUNNING') or (j.trace_id and j.trace_id not in ids)
           or (j.attempts>0 and j.status!='SUPERSEDED' and not j.trace_id) for j in jobs):
        complete=False
    message_traces=db.scalars(select(Message.trace_id).where(Message.tenant_id==tenant_id,
        Message.conversation_id==conversation_id,Message.sender_type=='AI')).all()
    if any(trace_id not in ids for trace_id in message_traces):complete=False
    return {'known_total_tokens':known,'complete':complete,'missing_usage_calls':missing,
            'call_count':len(nodes),'summary_excluded':True}
