from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not configured. "
        "Set it to the PostgreSQL connection URL."
    )


# ================================================================
# FORCE PSYCOPG2
# ================================================================

if DATABASE_URL.startswith("postgresql+psycopg://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql+psycopg://",
        "postgresql+psycopg2://",
        1
    )

elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg2://",
        1
    )

elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql+psycopg2://",
        1
    )

print(
    "DATABASE DRIVER:",
    DATABASE_URL.split("://", 1)[0]
)

import sys

print("PYTHON EXECUTABLE:", sys.executable)

try:
    import psycopg
    print("PSYCOPG IMPORT: OK")
    print("PSYCOPG VERSION:", psycopg.__version__)
except Exception as exc:
    print("PSYCOPG IMPORT: FAILED")
    print("PSYCOPG ERROR:", repr(exc))

try:
    import psycopg2
    print("PSYCOPG2 IMPORT: OK")
    print("PSYCOPG2 VERSION:", psycopg2.__version__)
except Exception as exc:
    print("PSYCOPG2 IMPORT: FAILED")
    print("PSYCOPG2 ERROR:", repr(exc))


# ================================================================
# ENGINE
# pool_size     — number of persistent connections kept open
# max_overflow  — extra connections allowed beyond pool_size
# pool_pre_ping — checks connection health before using it
# ================================================================

engine = create_engine(
    DATABASE_URL,
    module=psycopg2,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False
)


# ================================================================
# SESSION FACTORY
# autocommit=False — we control when to commit
# autoflush=False  — we control when to flush
# ================================================================

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)


# ================================================================
# BASE
# all ORM models will inherit from this
# ================================================================

Base = declarative_base()


# ================================================================
# DEPENDENCY
# use this in every FastAPI route that needs a DB session
#
# Usage in a router:
#   from database import get_db
#   from sqlalchemy.orm import Session
#   from fastapi import Depends
#
#   @router.post("/upload")
#   def upload(db: Session = Depends(get_db)):
#       ...
# ================================================================

def get_db():
    db = SessionLocal()

    try:
        yield db

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ================================================================
# INIT DB
# creates all tables that don't exist yet
# call this once on app startup from main.py
#
# Usage in main.py:
#   from database import init_db
#
#   @app.on_event("startup")
#   def startup():
#       init_db()
# ================================================================

def init_db():

    # import all models here so Base knows about them
    from models import (       # noqa: F401
        fir,
        contact,
        bank,
        social,
        crime,
        surveillance,
        entities,
        llm_results,
        audit,
        users,
        role_permission,
    )

    Base.metadata.create_all(
        bind=engine
    )

    # Patch older databases that were created
    # before schema.sql was updated.
    with engine.begin() as conn:

        conn.execute(
            text(
                "ALTER TABLE fir_records "
                "ADD COLUMN IF NOT EXISTS "
                "locations_mentioned "
                "JSONB DEFAULT '[]'::jsonb"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE contact_records "
                "ADD COLUMN IF NOT EXISTS "
                "source_file VARCHAR(500)"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE contact_records "
                "ADD COLUMN IF NOT EXISTS "
                "source_hash VARCHAR(64)"
            )
        )

        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                uq_extracted_entities_fir_type_value
                ON extracted_entities
                (fir_id, entity_type, entity_value)
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                uq_role_permissions_role_resource
                ON role_permissions
                (role, resource)
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO role_permissions
                    (
                        role,
                        resource,
                        can_read,
                        can_write,
                        can_delete
                    )
                VALUES
                    (
                        'admin',
                        'fir_records',
                        TRUE,
                        TRUE,
                        TRUE
                    ),
                    (
                        'admin',
                        'graph',
                        TRUE,
                        TRUE,
                        TRUE
                    ),
                    (
                        'admin',
                        'audit_ledger',
                        TRUE,
                        FALSE,
                        FALSE
                    ),
                    (
                        'investigator',
                        'fir_records',
                        TRUE,
                        TRUE,
                        FALSE
                    ),
                    (
                        'investigator',
                        'graph',
                        TRUE,
                        TRUE,
                        FALSE
                    ),
                    (
                        'investigator',
                        'audit_ledger',
                        TRUE,
                        FALSE,
                        FALSE
                    ),
                    (
                        'viewer',
                        'fir_records',
                        TRUE,
                        FALSE,
                        FALSE
                    ),
                    (
                        'viewer',
                        'graph',
                        TRUE,
                        FALSE,
                        FALSE
                    ),
                    (
                        'viewer',
                        'audit_ledger',
                        FALSE,
                        FALSE,
                        FALSE
                    )
                ON CONFLICT (role, resource)
                DO NOTHING
                """
            )
        )

    print(
        "Database tables created / verified"
    )


# ================================================================
# HEALTH CHECK
# call this to verify DB connection is alive
# ================================================================

def check_db_connection() -> bool:

    try:

        with engine.connect() as conn:
            conn.execute(
                text("SELECT 1")
            )

        return True

    except Exception as e:

        print(
            f"Database connection failed: {e}"
        )

        return False