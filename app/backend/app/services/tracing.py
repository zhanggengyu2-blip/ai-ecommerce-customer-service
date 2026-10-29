"""Request-scoped observation. MySQL writes use a separate transaction from business work."""
import gzip
import hashlib
import json
import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import QuestionTrace, QuestionTraceNode, QuestionTracePayload, utcnow

active_trace = ContextVar('question_trace', default=None)
active_node = ContextVar('question_trace_node', default=None)
PAYLOAD_ROOT = Path(__file__).resolve().parents[2] / 'var' / 'trace_payloads'
SECRET_KEYS = {'authorization', 'cookie', 'set-cookie', 'password', 'api_key', 'apikey', 'key', 'client_secret', 'access_token',
               'refresh_token', 'secret', 'token', 'llm_api_key', 'ai_api_key', 'business_api_token',
               'embedding_api_key', 'rerank_api_key', 'opensearch_password', 'minio_secret_key',
               'jwt_secret', 'customer_token_secret', 'bootstrap_admin_password', 'x-integration-secret'}


def clean(value):
    if isinstance(value, dict):
        return {str(k): '[REDACTED]' if str(k).lower().replace('-', '_') in
                {key.replace('-', '_') for key in SECRET_KEYS} else clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, str):
        r = active_trace.get()
        for secret in sorted(r.secrets if r else [], key=len, reverse=True):
            value = value.replace(secret, '[REDACTED]')
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if hasattr(value, 'model_dump'):
        return clean(value.model_dump())
    return str(value)


def safe_url(url):
    parts = urlsplit(str(url))
    netloc = parts.netloc.rsplit('@', 1)[-1]
    query = [(k, '[REDACTED]' if k.lower() in SECRET_KEYS else v) for k, v in parse_qsl(parts.query)]
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), ''))


def payload_content(row):
    if row.content is not None:
        raw = row.content.encode('utf-8')
    else:
        path = (PAYLOAD_ROOT / (row.file_key or '')).resolve()
        if not path.is_relative_to(PAYLOAD_ROOT.resolve()):
            raise ValueError('Invalid payload path')
        raw = gzip.decompress(path.read_bytes())
    if hashlib.sha256(raw).hexdigest() != row.sha256:
        raise ValueError('Payload checksum mismatch')
    return json.loads(raw)


class Recorder:
    def __init__(self, db, conversation, user, query, **fields):
        self.db = db
        self.engine = db.get_bind()
        self.trace_id = uuid.uuid4().hex
        self.conversation_id = conversation.id
        self.sequence = 0
        self.tails = {}
        self.errors = []
        self.secrets = set()
        self.node_by_type = {}
        self.last_business_node = None
        self.started = time.monotonic()
        self.values = {}
        def create(session):
            row = QuestionTrace(trace_id=self.trace_id, tenant_id=conversation.tenant_id,
                account_id=conversation.account_id,
                conversation_id=conversation.id, user_id=user.id, query=query, **fields)
            session.add(row)
        self.write(create)

    def write(self, fn):
        try:
            # SQLite unit fixtures share one connection; production MySQL is independent.
            if self.engine.dialect.name == 'sqlite':
                result = fn(self.db)
                self.db.flush()
                return result
            with Session(self.engine, expire_on_commit=False) as session:
                result = fn(session)
                session.commit()
                return result
        except Exception as exc:
            code = type(exc).__name__
            self.errors.append(code)
            logging.getLogger(__name__).error('Trace capture failed: %s', code)
            return None

    def update(self, **fields):
        self.values.update(fields)
        def update(session):
            row = session.scalar(select(QuestionTrace).where(QuestionTrace.trace_id == self.trace_id))
            if row:
                for key, value in fields.items():
                    setattr(row, key, clean(value) if isinstance(value, (dict, list)) else value)
        self.write(update)

    def payload(self, node_id, kind, value):
        if not node_id:
            return
        try:
            raw = json.dumps(clean(value), ensure_ascii=False, allow_nan=False).encode('utf-8')
        except (ValueError, TypeError) as exc:
            self.errors.append('payload:' + type(exc).__name__)
            return
        digest = hashlib.sha256(raw).hexdigest()
        content, key = raw.decode('utf-8'), None
        if len(raw) > 48_000:
            key = f'{self.trace_id}/{node_id}-{kind}-{digest}.json.gz'
            try:
                path = PAYLOAD_ROOT / key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(gzip.compress(raw))
                content = None
            except OSError as exc:
                self.errors.append('payload:' + type(exc).__name__)
                return
        def save(session):
            row = session.scalar(select(QuestionTracePayload).where(
                QuestionTracePayload.node_id == node_id, QuestionTracePayload.kind == kind))
            if row is None:
                row = QuestionTracePayload(node_id=node_id, kind=kind)
                session.add(row)
            row.content, row.file_key, row.byte_size, row.sha256 = content, key, len(raw), digest
        self.write(save)

    def finish(self, **fields):
        self.update(**fields, ended_at=utcnow(), latency_ms=int((time.monotonic()-self.started)*1000),
                    capture_complete=not self.errors, capture_errors=self.errors[:])


class Span:
    def __init__(self, node_type, name, location='local', input=None, model='', sources=None, attempt=1):
        self.recorder = active_trace.get()
        self.id = None
        self.node_type, self.name, self.location = node_type, name, location
        self.input, self.model, self.sources, self.attempt = input, model, sources or [], attempt
        self.summary, self.usage = {}, {}
        self.status = 'SUCCESS'
        self.error = None

    def __enter__(self):
        self.started = time.monotonic()
        self.parent = active_node.get()
        if self.recorder:
            r = self.recorder
            def secrets(value):
                if isinstance(value, dict):
                    for key, item in value.items():
                        if str(key).lower().replace('-', '_') in {k.replace('-', '_') for k in SECRET_KEYS} and isinstance(item, str) and len(item) >= 6:
                            r.secrets.add(item)
                            if item.startswith('Bearer '):
                                r.secrets.add(item[7:])
                        else:
                            secrets(item)
                elif isinstance(value, list):
                    for item in value:
                        secrets(item)
            secrets(self.input)
            r.sequence += 1
            deps = [r.tails[self.parent]] if self.parent in r.tails else ([self.parent] if self.parent else [])
            def start(session):
                row = QuestionTraceNode(trace_id=r.trace_id, conversation_id=r.conversation_id,
                    parent_node_id=self.parent, depends_on=deps, sequence=r.sequence,
                    node_type=self.node_type, name=self.name, location=self.location,
                    model=self.model, sources=clean(self.sources), attempt=self.attempt)
                session.add(row)
                session.flush()
                return row.id
            self.id = r.write(start)
            r.payload(self.id, 'input', self.input)
        self.token = active_node.set(self.id or self.parent)
        return self

    def output(self, value, kind='output'):
        if self.recorder:
            self.recorder.payload(self.id, kind, value)
        return value

    def __exit__(self, exc_type, exc, tb):
        active_node.reset(self.token)
        if exc:
            self.status = 'FAILED'
            self.error = getattr(exc, 'code', type(exc).__name__)
            self.output({'code': self.error}, 'error')
        if self.recorder and self.id:
            def end(session):
                row = session.get(QuestionTraceNode, self.id)
                row.status, row.error = self.status, self.error
                row.summary, row.usage = clean(self.summary), clean(self.usage)
                row.ended_at = utcnow()
                row.latency_ms = int((time.monotonic()-self.started)*1000)
            self.recorder.write(end)
            self.recorder.tails[self.parent] = self.id
            self.recorder.node_by_type[self.node_type] = self.id
            if self.node_type == 'business.tool' and self.status == 'SUCCESS':
                self.recorder.last_business_node = self.id
        return False


def step(node_type, name, location='local', input=None, **kwargs):
    return Span(node_type, name, location, input, **kwargs)


def event(node_type, name, input=None, output=None, status='SUCCESS', **kwargs):
    with step(node_type, name, input=input, **kwargs) as node:
        node.output(output)
        node.status = status
    return node.id


def mark(**fields):
    if active_trace.get():
        active_trace.get().update(**fields)


def composition(kind, text, sources=None):
    r = active_trace.get()
    if r:
        parts = r.values.get('composition', []) + [{'kind': kind, 'text': text, 'sources': sources or []}]
        r.update(composition=parts)


@contextmanager
def trace_scope(db, conversation, user, query, **fields):
    recorder = Recorder(db, conversation, user, query, **fields)
    token = active_trace.set(recorder)
    node_token = active_node.set(None)
    try:
        yield recorder
    except BaseException as exc:
        status_code = getattr(exc, 'status_code', None)
        event('local.failure', '本轮执行异常', output={'code': getattr(exc, 'code', type(exc).__name__),
            'status_code': status_code, 'detail': getattr(exc, 'detail', None)}, status='FAILED')
        recorder.finish(status='FAILED', outcome='REJECTED' if status_code in (400,403,404,409) else 'ERROR',
                        error=getattr(exc, 'code', type(exc).__name__))
        raise
    finally:
        active_trace.reset(token)
        active_node.reset(node_token)
