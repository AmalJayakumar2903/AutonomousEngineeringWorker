import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    import redis
except ImportError:
    redis = None

try:
    import chromadb
except ImportError:
    chromadb = None

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)


# -------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_PATH = DATA_DIR / "worker.db"
CHROMA_PATH = DATA_DIR / "chroma"


# -------------------------------------------------------------------
# OpenTelemetry
# -------------------------------------------------------------------

_provider = TracerProvider()

_provider.add_span_processor(
    SimpleSpanProcessor(
        ConsoleSpanExporter()
    )
)

trace.set_tracer_provider(_provider)

tracer = trace.get_tracer(
    "autonomous-engineering-worker"
)


# -------------------------------------------------------------------
# SQLite audit database
# -------------------------------------------------------------------

def init_database() -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_runs (
                run_id TEXT PRIMARY KEY,
                request TEXT NOT NULL,
                repository TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                verified INTEGER DEFAULT 0,
                summary TEXT
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS worker_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                tool TEXT,
                success INTEGER,
                details TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        connection.commit()


def create_run(
    request: str,
    repository: str,
) -> str:
    init_database()

    run_id = str(uuid.uuid4())

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            INSERT INTO worker_runs
            (run_id, request, repository, status, started_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                run_id,
                request,
                repository,
                "running",
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        connection.commit()

    return run_id


def record_event(
    run_id: str,
    event_type: str,
    tool: str | None = None,
    success: bool | None = None,
    details: dict | str | None = None,
) -> None:
    init_database()

    if isinstance(details, dict):
        details = json.dumps(details)

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            INSERT INTO worker_events
            (run_id, event_type, tool, success, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                event_type,
                tool,
                None if success is None else int(success),
                details,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        connection.commit()


def complete_run(
    run_id: str,
    status: str,
    verified: bool,
    summary: str,
) -> None:
    init_database()

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            UPDATE worker_runs
            SET status = ?,
                completed_at = ?,
                verified = ?,
                summary = ?
            WHERE run_id = ?
            """,
            (
                status,
                datetime.now(timezone.utc).isoformat(),
                int(verified),
                summary,
                run_id,
            ),
        )

        connection.commit()


def get_recent_runs(limit: int = 20) -> list[dict]:
    init_database()

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT *
            FROM worker_runs
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def get_run_events(run_id: str) -> list[dict]:
    init_database()

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT *
            FROM worker_events
            WHERE run_id = ?
            ORDER BY id
            """,
            (run_id,),
        ).fetchall()

    return [dict(row) for row in rows]


# -------------------------------------------------------------------
# Redis
# -------------------------------------------------------------------

_redis_client = None


def get_redis():
    global _redis_client

    if redis is None:
        return None

    if _redis_client is None:
        try:
            client = redis.Redis(
                host="localhost",
                port=6379,
                db=0,
                decode_responses=True,
                socket_connect_timeout=1,
            )

            client.ping()
            _redis_client = client

        except Exception:
            _redis_client = False

    return _redis_client if _redis_client is not False else None


def cache_run_status(
    run_id: str,
    status: str,
) -> None:
    client = get_redis()

    if client is None:
        return

    try:
        client.setex(
            f"worker:run:{run_id}:status",
            3600,
            status,
        )
    except Exception:
        pass


def get_cached_status(run_id: str) -> str | None:
    client = get_redis()

    if client is None:
        return None

    try:
        return client.get(
            f"worker:run:{run_id}:status"
        )
    except Exception:
        return None


# -------------------------------------------------------------------
# ChromaDB memory
# -------------------------------------------------------------------

_chroma_collection = None


def get_memory_collection():
    global _chroma_collection

    if chromadb is None:
        return None

    if _chroma_collection is None:
        try:
            client = chromadb.PersistentClient(
                path=str(CHROMA_PATH)
            )

            _chroma_collection = (
                client.get_or_create_collection(
                    name="worker_memory"
                )
            )

        except Exception:
            _chroma_collection = False

    return (
        _chroma_collection
        if _chroma_collection is not False
        else None
    )


def remember_run(
    run_id: str,
    request: str,
    outcome: str,
) -> None:
    collection = get_memory_collection()

    if collection is None:
        return

    try:
        collection.upsert(
            ids=[run_id],
            documents=[
                f"""
Task:
{request}

Outcome:
{outcome}
"""
            ],
            metadatas=[
                {
                    "run_id": run_id,
                }
            ],
        )

    except Exception:
        pass


def search_memory(
    query: str,
    limit: int = 3,
) -> list[str]:
    collection = get_memory_collection()

    if collection is None:
        return []

    try:
        result = collection.query(
            query_texts=[query],
            n_results=limit,
        )

        documents = result.get(
            "documents",
            [[]],
        )

        return documents[0] if documents else []

    except Exception:
        return []


# -------------------------------------------------------------------
# Observability helper
# -------------------------------------------------------------------

def trace_event(
    name: str,
    attributes: dict | None = None,
):
    return tracer.start_as_current_span(
        name,
        attributes=attributes or {},
    )


# -------------------------------------------------------------------
# Initialization
# -------------------------------------------------------------------

init_database()