from celery import Celery
from app.config.settings import settings
from app.core.database import SessionLocal
from app.models import DocumentVersion
from app.services.knowledge import load_original, parse_file, process_version

celery_app = Celery("agentserve", broker=settings().redis_url, backend=settings().redis_url)


@celery_app.task(name="agentserve.process_document", bind=True, max_retries=0)
def process_document_task(self, version_id: int, filename: str):
    with SessionLocal() as db:
        version = db.get(DocumentVersion, version_id)
        if not version or version.status != "PROCESSING" or not version.original_key:
            return {"status": "SKIPPED"}
        try:
            content = parse_file(filename, load_original(version.original_key))
            count = process_version(db, version, content)
            return {"status": "DRAFT", "chunks": count}
        except Exception as exc:
            db.rollback()
            version = db.get(DocumentVersion, version_id)
            version.status, version.error = "FAILED", str(exc)[:1000]
            db.commit()
            raise
