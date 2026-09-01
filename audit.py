"""Append-only audit logging for every agent interaction, allowed or denied."""

from datetime import datetime, timezone
from typing import Optional

from database import get_db_connection


def ensure_audit_table():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INT,
                    username VARCHAR(100),
                    role VARCHAR(20),
                    natural_language_request TEXT,
                    generated_sql TEXT,
                    operation VARCHAR(20),
                    authorization_result VARCHAR(20),
                    execution_status VARCHAR(20),
                    error_detail TEXT,
                    timestamp TIMESTAMPTZ NOT NULL
                );
                """
            )
        conn.commit()


def log_attempt(
    user_id: Optional[int],
    username: Optional[str],
    role: str,
    natural_language_request: str,
    generated_sql: Optional[str],
    operation: Optional[str],
    authorization_result: str,
    execution_status: str,
    error_detail: Optional[str] = None,
):
    """Writes one audit row. Never raises — a logging failure must not
    block or crash the request it's trying to record."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO audit_logs (
                        user_id, username, role, natural_language_request,
                        generated_sql, operation, authorization_result,
                        execution_status, error_detail, timestamp
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        user_id, username, role, natural_language_request,
                        generated_sql, operation, authorization_result,
                        execution_status, error_detail, datetime.now(timezone.utc),
                    ),
                )
            conn.commit()
    except Exception as e:
        print(f"AUDIT LOG ERROR: {e}")