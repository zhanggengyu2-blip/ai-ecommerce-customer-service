"""Rebuild the OpenSearch index from published knowledge stored in MySQL."""
import argparse

from app.core.database import SessionLocal
from app.services.knowledge import reindex_published_knowledge


def rebuild(tenant_id: int | None = None):
    with SessionLocal() as db:
        return reindex_published_knowledge(db, tenant_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", type=int)
    args = parser.parse_args()
    result = rebuild(args.tenant_id)
    print("Indexed {published_versions} published versions, {indexed_chunks} chunks; "
          "missing embeddings={missing_embeddings}".format(**result))
