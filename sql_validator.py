#keywords that modify databases tables or structures
import re
FORBIDDEN_KEYWORDS=["INSERT","UPDATE","DELETE","DROP","ALTER","TRUNCATE","CREATE","GRANT","REVOKE","EXEC","EXECUTE","PG_SLEEP",
                    "VACUUM","REINDEX","COPY"]

def is_query(sql_query:str):
    """query must start with SELECT or WITH statement
    query must not contain forbidden kwywords
    query must contain ; """
    if not sql_query.strip().upper().startswith(("SELECT","WITH")):
        return False
    for i in FORBIDDEN_KEYWORDS:
        if re.search(r"\b" + re.escape(i) + r"\b", sql_query, re.IGNORECASE):
            return False
    if not sql_query.endswith(";"):
        return False
    return True






# Write operations an ADMIN may perform through the agent. Everything else
# in FORBIDDEN_KEYWORDS (DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE,
# EXEC/EXECUTE, PG_SLEEP, VACUUM, REINDEX, COPY) stays blocked for EVERY
# role, admin included — the spec only grants admin
# SELECT/INSERT/UPDATE/DELETE, nothing schema-level or destructive.
ADMIN_ALLOWED_WRITE_KEYWORDS = ["INSERT", "UPDATE", "DELETE"]

ALWAYS_FORBIDDEN_KEYWORDS = [
    kw for kw in FORBIDDEN_KEYWORDS if kw not in ADMIN_ALLOWED_WRITE_KEYWORDS
]

ROLE_ALLOWED_STARTS = {
    "admin": ("SELECT", "WITH", "INSERT", "UPDATE", "DELETE"),
    "employee": ("SELECT", "WITH"),
}


def is_query_allowed(sql_query: str, role: str) -> bool:
    """Role-aware validator. This is the real, non-bypassable security
    boundary — it's applied to the SQL that actually gets generated,
    regardless of what the LLM was told in its system prompt or what the
    RBAC pre-check in rbac.py already guessed.

    EMPLOYEE: identical behavior to is_query() — SELECT/WITH only.
    ADMIN: additionally allows INSERT/UPDATE/DELETE. DROP/ALTER/CREATE/
    TRUNCATE and other dangerous statements remain blocked for everyone.
    """
    stripped = (sql_query or "").strip()

    if not stripped:
        return False

    # Reject multiple statements stacked in one string (e.g. "SELECT 1;
    # DROP TABLE users;") — only a single trailing semicolon is allowed.
    if stripped.count(";") > 1:
        return False
    if not stripped.endswith(";"):
        return False

    for kw in ALWAYS_FORBIDDEN_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", stripped, re.IGNORECASE):
            return False

    allowed_starts = ROLE_ALLOWED_STARTS.get(role, ("SELECT", "WITH"))
    if not stripped.upper().startswith(allowed_starts):
        return False

    return True
