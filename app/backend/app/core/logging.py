"""Console and seven-day file logging for the backend."""

import logging
import sys
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_FORMAT = (
    "%(asctime)s %(levelname)-8s [pid=%(process)d] %(name)s "
    "%(pathname)s:%(lineno)d - %(message)s"
)


def _prune_archives(filename: str) -> None:
    # Keep today and the six preceding calendar days.
    cutoff = datetime.now().date() - timedelta(days=6)
    for archived in LOG_DIR.glob(f"{filename}.*"):
        try:
            day = datetime.strptime(archived.name[len(filename) + 1:], "%Y-%m-%d").date()
        except ValueError:
            continue
        if day < cutoff:
            archived.unlink(missing_ok=True)


class SevenDayFileHandler(TimedRotatingFileHandler):
    def doRollover(self) -> None:
        super().doRollover()
        _prune_archives(Path(self.baseFilename).name)


def _daily_handler(filename: str, level: int) -> TimedRotatingFileHandler:
    path = LOG_DIR / filename
    handler = SevenDayFileHandler(
        path, when="midnight", interval=1, backupCount=6, encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    _prune_archives(filename)
    return handler


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT)
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)

    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(_daily_handler("app.log", logging.INFO))
    root.addHandler(_daily_handler("error.log", logging.ERROR))

    # Uvicorn installs its own console handlers before importing the app.
    # Propagate those records to the root so access and startup logs reach files.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        logger.propagate = True

    logging.getLogger("httpx").setLevel(logging.WARNING)
