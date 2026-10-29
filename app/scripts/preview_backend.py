"""Run the original backend against a separate, local SQLite demo database.

This helper copies selected public seed tables, never loads the upstream .env,
and disables external AI, search and commerce services. It does not change the
application's authentication or business handlers.
"""
import argparse
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "var" / "preview"
DATABASE = DATA / "agentserve.db"
SEED = ROOT / "backend" / "db" / "agentserve.sql"
TABLES = {
    "tenant", "channel_account", "user", "staff_account_access",
    "external_customer_identity", "document", "document_version", "chunk",
    "prompt_template", "config_version", "eshop_customer", "eshop_product",
    "eshop_order", "eshop_order_item", "eshop_payment", "eshop_shipment",
    "eshop_refund", "eshop_inventory_log", "eshop_operation",
    "conversation", "message",
}


def values_tuple(text):
    """Decode the dump's single-row VALUES tuples into bound SQLite values."""
    text = text.strip()
    if not text.startswith("(") or not text.endswith(");"):
        raise ValueError("Unexpected seed tuple format")
    result, i = [], 1
    escapes = {"0": "\0", "b": "\b", "n": "\n", "r": "\r", "t": "\t", "Z": "\x1a"}
    while True:
        while text[i].isspace():
            i += 1
        if text[i] == "'":
            chars, i = [], i + 1
            while True:
                char = text[i]
                i += 1
                if char == "\\":
                    char = text[i]
                    i += 1
                    chars.append(escapes.get(char, char))
                elif char == "'":
                    if text[i] == "'":
                        chars.append("'")
                        i += 1
                    else:
                        break
                else:
                    chars.append(char)
            value = "".join(chars)
        else:
            start = i
            while text[i] not in ",)":
                i += 1
            atom = text[start:i].strip()
            if atom.upper() == "NULL":
                value = None
            elif re.fullmatch(r"-?\d+", atom):
                value = int(atom)
            elif re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", atom):
                value = float(atom)
            else:
                raise ValueError("Unexpected seed value type")
        result.append(value)
        while text[i].isspace():
            i += 1
        if text[i] == ")":
            if text[i:] != ");":
                raise ValueError("Unexpected data after seed tuple")
            return result
        if text[i] != ",":
            raise ValueError("Unexpected seed separator")
        i += 1


def initialize():
    from sqlalchemy import create_engine
    from app.models import Base
    from app.foundation.migrate import upgrade

    DATA.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='user'").fetchone()
        if exists and db.execute("SELECT 1 FROM user LIMIT 1").fetchone():
            engine = create_engine("sqlite:///" + str(DATABASE))
            try:
                upgrade(engine, adopt_legacy=True)
            finally:
                engine.dispose()
            print("Using existing local preview database.", flush=True)
            return
    engine = create_engine("sqlite:///" + str(DATABASE))
    Base.metadata.create_all(engine)
    upgrade(engine, adopt_legacy=True)
    engine.dispose()
    columns, table, inserted = {}, None, 0
    conversation_ids = set()
    with sqlite3.connect(DATABASE) as db:
        for line in SEED.read_text(encoding="utf-8").splitlines():
            definition = re.match(r"CREATE TABLE `([a-z_]+)`", line)
            if definition:
                table = definition.group(1)
                columns[table] = []
                continue
            column = re.match(r"\s+`([a-z_]+)`\s", line)
            if table and column:
                columns[table].append(column.group(1))
                continue
            match = re.match(r"INSERT INTO `([a-z_]+)` VALUES (.*)", line)
            if not match or match.group(1) not in TABLES:
                continue
            name = match.group(1)
            values = values_tuple(match.group(2))
            # Only the four public named demo identities; omit old guest sessions.
            if name == "user" and values[columns[name].index("id")] > 4:
                continue
            if name == "conversation":
                if values[columns[name].index("user_id")] not in (1, 2, 3, 4):
                    continue
                conversation_ids.add(values[columns[name].index("id")])
            if name == "message" and values[columns[name].index("conversation_id")] not in conversation_ids:
                continue
            if len(values) != len(columns[name]):
                raise ValueError(f"Seed column mismatch: {name}")
            fields = ",".join('"' + x + '"' for x in columns[name])
            placeholders = ",".join("?" for _ in values)
            db.execute(f'INSERT INTO "{name}" ({fields}) VALUES ({placeholders})', values)
            inserted += 1
        db.commit()
    DATABASE.chmod(0o600)
    print(f"Created separate preview database: {inserted} demo rows.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize-only", action="store_true")
    args = parser.parse_args()
    # A separate working directory prevents Settings from loading an existing .env.
    DATA.mkdir(parents=True, exist_ok=True)
    os.chdir(DATA)
    sys.path.insert(0, str(ROOT / "backend"))
    os.environ.update({
        "DATABASE_URL": "sqlite:///" + str(DATABASE),
        "JWT_SECRET": secrets.token_urlsafe(48),
        "CUSTOMER_TOKEN_SECRET": secrets.token_urlsafe(48),
        "BOOTSTRAP_ADMIN_PASSWORD": "", "DEMO_ENABLED": "true",
        "LLM_MODE": "mock", "BUSINESS_MODE": "mock", "ASYNC_INGESTION": "false",
        "LLM_API_KEY": "", "LLM_BASE_URL": "", "AI_API_KEY": "", "AI_BASE_URL": "",
        "EMBEDDING_API_KEY": "", "EMBEDDING_BASE_URL": "",
        "RERANK_API_KEY": "", "RERANK_URL": "", "BUSINESS_API_URL": "",
        "BUSINESS_API_TOKEN": "", "OPENSEARCH_URL": "", "MINIO_ENDPOINT": "",
    })
    initialize()
    if not args.initialize_only:
        import uvicorn
        uvicorn.run("app.main:app", host="127.0.0.1", port=8001, log_level="info")


if __name__ == "__main__":
    main()
