"""Deterministic role-based access control.

This module (together with sql_validator.is_query_allowed) is the ONLY
authority on whether an operation is permitted. The LLM in agents.py
never makes this decision — it only proposes SQL, which is checked here
and, more importantly, checked again against the actual generated SQL
in sql_validator.py before anything reaches the database.
"""

import re
from typing import Optional

ROLE_PERMISSIONS = {
    "admin": {"SELECT", "WITH", "INSERT", "UPDATE", "DELETE"},
    "employee": {"SELECT", "WITH"},
}

# Keyword hints used ONLY to fail fast on the raw natural-language request,
# before spending an LLM call generating SQL. This is a UX optimization,
# not a security boundary — a request can easily avoid these words while
# still implying a write. The real, non-bypassable check is
# sql_validator.is_query_allowed() applied to the SQL that actually gets
# generated.
_NL_OPERATION_HINTS = {
    "DELETE": ["delete", "remove", "drop "],
    "UPDATE": ["update", "change", "modify", "edit", "set "],
    "INSERT": ["add ", "insert", "create a new", "register "],
}


def guess_operation_from_text(text: str) -> Optional[str]:
    """Best-effort, non-authoritative guess at intended operation."""
    lowered = f" {text.lower()} "
    for operation, hints in _NL_OPERATION_HINTS.items():
        for hint in hints:
            if hint in lowered:
                return operation
    return None


def detect_operation_from_sql(sql: str) -> str:
    """Deterministic — reads the operation off the actual generated SQL."""
    match = re.match(r"\s*(\w+)", sql or "")
    return match.group(1).upper() if match else "UNKNOWN"


def is_authorized(role: str, operation: str) -> bool:
    return operation in ROLE_PERMISSIONS.get(role, set())