import csv
from datetime import date
import html
import io
import math
import re
import zipfile
from xml.etree import ElementTree
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
import httpx
from fastapi import HTTPException
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session
from app.config.settings import settings
from app.models import Chunk, Document, DocumentVersion, ChannelAccount
from app.providers.ai import ProviderError, embed, rerank
from app.services.tracing import step, event, mark, safe_url
from app.services.knowledge_lifecycle import active_version
from app.services.runtime_config import active_config


def parse_file(filename: str, data: bytes) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix in ("txt", "md", "csv", "html", "htm"):
        text = data.decode("utf-8-sig")
        if suffix == "csv":
            rows = csv.DictReader(io.StringIO(text))
            return "\n".join("；".join(f"{k}: {v}" for k, v in row.items()) for row in rows)
        if suffix in ("html", "htm"):
            text = re.sub(r"<\s*(script|style).*?</\s*\1\s*>", "", text, flags=re.I | re.S)
            text = re.sub(r"</?(?:p|div|li|tr|h[1-6]|br)[^>]*>", "\n", text, flags=re.I)
            text = html.unescape(re.sub(r"<[^>]+>", "", text))
        return text
    if suffix == "docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                root = ElementTree.fromstring(archive.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            return "\n".join("".join(t.text or "" for t in p.findall(".//w:t", ns)) for p in root.findall(".//w:p", ns))
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
            raise HTTPException(422, "Invalid DOCX") from exc
    if suffix in ("pdf", "xlsx"):
        try:
            from docling.document_converter import DocumentConverter
            import tempfile
            from pathlib import Path
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / ("source." + suffix)
                path.write_bytes(data)
                return DocumentConverter().convert(str(path)).document.export_to_markdown()
        except ImportError as exc:
            raise HTTPException(422, "Install docling to parse PDF/XLSX") from exc
    raise HTTPException(415, "Unsupported file type")


def chunks_for(content: str, target: int = 420, overlap: int = 60) -> list[tuple[str, str]]:
    sections = re.split(r"(?=^#{1,4}\s|^第[一二三四五六七八九十\d]+[章节条])", content, flags=re.M)
    output = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        title = section.splitlines()[0][:255]
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", section) if p.strip()]
        current = ""
        for paragraph in paragraphs:
            while paragraph:
                room = target * 2 - len(current)
                if room <= 0:
                    output.append((title, current))
                    current = current[-overlap * 2:]
                    room = target * 2 - len(current)
                if len(paragraph) <= room:
                    current = (current + "\n" + paragraph).strip()
                    paragraph = ""
                else:
                    current = (current + "\n" + paragraph[:room]).strip()
                    paragraph = paragraph[room:]
                    output.append((title, current))
                    current = current[-overlap * 2:]
        if current:
            output.append((title, current))
    return output


def storage_client():
    s = settings()
    return boto3.client("s3", endpoint_url=s.minio_endpoint, aws_access_key_id=s.minio_access_key,
                        aws_secret_access_key=s.minio_secret_key, region_name="us-east-1",
                        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                                      connect_timeout=3, read_timeout=15, retries={"max_attempts": 1}))


def save_original(key: str, data: bytes, content_type: str):
    s = settings()
    if s.minio_endpoint:
        try:
            storage_client().put_object(Bucket=s.minio_bucket, Key=key, Body=data, ContentType=content_type)
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(503, "File storage unavailable; original was not saved") from exc
    else:
        from pathlib import Path
        path = Path("var/uploads") / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def load_original(key: str) -> bytes:
    s = settings()
    if s.minio_endpoint:
        try:
            return storage_client().get_object(Bucket=s.minio_bucket, Key=key)["Body"].read()
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(503, "File storage unavailable; original could not be loaded") from exc
    from pathlib import Path
    return (Path("var/uploads") / key).read_bytes()


def delete_original(key: str):
    s = settings()
    if s.minio_endpoint:
        try:
            storage_client().delete_object(Bucket=s.minio_bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise HTTPException(503, "Original file could not be deleted") from exc
        return
    from pathlib import Path
    path = (Path("var/uploads") / key).resolve()
    root = Path("var/uploads").resolve()
    if path.is_relative_to(root):
        path.unlink(missing_ok=True)


def process_version(db: Session, version: DocumentVersion, content: str):
    document = db.get(Document, version.document_id)
    rag = active_config(db, document.tenant_id, "rag")
    pieces = chunks_for(content, int(rag.get("target_chars", 800)), int(rag.get("overlap_chars", 100)))
    if not pieces:
        raise ValueError("No text extracted")
    vectors = None
    embedding_warning = None
    try:
        vectors = embed([part for _, part in pieces], active_config(db, document.tenant_id, "model"))
    except ProviderError as exc:
        embedding_warning = f"Embedding unavailable ({exc.code}); lexical search only"
    version.content = content
    for ordinal, (section, part) in enumerate(pieces):
        document = db.get(Document, version.document_id)
        db.add(Chunk(tenant_id=document.tenant_id, account_id=document.account_id,
                     platform_code=document.platform_code,
                     document_version_id=version.id, ordinal=ordinal, section=section,
                     content=part, embedding=vectors[ordinal] if vectors else None))
    version.status = "DRAFT"
    version.error = embedding_warning
    db.commit()
    return len(pieces)


def search_headers() -> dict:
    s = settings()
    import base64
    credentials = base64.b64encode(f"{s.opensearch_user}:{s.opensearch_password}".encode()).decode()
    return {"Authorization": f"Basic {credentials}"} if s.opensearch_user else {}


def ensure_index(dimension: int | None = None):
    s = settings()
    if not s.opensearch_url:
        return
    url = s.opensearch_url.rstrip("/") + "/knowledge_chunks"
    with httpx.Client(timeout=10) as client:
        response = client.head(url, headers=search_headers())
        if response.status_code == 404:
            r = client.put(url, headers=search_headers(), json={"settings": {"index": {"knn": True, "number_of_replicas": 0}}, "mappings": {"properties": {
                "tenant_id": {"type": "integer"}, "account_id": {"type": "integer"},
                "platform_code": {"type": "keyword"}, "document_id": {"type": "integer"},
                "version_id": {"type": "integer"}, "chunk_id": {"type": "integer"},
                "content": {"type": "text", "analyzer": "standard"},
                "tags": {"properties": {"type": {"type": "keyword"}, "category": {"type": "keyword"},
                    "valid_from": {"type": "date"}, "valid_until": {"type": "date"}}},
                "embedding": {"type": "knn_vector", "dimension": dimension or s.embedding_dim,
                              "method": {"name": "hnsw", "engine": "lucene", "space_type": "cosinesimil"}}}}})
            r.raise_for_status()
        else:
            response.raise_for_status()
            mapping = client.get(url + "/_mapping", headers=search_headers())
            mapping.raise_for_status()
            properties = mapping.json()["knowledge_chunks"]["mappings"]["properties"]
            existing_dimension = properties["embedding"]["dimension"]
            if existing_dimension != (dimension or s.embedding_dim):
                raise ProviderError("OpenSearch embedding dimension differs from configuration; rebuild a matching index")
            if 'tags' not in properties:
                update = client.put(url + '/_mapping', headers=search_headers(), json={'properties': {
                    'tags': {'properties': {'type': {'type': 'keyword'}, 'category': {'type': 'keyword'},
                        'valid_from': {'type': 'date'}, 'valid_until': {'type': 'date'}}}}})
                update.raise_for_status()


def index_chunks(db: Session, version: DocumentVersion, document: Document,
                 rows: list[Chunk] | None = None) -> int:
    s = settings()
    if not s.opensearch_url:
        return 0
    model_config = active_config(db, document.tenant_id, "model")
    dimension = int(model_config.get("embedding_dim") or s.embedding_dim)
    ensure_index(dimension)
    if rows is None:
        rows = db.scalars(select(Chunk).where(Chunk.document_version_id == version.id)).all()
    with httpx.Client(timeout=20) as client:
        for row in rows:
            body = {"tenant_id": document.tenant_id, "account_id": document.account_id,
                    "platform_code": document.platform_code, "document_id": document.id, "version_id": version.id,
                    "chunk_id": row.id, "content": row.content}
            if row.tags:
                body["tags"] = row.tags
            if row.embedding:
                body["embedding"] = row.embedding
            r = client.put(f"{s.opensearch_url.rstrip('/')}/knowledge_chunks/_doc/{row.id}?refresh=true",
                           headers=search_headers(), json=body)
            r.raise_for_status()
    return len(rows)


def reindex_published_knowledge(db: Session, tenant_id: int | None = None) -> dict[str, int]:
    """Restore published knowledge documents in OpenSearch from MySQL chunks."""
    if not settings().opensearch_url:
        raise ProviderError("opensearch_not_configured")
    query = (select(DocumentVersion, Document)
             .join(Document, DocumentVersion.document_id == Document.id)
             .where(DocumentVersion.status == "PUBLISHED"))
    if tenant_id is not None:
        query = query.where(Document.tenant_id == tenant_id)

    versions = db.execute(query.order_by(DocumentVersion.id)).all()
    chunk_count = 0
    missing_embeddings = 0
    for version, document in versions:
        chunks = db.scalars(
            select(Chunk).where(Chunk.document_version_id == version.id).order_by(Chunk.ordinal)
        ).all()
        missing_embeddings += sum(not chunk.embedding for chunk in chunks)
        chunk_count += index_chunks(db, version, document, chunks)

    return {
        "published_versions": len(versions),
        "indexed_chunks": chunk_count,
        "missing_embeddings": missing_embeddings,
    }


def delete_index_version(version_id: int):
    s = settings()
    if not s.opensearch_url:
        return
    with httpx.Client(timeout=20) as client:
        client.post(s.opensearch_url.rstrip("/") + "/knowledge_chunks/_delete_by_query?refresh=true",
                    headers=search_headers(), json={"query": {"term": {"version_id": version_id}}}).raise_for_status()


def retrieve(db: Session, tenant_id: int, query: str, account_id: int = 1,
             tag_filters: dict[str, str] | None = None) -> list[tuple[Chunk, str, float]]:
    with step('retrieval', '知识检索流程', input={'query': query, 'tenant_id': tenant_id,
              'account_id': account_id,
              'tag_filters': tag_filters or {},
              'opensearch_enabled': bool(settings().opensearch_url)}) as node:
        try:
            result = _retrieve(db, tenant_id, query, bool(settings().opensearch_url), account_id, tag_filters)
        except ProviderError as exc:
            if not settings().opensearch_url:
                raise
            mark(fallback=True)
            event('local.fallback', 'OpenSearch 失败，降级 MySQL', input={'code': exc.code}, output={'location': 'mysql'})
            result = _retrieve(db, tenant_id, query, False, account_id, tag_filters)
        node.output([{'chunk_id': c.id, 'content': c.content, 'version_id': c.document_version_id,
                      'source': source, 'score': score} for c, source, score in result])
        return result


def _search_post(client, url, payload, name):
    with step('search.' + name, 'OpenSearch ' + name, 'opensearch',
              input={'method': 'POST', 'url': safe_url(url), 'body': payload}) as node:
        response = client.post(url, headers=search_headers(), json=payload)
        node.output({'status_code': response.status_code, 'body': response.text}, 'raw_response')
        response.raise_for_status()
        node.output(response.json())
        return response


def _rank_rows(rows):
    return [{'chunk_id': row.id, 'version_id': row.document_version_id, 'content': row.content} for row in rows]


def _chunk_allowed(chunk: Chunk, filters: dict[str, str] | None = None) -> bool:
    tags = chunk.tags or {}
    today = date.today().isoformat()
    if tags.get('valid_from') and tags['valid_from'] > today:
        return False
    if tags.get('valid_until') and tags['valid_until'] < today:
        return False
    return all(tags.get(key) == value for key, value in (filters or {}).items() if key in ('type', 'category') and value)


def _retrieve(db: Session, tenant_id: int, query: str, use_opensearch: bool,
              account_id: int = 1, tag_filters: dict[str, str] | None = None) -> list[tuple[Chunk, str, float]]:
    s = settings()
    model_config = active_config(db, tenant_id, "model")
    account = db.get(ChannelAccount, account_id)
    platform = account.platform_code if account else 'SELF'
    allowed = or_(Document.account_id == account_id,
        and_(Document.account_id.is_(None), Document.platform_code == platform),
        and_(Document.account_id.is_(None), Document.platform_code.is_(None)))
    documents = db.scalars(select(Document).where(Document.tenant_id == tenant_id,
                                                   Document.is_active.is_(True), allowed)).all()
    scopes = [(active_version(db, doc.id), doc) for doc in documents]
    ranked_scopes = sorted(((version, doc) for version, doc in scopes if version), key=lambda item:
        (3 if item[1].account_id == account_id else 2 if item[1].platform_code == platform else 1), reverse=True)
    published = []
    titles = set()
    for version, doc in ranked_scopes:
        if doc.title not in titles:
            published.append(version.id)
            titles.add(doc.title)
    if not published:
        return []
    if not use_opensearch:
        rows = db.scalars(select(Chunk).join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
                          .join(Document, DocumentVersion.document_id == Document.id)
                          .where(Chunk.tenant_id == tenant_id,
                                 DocumentVersion.id.in_(published))).all()
        rows = [row for row in rows if _chunk_allowed(row, tag_filters)]
        if not rows:
            return []
        chinese = re.findall(r"[\u4e00-\u9fff]", query)
        terms = set(re.findall(r"[a-z0-9_-]+", query.lower()) + ["".join(chinese[i:i+2]) for i in range(len(chinese)-1)])
        lexical = [(row, sum(row.content.lower().count(t) for t in terms)) for row in rows]
        lexical = [row for row, score in sorted(lexical, key=lambda x: x[1], reverse=True) if score][:30]
        event('search.lexical', 'MySQL 本地词法检索', input={'query': query, 'terms': sorted(terms),
            'filters': {'tenant_id': tenant_id, 'account_id': account_id,
                        'version_status': 'PUBLISHED'}, 'limit': 30},
            output=_rank_rows(lexical), location='mysql')
        vector_rows: list[Chunk] = []
        try:
            query_vector = embed([query], model_config)[0]
            norm = math.sqrt(sum(x * x for x in query_vector)) or 1.0
            similarities = [(row, sum(x * y for x, y in zip(query_vector, row.embedding)) /
                             (norm * (math.sqrt(sum(y * y for y in row.embedding)) or 1.0)))
                            for row in rows if row.embedding and len(row.embedding) == len(query_vector)]
            vector_rows = [row for row, _ in sorted(similarities, key=lambda x: x[1], reverse=True)[:30]]
            event('search.local_vector', '本地向量相似度计算', input={'query_vector': query_vector,
                'candidates': _rank_rows(rows), 'metric': 'cosine', 'limit': 30},
                output=[{'chunk_id': row.id, 'score': score} for row, score in sorted(similarities, key=lambda x: x[1], reverse=True)[:30]])
        except ProviderError as exc:
            mark(fallback=True)
            event('local.fallback', 'Embedding 不可用，保留词法结果', input={'code': exc.code}, output={'vector_candidates': []})
        scores: dict[int, float] = {}
        sources: dict[int, str] = {}
        for source, candidates in (("LEXICAL", lexical), ("VECTOR", vector_rows)):
            for rank, row in enumerate(candidates, 1):
                scores[row.id] = scores.get(row.id, 0.0) + 1 / (60 + rank)
                sources[row.id] = "RRF" if row.id in sources else source
        by_id = {row.id: row for row in rows}
        candidates = [by_id[cid] for cid in sorted(scores, key=scores.get, reverse=True)[:20]]
        event('local.rrf', '本地 RRF 融合', input={'lexical': _rank_rows(lexical), 'vector': _rank_rows(vector_rows), 'k': 60, 'limit': 20},
            output=[{'chunk_id': c.id, 'score': scores[c.id], 'source': sources[c.id]} for c in candidates])
        try:
            order = rerank(query, [row.content for row in candidates], model_config) if candidates else []
            event('local.rerank_apply', '应用 Rerank 排序', input={'candidates': _rank_rows(candidates)}, output={'indices': order})
            candidates = [candidates[i] for i in order if 0 <= i < len(candidates)]
        except ProviderError as exc:
            mark(fallback=True)
            event('local.fallback', 'Rerank 不可用，保留融合排序', input={'code': exc.code}, output=_rank_rows(candidates))
        return [(row, sources[row.id], scores[row.id]) for row in candidates]
    event('local.published_filter', '读取允许检索的发布版本', input={'tenant_id': tenant_id,
          'account_id': account_id, 'platform_code': platform, 'status': 'PUBLISHED'},
          output={'version_ids': published}, location='mysql')
    filter_ = [{"term": {"tenant_id": tenant_id}}, {"terms": {"version_id": published}}]
    today = date.today().isoformat()
    for key, operator in (('valid_from', 'lte'), ('valid_until', 'gte')):
        filter_.append({'bool': {'should': [
            {'bool': {'must_not': {'exists': {'field': f'tags.{key}'}}}},
            {'range': {f'tags.{key}': {operator: today}}}], 'minimum_should_match': 1}})
    for key, value in (tag_filters or {}).items():
        if key in ('type', 'category') and value:
            filter_.append({'term': {f'tags.{key}': value}})
    url = s.opensearch_url.rstrip("/") + "/knowledge_chunks/_search"
    try:
        with httpx.Client(timeout=8) as client:
            bm = _search_post(client, url, {"size": 30, "query": {"bool": {"must": [{"match": {"content": query}}], "filter": filter_}}}, 'bm25')
            bm.raise_for_status()
            searches = [bm.json()["hits"]["hits"]]
            try:
                vector = embed([query], model_config)[0]
                ve = _search_post(client, url, {"size": 30, "query": {"knn": {"embedding": {
                    "vector": vector, "k": 30, "filter": {"bool": {"filter": filter_}}}}}}, 'vector')
                ve.raise_for_status()
                searches.append(ve.json()["hits"]["hits"])
            except (ProviderError, httpx.HTTPError, KeyError, ValueError) as exc:
                searches.append([])
                mark(fallback=True)
                event('local.fallback', '向量分支失败，保留 BM25', input={'code': getattr(exc, 'code', type(exc).__name__)}, output={'vector_hits': []})
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise ProviderError("Search service unavailable") from exc
    scores: dict[int, float] = {}
    sources: dict[int, str] = {}
    for source, hits in zip(("BM25", "VECTOR"), searches):
        for rank, hit in enumerate(hits, 1):
            cid = int(hit["_source"]["chunk_id"])
            scores[cid] = scores.get(cid, 0) + 1 / (60 + rank)
            sources[cid] = source if cid not in sources else "RRF"
    ids = sorted(scores, key=scores.get, reverse=True)[:20]
    event('local.rrf', '本地 RRF 融合', input={'bm25_hits': searches[0], 'vector_hits': searches[1], 'k': 60, 'limit': 20},
        output=[{'chunk_id': cid, 'score': scores[cid], 'source': sources[cid]} for cid in ids])
    rows = {row.id: row for row in db.scalars(select(Chunk).join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(Chunk.id.in_(ids), Chunk.tenant_id == tenant_id,
                   DocumentVersion.id.in_(published))).all()}
    candidates = [rows[cid] for cid in ids if cid in rows and _chunk_allowed(rows[cid], tag_filters)]
    event('local.chunk_validate', 'MySQL 核验知识版本与片段', input={'candidate_ids': ids, 'tenant_id': tenant_id},
        output=_rank_rows(candidates), location='mysql')
    try:
        order = rerank(query, [c.content for c in candidates], model_config) if candidates else []
        event('local.rerank_apply', '应用 Rerank 排序', input={'candidates': _rank_rows(candidates)}, output={'indices': order})
        candidates = [candidates[i] for i in order if 0 <= i < len(candidates)]
    except ProviderError as exc:
        mark(fallback=True)
        event('local.fallback', 'Rerank 不可用，保留融合排序', input={'code': exc.code}, output=_rank_rows(candidates))
    return [(c, sources[c.id], scores[c.id]) for c in candidates[:20]]
