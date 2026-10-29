"""Check MySQL/OpenSearch vector coverage and one account-scoped kNN result."""
import httpx
from sqlalchemy import select

from app.config.settings import settings
from app.core.database import SessionLocal
from app.models import Chunk, DocumentVersion
from app.services.knowledge import search_headers


def main() -> None:
    s = settings()
    with SessionLocal() as db:
        chunks = db.scalars(select(Chunk).join(DocumentVersion, Chunk.document_version_id == DocumentVersion.id)
                            .where(DocumentVersion.status == "PUBLISHED").order_by(Chunk.id)).all()
        coverage = [(c.id, c.account_id, len(c.embedding) if c.embedding else 0) for c in chunks]
        print("mysql_published_vectors=", coverage)
        if not chunks or not all(c.embedding and len(c.embedding) == s.embedding_dim for c in chunks):
            raise RuntimeError("Some published chunks have no valid embedding")
        sample = chunks[0]
        with httpx.Client(timeout=10) as client:
            endpoint = s.opensearch_url.rstrip("/") + "/knowledge_chunks/_search"
            response = client.post(endpoint, headers=search_headers(), json={
                "size": 10, "_source": ["chunk_id", "account_id"],
                "query": {"knn": {"embedding": {"vector": sample.embedding, "k": 10,
                    "filter": {"bool": {"filter": [{"term": {"tenant_id": sample.tenant_id}},
                                               {"term": {"account_id": sample.account_id}}]}}}}},
            })
            response.raise_for_status()
            hits = [(hit["_source"]["chunk_id"], hit["_source"]["account_id"])
                    for hit in response.json()["hits"]["hits"]]
            print("opensearch_knn_hits=", hits)
            if sample.id not in [chunk_id for chunk_id, _ in hits]:
                raise RuntimeError("Known vector not returned by OpenSearch kNN")


if __name__ == "__main__":
    main()
