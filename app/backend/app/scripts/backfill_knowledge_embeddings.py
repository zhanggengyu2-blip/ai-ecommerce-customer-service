"""Repair published knowledge vectors without resetting business data.

Run once without --apply to inspect; --apply calls the configured embedding provider.
All published versions are reindexed so a retry also repairs a partial OpenSearch write.
"""
import argparse

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Chunk, Document, DocumentVersion
from app.providers.ai import embed
from app.services.knowledge import index_chunks


def main(apply: bool) -> None:
    with SessionLocal() as db:
        versions = db.execute(
            select(DocumentVersion, Document)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(DocumentVersion.status == "PUBLISHED")
            .order_by(DocumentVersion.id)
        ).all()
        missing_total = 0
        for version, document in versions:
            chunks = db.scalars(
                select(Chunk).where(Chunk.document_version_id == version.id).order_by(Chunk.ordinal)
            ).all()
            missing = [chunk for chunk in chunks if chunk.embedding is None]
            missing_total += len(missing)
            print(f"version={version.id} account={document.account_id} chunks={len(chunks)} missing={len(missing)}")
            if not apply:
                continue
            if missing:
                vectors = embed([chunk.content for chunk in missing])
                for chunk, vector in zip(missing, vectors, strict=True):
                    chunk.embedding = vector
                if (version.error or "").startswith("Embedding unavailable ("):
                    version.error = None
                db.commit()
            # Reindex even if MySQL is complete: an earlier OpenSearch write may have failed.
            index_chunks(db, version, document)
        print(f"published_versions={len(versions)} missing_vectors={missing_total} applied={apply}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Generate missing vectors and reindex published versions")
    main(parser.parse_args().apply)
