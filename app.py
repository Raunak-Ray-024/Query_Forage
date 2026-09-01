"""
QueryForge — Secure Role-Based Agentic SQL Assistant
======================================================
A single-file Streamlit front end for the existing RBAC-enforced
LangGraph SQL agent (agents.py / rbac.py / sql_validator.py / auth.py /
audit.py / database.py). This file adds NO new authorization logic —
every authorization decision still happens in rbac.py / sql_validator.py,
exactly as before. This is presentation only.
"""

import io
import csv
import time

import streamlit as st

from database import get_db_connection, seed_database
from auth import verify_password, create_access_token, decode_access_token
from audit import ensure_audit_table, log_attempt
from rbac import ROLE_PERMISSIONS

# agents.py hard-requires GROQ_API_KEY at import time. QueryForge should
# still run (schema browsing, audit trail, dashboards, admin tools) even
# if no LLM key is configured yet — so the import is isolated and the
# Query Assistant page degrades gracefully if it fails.
try:
    from agents import ask_agent
    AGENT_AVAILABLE = True
    AGENT_ERROR = None
except Exception as exc:  # noqa: BLE001
    AGENT_AVAILABLE = False
    AGENT_ERROR = str(exc)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="QueryForge",
    page_icon="⚒️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# DESIGN TOKENS / CSS
# ============================================================

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,700;1,9..144,500&family=Sora:wght@300;400;500;600;700&display=swap');

:root{
  --bg:            #E9DBBF;
  --bg-alt:        #DFC89E;
  --surface:       #F7EEDC;
  --surface-raised:#FFFBF3;
  --line:          #B4915E;
  --line-soft:     #C9A76F;
  --ink:           #211404;
  --ink-soft:      #43301C;
  --ink-faint:     #5F4527;
  --primary:       #4A3220;
  --primary-dark:  #211404;
  --accent:        #7A4E27;
  --accent-soft:   #A97940;
  --olive:         #4F5C33;
  --brick:         #742F1F;
  --shadow:        rgba(33,20,4,0.22);
}

html, body, [class*="css"]{
  font-family: 'Sora', sans-serif;
  color: var(--ink);
  font-size: 16px;
  line-height: 1.55;
}

.stMarkdown p, .stMarkdown li, .stMarkdown{
  font-size: 1rem;
  color: var(--ink);
}
.stCaption, [data-testid="stCaptionContainer"]{
  font-size: 0.92rem !important;
  color: var(--ink-soft) !important;
}
p, span, div, label{ font-size: 1rem; }
h1{ font-size: 2rem !important; }
h2{ font-size: 1.5rem !important; }
h3{ font-size: 1.2rem !important; }
h4{ font-size: 1.05rem !important; }

.stApp{
  background:
    radial-gradient(1200px 600px at 85% -10%, #F7EFDF 0%, transparent 60%),
    var(--bg);
}

h1,h2,h3,h4, .qf-display{
  font-family: 'Fraunces', serif !important;
  color: var(--primary-dark);
  letter-spacing: 0.2px;
}

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"]{
  background: linear-gradient(180deg, #493827 0%, #33261B 100%);
  border-right: 1px solid #2A1F15;
}
[data-testid="stSidebar"] *{ color: #F5EAD3 !important; }
[data-testid="stSidebar"] .qf-brand-sub{ color: #D8BE93 !important; }
[data-testid="stSidebar"] hr{ border-color: rgba(239,227,204,0.18); }

/* Nav buttons render as light cream boxes (Streamlit's own button
   surface), so their label text needs dark brown, not the sidebar's
   default cream — and needs enough selector weight to beat the
   `[data-testid="stSidebar"] *` rule above and Streamlit's own button
   styles. Cover every DOM shape Streamlit has used for button labels. */
[data-testid="stSidebar"] .stButton button,
[data-testid="stSidebar"] button[kind],
[data-testid="stSidebar"] [data-testid^="stBaseButton"]{
  width: 100%;
  text-align: left;
  background: var(--surface-raised) !important;
  border: 1px solid var(--line-soft) !important;
  border-radius: 8px;
  padding: 0.55rem 0.9rem;
  font-weight: 600;
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.12s ease;
}
[data-testid="stSidebar"] .stButton button *,
[data-testid="stSidebar"] button[kind] *,
[data-testid="stSidebar"] [data-testid^="stBaseButton"] *,
[data-testid="stSidebar"] .stButton button p,
[data-testid="stSidebar"] button[kind] p{
  color: var(--primary-dark) !important;
  font-weight: 600 !important;
}
[data-testid="stSidebar"] .stButton button:hover,
[data-testid="stSidebar"] button[kind]:hover,
[data-testid="stSidebar"] [data-testid^="stBaseButton"]:hover{
  background: var(--accent-soft) !important;
  border-color: var(--accent) !important;
  transform: translateX(2px);
}
[data-testid="stSidebar"] .stButton button:hover *,
[data-testid="stSidebar"] button[kind]:hover *{
  color: var(--primary-dark) !important;
}
[data-testid="stSidebar"] .qf-nav-active button{
  background: var(--accent-soft) !important;
  border-color: var(--accent) !important;
}

/* ---------- Generic surfaces ---------- */
.qf-card{
  background: var(--surface);
  border: 1px solid var(--line-soft);
  border-radius: 10px;
  padding: 1.4rem 1.5rem;
  box-shadow: 0 6px 18px var(--shadow);
}

.qf-hero{
  animation: qf-rise 0.6s ease both;
}
@keyframes qf-rise{
  from{ opacity:0; transform: translateY(10px); }
  to{ opacity:1; transform: translateY(0); }
}

.qf-fade-in{ animation: qf-fade 0.5s ease both; }
@keyframes qf-fade{ from{opacity:0;} to{opacity:1;} }

.qf-stagger-1{ animation-delay: 0.05s; }
.qf-stagger-2{ animation-delay: 0.12s; }
.qf-stagger-3{ animation-delay: 0.19s; }
.qf-stagger-4{ animation-delay: 0.26s; }

/* ---------- KPI tiles ---------- */
.qf-kpi{
  background: var(--surface-raised);
  border: 1px solid var(--line-soft);
  border-radius: 10px;
  padding: 1.1rem 1.3rem;
  box-shadow: 0 4px 12px var(--shadow);
}
.qf-kpi .qf-kpi-label{
  font-size: 0.9rem;
  color: var(--ink-soft);
  font-weight: 600;
}
.qf-kpi .qf-kpi-value{
  font-family:'Fraunces', serif;
  font-size: 2.1rem;
  color: var(--primary-dark);
  line-height: 1.15;
}
.qf-kpi .qf-kpi-icon{ color: var(--accent); }

/* ---------- Badges / pills ---------- */
.qf-pill{
  display:inline-flex; align-items:center; gap:0.35rem;
  padding: 0.2rem 0.7rem;
  border-radius: 999px;
  font-size: 0.85rem;
  font-weight: 700;
  border: 1px solid transparent;
}
.qf-pill-admin{ background:#E6D2AC; color:#3A2814; border-color:#A9764E; }
.qf-pill-employee{ background:#D9E0C4; color:#37401F; border-color:#8B9968; }
.qf-pill-allowed{ background:#D9E0C4; color:#37401F; border-color:#8B9968; }
.qf-pill-denied{ background:#EAC7B9; color:#5C2415; border-color:#B96A4F; }

/* ---------- Buttons ---------- */
.stButton>button{
  background: var(--primary);
  color: #F7EFDF;
  border: 1px solid var(--primary-dark);
  border-radius: 8px;
  font-weight: 500;
  padding: 0.5rem 1.1rem;
  transition: background 0.18s ease, transform 0.12s ease;
}
.stButton>button:hover{
  background: var(--primary-dark);
  transform: translateY(-1px);
}
button[kind="secondary"]{
  background: var(--surface) !important;
  color: var(--primary-dark) !important;
}

/* ---------- Inputs ---------- */
/* Target both the class-based and BaseWeb/testid DOM Streamlit actually
   renders, so styling holds regardless of Streamlit version. */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input,
.stSelectbox [data-baseweb="select"] *,
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea,
[data-baseweb="select"] div,
div[data-testid="stChatInput"] textarea{
  background: var(--surface-raised) !important;
  color: var(--ink) !important;
  font-size: 1rem !important;
  font-weight: 500 !important;
  caret-color: var(--ink) !important;
}
.stTextInput > div,
.stTextArea > div,
.stNumberInput > div,
[data-baseweb="input"],
[data-baseweb="textarea"],
[data-baseweb="select"] > div,
div[data-testid="stChatInput"]{
  background: var(--surface-raised) !important;
  border: 1.5px solid var(--line) !important;
  border-radius: 8px !important;
}
.stTextInput input::placeholder,
.stTextArea textarea::placeholder,
div[data-testid="stChatInput"] textarea::placeholder{
  color: var(--ink-faint) !important;
  opacity: 1 !important;
}
.stTextInput label, .stTextArea label, .stSelectbox label, .stNumberInput label,
.stCheckbox label p{
  color: var(--ink) !important;
  font-size: 0.95rem !important;
  font-weight: 600 !important;
}
/* Focus state — visible brown ring instead of Streamlit's default red */
.stTextInput input:focus, .stTextArea textarea:focus,
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within,
[data-baseweb="select"] > div:focus-within{
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 2px rgba(122,78,39,0.25) !important;
}

/* Selectbox closed value + the icon next to it */
.stSelectbox [data-baseweb="select"] > div > div,
.stSelectbox [data-baseweb="select"] span,
.stSelectbox [data-baseweb="select"] svg{
  color: var(--ink) !important;
  fill: var(--ink) !important;
  font-weight: 500 !important;
}

/* The dropdown option list is rendered in a portal outside .stSelectbox,
   so it needs its own rules — otherwise it inherits Streamlit's default
   light-grey text on a white popover. */
ul[data-baseweb="menu"],
div[data-baseweb="popover"] ul{
  background: var(--surface-raised) !important;
  border: 1px solid var(--line) !important;
}
ul[data-baseweb="menu"] li,
ul[data-baseweb="menu"] li *,
div[data-baseweb="popover"] li,
div[data-baseweb="popover"] li *,
li[role="option"],
li[role="option"] *{
  color: var(--ink) !important;
  font-size: 1rem !important;
  font-weight: 500 !important;
}
li[role="option"]:hover,
ul[data-baseweb="menu"] li:hover{
  background: var(--bg-alt) !important;
}
li[aria-selected="true"]{
  background: var(--line-soft) !important;
}
[data-testid="stDataFrame"] *{ color: var(--ink) !important; }

/* ---------- DataFrame ---------- */
[data-testid="stDataFrame"]{
  border: 1px solid var(--line-soft);
  border-radius: 10px;
  overflow: hidden;
}

/* ---------- Expander (Schema Explorer table rows, Demo credentials) ---------- */
[data-testid="stExpander"]{
  background: var(--surface) !important;
  border: 1px solid var(--line-soft) !important;
  border-radius: 8px !important;
  margin-bottom: 0.5rem;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary *,
[data-testid="stExpander"] [data-testid="stExpanderToggleIcon"],
[data-testid="stExpander"] svg{
  color: var(--primary-dark) !important;
  fill: var(--primary-dark) !important;
  font-weight: 600 !important;
  font-size: 1rem !important;
}
[data-testid="stExpander"] summary:hover{
  background: var(--bg-alt) !important;
}
[data-testid="stExpanderDetails"]{
  background: var(--surface-raised) !important;
}

/* ---------- Divider ---------- */
.qf-divider{
  border: none; border-top: 1px solid var(--line);
  margin: 1.1rem 0;
}

/* ---------- Chat bubbles ---------- */
.qf-msg-user{
  background: var(--primary);
  color: #F7EFDF;
  border-radius: 12px 12px 2px 12px;
  padding: 0.7rem 1rem;
  margin: 0.35rem 0;
  max-width: 85%;
  margin-left: auto;
}
.qf-msg-agent{
  background: var(--surface-raised);
  border: 1px solid var(--line-soft);
  color: var(--ink);
  border-radius: 12px 12px 12px 2px;
  padding: 0.8rem 1rem;
  margin: 0.35rem 0;
  max-width: 92%;
}
.qf-msg-meta{
  font-size: 0.85rem;
  color: var(--ink-soft);
  margin-top: 0.35rem;
}
.qf-sql-block{
  background: #2E2115;
  color: #F0E1BE;
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 0.9rem;
  border-radius: 8px;
  padding: 0.75rem 0.9rem;
  margin-top: 0.4rem;
  overflow-x: auto;
  white-space: pre-wrap;
}

/* ---------- Forge loader ---------- */
.qf-forge-wrap{ display:flex; align-items:center; gap:0.8rem; padding: 0.6rem 0; }
.qf-spark{
  animation: qf-spark-pulse 1.1s ease-in-out infinite;
  transform-origin: center;
}
@keyframes qf-spark-pulse{
  0%,100%{ opacity:0.35; transform: scale(0.85); }
  50%{ opacity:1; transform: scale(1.05); }
}
.qf-forge-text{ color: var(--ink-soft); font-style: italic; }

/* ---------- Login ---------- */
.qf-login-wrap{ max-width: 430px; margin: 2.2rem auto 0 auto; }
.qf-login-card{
  background: var(--surface);
  border: 1px solid var(--line-soft);
  border-radius: 14px;
  padding: 2.1rem 2.2rem 1.6rem 2.2rem;
  box-shadow: 0 14px 38px var(--shadow);
  animation: qf-rise 0.55s ease both;
}
.qf-login-title{
  font-family:'Fraunces', serif;
  font-size: 1.9rem;
  color: var(--primary-dark);
  margin-bottom: 0.1rem;
}
.qf-login-sub{ color: var(--ink-soft); font-size: 1rem; margin-bottom: 1.3rem; }

/* Streamlit chrome cleanup */
#MainMenu{visibility:hidden;}
footer{visibility:hidden;}
header[data-testid="stHeader"]{ background: transparent; }
[data-testid="stMetricValue"]{ color: var(--primary-dark); font-family:'Fraunces', serif; }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


# ============================================================
# SVG ICONOGRAPHY (inline, brown line-art, no external images)
# ============================================================

def icon(name: str, size: int = 20, color: str = "currentColor") -> str:
    paths = {
        "forge": '<path d="M4 20h16"/><path d="M7 20l1-6h8l1 6"/><path d="M9 14V9a3 3 0 0 1 6 0v5"/><path d="M12 6V3"/><path d="M9.5 4.5l1-1.2"/><path d="M14.5 4.5l-1-1.2"/>',
        "dashboard": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
        "chat": '<path d="M21 12a7 7 0 0 1-7 7H8l-5 3 1.5-4.7A7 7 0 1 1 21 12Z"/><circle cx="9" cy="12" r="0.6" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="0.6" fill="currentColor" stroke="none"/><circle cx="15" cy="12" r="0.6" fill="currentColor" stroke="none"/>',
        "layers": '<path d="M12 3 2 8l10 5 10-5-10-5Z"/><path d="M2 13l10 5 10-5"/>',
        "scroll": '<path d="M6 4h11a2 2 0 0 1 2 2v13a1.5 1.5 0 0 1-3 0"/><path d="M6 4a2 2 0 0 0-2 2v11a2.5 2.5 0 0 0 2.5 2.5H16"/><path d="M8 8h7"/><path d="M8 12h7"/>',
        "users": '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 20a5.5 5.5 0 0 1 11 0"/><circle cx="17.5" cy="9" r="2.6"/><path d="M15 20a4.6 4.6 0 0 1 6.5-3.9"/>',
        "logout": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>',
        "shield": '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3Z"/><path d="M9 12l2 2 4-4"/>',
        "spark": '<path d="M12 2v6"/><path d="M12 16v6"/><path d="M2 12h6"/><path d="M16 12h6"/><path d="M4.9 4.9l4.2 4.2"/><path d="M14.9 14.9l4.2 4.2"/><path d="M19.1 4.9l-4.2 4.2"/><path d="M9.1 14.9l-4.2 4.2"/>',
        "download": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/>',
        "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M20 20l-4.5-4.5"/>',
        "warn": '<path d="M12 3l10 18H2L12 3Z"/><path d="M12 9v5"/><circle cx="12" cy="17" r="0.6" fill="currentColor" stroke="none"/>',
    }
    body = paths.get(name, "")
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )


def brand_mark(size: int = 34) -> str:
    return f'<span style="display:inline-flex;color:#CBA679;">{icon("forge", size, "#CBA679")}</span>'


def forge_loader(text: str = "Forging your query…") -> str:
    return (
        '<div class="qf-forge-wrap">'
        f'<span class="qf-spark" style="color:var(--accent);">{icon("spark", 24)}</span>'
        f'<span class="qf-forge-text">{text}</span>'
        "</div>"
    )


# ============================================================
# SESSION STATE
# ============================================================

DEFAULTS = {
    "authenticated": False,
    "token": None,
    "user_id": None,
    "username": None,
    "role": None,
    "name": None,
    "city": None,
    "page": "Dashboard",
    "chat_history": [],
    "db_ok": None,
}
for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val


# ============================================================
# DATA ACCESS HELPERS (thin wrappers around database.py)
# ============================================================

def run_query(sql: str, params: tuple = ()):
    """Internal helper for QueryForge's own UI queries — NOT the agent
    path. These are fixed, parameterized statements written by the app,
    never raw user input, so they sit outside the NL-agent RBAC boundary
    by design (the same way any admin dashboard queries its own DB)."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                conn.commit()
                return [], []
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            return cols, rows


def rows_to_dicts(cols, rows):
    return [dict(zip(cols, r)) for r in rows]


def get_schema_info():
    cols, rows = run_query(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position;
        """
    )
    schema = {}
    for table, column, dtype in rows:
        schema.setdefault(table, []).append((column, dtype))
    return schema


def get_audit_stats(role: str, user_id: int):
    scope_clause = "" if role == "admin" else "WHERE user_id = %s"
    params = () if role == "admin" else (user_id,)

    cols, rows = run_query(f"SELECT COUNT(*) FROM audit_logs {scope_clause};", params)
    total = rows[0][0] if rows else 0

    cols, rows = run_query(
        f"SELECT COUNT(*) FROM audit_logs {scope_clause}{' AND' if scope_clause else 'WHERE'} authorization_result='ALLOWED';",
        params,
    )
    allowed = rows[0][0] if rows else 0

    cols, rows = run_query(
        f"SELECT COUNT(*) FROM audit_logs {scope_clause}{' AND' if scope_clause else 'WHERE'} authorization_result='DENIED';",
        params,
    )
    denied = rows[0][0] if rows else 0

    op_clause = f"{scope_clause} " if scope_clause else ""
    cols, rows = run_query(
        f"""SELECT COALESCE(operation,'UNKNOWN') AS operation, COUNT(*) AS n
            FROM audit_logs {op_clause}
            GROUP BY operation ORDER BY n DESC;""",
        params,
    )
    by_op = rows_to_dicts(cols, rows)

    cols, rows = run_query(
        f"""SELECT username, role, natural_language_request, generated_sql,
                   operation, authorization_result, execution_status, timestamp
            FROM audit_logs {scope_clause}
            ORDER BY timestamp DESC LIMIT 8;""",
        params,
    )
    recent = rows_to_dicts(cols, rows)

    return {"total": total, "allowed": allowed, "denied": denied, "by_op": by_op, "recent": recent}


def get_all_users():
    cols, rows = run_query(
        "SELECT id, username, name, role, city, email, created_at FROM users ORDER BY id;"
    )
    return rows_to_dicts(cols, rows)


def update_user_role(target_user_id: int, new_role: str, actor: dict):
    run_query("UPDATE users SET role = %s WHERE id = %s;", (new_role, target_user_id))
    try:
        log_attempt(
            user_id=actor["user_id"],
            username=actor["username"],
            role=actor["role"],
            natural_language_request=f"[admin action] change role of user_id={target_user_id} to {new_role}",
            generated_sql=None,
            operation="ROLE_CHANGE",
            authorization_result="ALLOWED",
            execution_status="SUCCESS",
        )
    except Exception:
        pass


# ============================================================
# AUTH
# ============================================================

def attempt_login(username: str, password: str):
    try:
        cols, rows = run_query(
            "SELECT id, username, password_hash, role, name, city FROM users WHERE username = %s;",
            (username,),
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"Database unavailable: {exc}"

    if not rows:
        return False, "No account matches that username."

    user_id, db_username, password_hash, role, name, city = rows[0]
    if not verify_password(password, password_hash):
        return False, "Incorrect password."

    token = create_access_token(user_id, db_username)
    st.session_state.update(
        authenticated=True,
        token=token,
        user_id=user_id,
        username=db_username,
        role=role,
        name=name,
        city=city,
        page="Dashboard",
        chat_history=[],
    )
    return True, None


def session_still_valid() -> bool:
    if not st.session_state.token:
        return False
    try:
        decode_access_token(st.session_state.token)
        return True
    except Exception:  # noqa: BLE001
        return False


def do_logout():
    for key, val in DEFAULTS.items():
        st.session_state[key] = val


# ============================================================
# LOGIN PAGE
# ============================================================

def render_login():
    st.markdown('<div class="qf-login-wrap">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="qf-login-card">
          <div style="display:flex; align-items:center; gap:0.6rem; margin-bottom:0.9rem;">
            {icon('forge', 30, '#5B4130')}
            <span style="font-family:'Fraunces',serif; font-size:1.5rem; color:var(--primary-dark); font-weight:600;">QueryForge</span>
          </div>
          <div class="qf-login-title">Sign in</div>
          <div class="qf-login-sub">Role-aware access to your database, forged one query at a time.</div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username", placeholder="e.g. admin")
        password = st.text_input("Password", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Sign in", use_container_width=True)

    if submitted:
        if not username or not password:
            st.warning("Enter both a username and a password.")
        else:
            ok, err = attempt_login(username.strip(), password)
            if ok:
                st.rerun()
            else:
                st.error(err)

    with st.expander("Demo credentials"):
        st.markdown(
            "- **admin** / `admin123` — full read/write access\n"
            "- **employee** / `employee123` — read-only access\n"
            "- **john_doe** / `john123` — read-only access"
        )

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# SIDEBAR
# ============================================================

NAV_ITEMS = [
    ("Dashboard", "dashboard"),
    ("Query Assistant", "chat"),
    ("Schema Explorer", "layers"),
    ("Audit Trail", "scroll"),
    ("User Management", "users"),
]


def render_sidebar():
    with st.sidebar:
        st.markdown(
            f"""
            <div style="display:flex; align-items:center; gap:0.55rem; padding:0.4rem 0 0.2rem 0;">
              {icon('forge', 28, '#CBA679')}
              <div>
                <div style="font-family:'Fraunces',serif; font-size:1.25rem; font-weight:600; line-height:1.1;">QueryForge</div>
                <div class="qf-brand-sub" style="font-size:0.85rem;">Agentic SQL, governed by role</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<hr/>", unsafe_allow_html=True)

        role_class = "qf-pill-admin" if st.session_state.role == "admin" else "qf-pill-employee"
        st.markdown(
            f"""
            <div style="margin-bottom:0.9rem;">
              <div style="font-weight:700; font-size:1.05rem;">{st.session_state.name}</div>
              <div style="font-size:0.9rem; color:#D8BE93;">@{st.session_state.username} · {st.session_state.city or '—'}</div>
              <span class="qf-pill {role_class}" style="margin-top:0.4rem;">{st.session_state.role.upper()}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        for label, ic in NAV_ITEMS:
            if label == "User Management" and st.session_state.role != "admin":
                continue
            if label == "Audit Trail" and st.session_state.role != "admin":
                continue
            active = st.session_state.page == label
            wrap_class = "qf-nav-active" if active else ""
            st.markdown(f'<div class="{wrap_class}">', unsafe_allow_html=True)
            if st.button(f"{'●' if active else '○'}  {label}", key=f"nav_{label}", use_container_width=True):
                st.session_state.page = label
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<hr/>", unsafe_allow_html=True)
        if st.button("↩  Sign out", key="nav_logout", use_container_width=True):
            do_logout()
            st.rerun()

        st.markdown(
            '<div style="font-size:0.82rem; color:#C9B084; margin-top:1rem; line-height:1.5;">'
            "Every query is validated against role permissions before it "
            "touches the database. Admin-only writes: INSERT / UPDATE / DELETE."
            "</div>",
            unsafe_allow_html=True,
        )


# ============================================================
# DASHBOARD
# ============================================================

def kpi_tile(label, value, ic, delay_class=""):
    st.markdown(
        f"""
        <div class="qf-kpi qf-fade-in {delay_class}">
          <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            <div class="qf-kpi-label">{label}</div>
            <span class="qf-kpi-icon">{icon(ic, 18)}</span>
          </div>
          <div class="qf-kpi-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard():
    st.markdown(
        f"""
        <div class="qf-hero">
          <h1 style="margin-bottom:0.1rem;">Welcome back, {st.session_state.name.split()[0]}</h1>
          <div style="color:var(--ink-soft); margin-bottom:1.4rem;">
            {'A full view of every request across the organization.' if st.session_state.role=='admin'
             else 'A view of your own query activity and permissions.'}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        ensure_audit_table()
        stats = get_audit_stats(st.session_state.role, st.session_state.user_id)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not reach the database: {exc}")
        return

    perms = ", ".join(sorted(ROLE_PERMISSIONS.get(st.session_state.role, set())))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_tile("Total requests", stats["total"], "chat", "qf-stagger-1")
    with c2:
        kpi_tile("Allowed", stats["allowed"], "shield", "qf-stagger-2")
    with c3:
        kpi_tile("Denied", stats["denied"], "warn", "qf-stagger-3")
    with c4:
        kpi_tile("Permitted operations", perms or "—", "layers", "qf-stagger-4")

    st.markdown("<div class='qf-divider'></div>", unsafe_allow_html=True)

    col_left, col_right = st.columns([1.3, 1])

    with col_left:
        st.markdown("#### Requests by operation")
        if stats["by_op"]:
            chart_data = {row["operation"]: row["n"] for row in stats["by_op"]}
            st.bar_chart(chart_data, color="#A9764E")
        else:
            st.markdown(
                '<div class="qf-card">No agent activity yet — try the '
                "**Query Assistant** to generate your first request.</div>",
                unsafe_allow_html=True,
            )

    with col_right:
        st.markdown("#### Access snapshot")
        st.markdown(
            f"""
            <div class="qf-card">
              <div style="margin-bottom:0.6rem;"><b>Role</b> · {st.session_state.role}</div>
              <div style="margin-bottom:0.6rem;"><b>Read</b> · SELECT / WITH — always allowed</div>
              <div><b>Write</b> · INSERT / UPDATE / DELETE — {'allowed' if st.session_state.role=='admin' else 'blocked'}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div class='qf-divider'></div>", unsafe_allow_html=True)
    st.markdown("#### Recent activity")
    if stats["recent"]:
        st.dataframe(stats["recent"], use_container_width=True, hide_index=True)
    else:
        st.caption("Nothing logged yet.")


# ============================================================
# QUERY ASSISTANT
# ============================================================

def render_query_assistant():
    st.markdown("<h1 class='qf-hero'>Query Assistant</h1>", unsafe_allow_html=True)
    st.markdown(
        "<div style='color:var(--ink-soft); margin-bottom:1rem;'>"
        "Ask a question in plain English. The agent inspects the schema, "
        "drafts SQL, and the validator enforces your role before anything runs."
        "</div>",
        unsafe_allow_html=True,
    )

    if not AGENT_AVAILABLE:
        st.markdown(
            f"""
            <div class="qf-card" style="border-color:#D9A28C;">
              <div style="display:flex; gap:0.6rem; align-items:flex-start;">
                <span style="color:var(--brick);">{icon('warn', 22)}</span>
                <div>
                  <b>Query Assistant is offline.</b><br/>
                  The LangGraph agent couldn't start: <code>{AGENT_ERROR}</code><br/>
                  Set <code>GROQ_API_KEY</code> (and <code>GROQ_MODEL</code>) in your <code>.env</code> file and restart QueryForge.
                  Dashboard, Schema Explorer, Audit Trail and User Management still work.
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    examples = [
        "Show every employee in the Engineering department",
        "List the five highest paid employees",
        "What are the total orders placed by each user?",
        "Add a new product called Desk Lamp priced at 39.99 in Accessories",
    ]
    st.markdown("**Try asking:**")
    cols = st.columns(len(examples))
    for c, ex in zip(cols, examples):
        with c:
            if st.button(ex, key=f"ex_{ex}", use_container_width=True):
                st.session_state["_pending_prompt"] = ex

    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(f"<div class='qf-msg-user'>{msg['content']}</div>", unsafe_allow_html=True)
        else:
            sql_html = (
                f"<div class='qf-sql-block'>{msg['sql']}</div>" if msg.get("sql") else ""
            )
            status = msg.get("status", "")
            pill_class = "qf-pill-allowed" if status == "ALLOWED" else ("qf-pill-denied" if status == "DENIED" else "")
            pill = f"<span class='qf-pill {pill_class}'>{status}</span>" if status else ""
            st.markdown(
                f"<div class='qf-msg-agent'>{msg['content']}{sql_html}"
                f"<div class='qf-msg-meta'>{pill}</div></div>",
                unsafe_allow_html=True,
            )

    prompt = st.chat_input("Ask about your data…")
    pending = st.session_state.pop("_pending_prompt", None)
    final_prompt = prompt or pending

    if final_prompt:
        st.session_state.chat_history.append({"role": "user", "content": final_prompt})
        st.markdown(f"<div class='qf-msg-user'>{final_prompt}</div>", unsafe_allow_html=True)

        loader = st.empty()
        loader.markdown(forge_loader("Forging your query…"), unsafe_allow_html=True)
        try:
            result = ask_agent(
                final_prompt,
                role=st.session_state.role,
                user_id=st.session_state.user_id,
                username=st.session_state.username,
            )
            status = "ALLOWED" if result["validation_passed"] else "DENIED"
            st.session_state.chat_history.append(
                {
                    "role": "agent",
                    "content": result["answer"],
                    "sql": result.get("sql"),
                    "status": status,
                }
            )
        except Exception as exc:  # noqa: BLE001
            st.session_state.chat_history.append(
                {"role": "agent", "content": f"Something went wrong: {exc}", "status": "DENIED"}
            )
        loader.empty()
        st.rerun()


# ============================================================
# SCHEMA EXPLORER
# ============================================================

def render_schema_explorer():
    st.markdown("<h1 class='qf-hero'>Schema Explorer</h1>", unsafe_allow_html=True)
    st.markdown(
        "<div style='color:var(--ink-soft); margin-bottom:1.2rem;'>"
        "The live structure of the database, exactly as the agent sees it."
        "</div>",
        unsafe_allow_html=True,
    )

    try:
        schema = get_schema_info()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not read schema: {exc}")
        return

    if not schema:
        st.info("No tables found in the public schema.")
        return

    search = st.text_input("", placeholder="Filter tables or columns…", label_visibility="collapsed")

    for table, columns in schema.items():
        if search:
            s = search.lower()
            if s not in table.lower() and not any(s in c.lower() for c, _ in columns):
                continue
        with st.expander(f"{table}  ·  {len(columns)} columns", expanded=bool(search)):
            st.dataframe(
                [{"Column": c, "Type": t} for c, t in columns],
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# AUDIT TRAIL (admin only)
# ============================================================

def render_audit_trail():
    st.markdown("<h1 class='qf-hero'>Audit Trail</h1>", unsafe_allow_html=True)
    st.markdown(
        "<div style='color:var(--ink-soft); margin-bottom:1.2rem;'>"
        "Every request the agent has processed — allowed or denied — is recorded here."
        "</div>",
        unsafe_allow_html=True,
    )

    try:
        ensure_audit_table()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not reach the database: {exc}")
        return

    f1, f2, f3, f4 = st.columns([1, 1, 1, 2])
    with f1:
        role_filter = st.selectbox("Role", ["All", "admin", "employee"])
    with f2:
        result_filter = st.selectbox("Result", ["All", "ALLOWED", "DENIED"])
    with f3:
        op_filter = st.selectbox("Operation", ["All", "SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "UNKNOWN"])
    with f4:
        search = st.text_input("Search request text", placeholder="e.g. salary, department…")

    clauses, params = [], []
    if role_filter != "All":
        clauses.append("role = %s"); params.append(role_filter)
    if result_filter != "All":
        clauses.append("authorization_result = %s"); params.append(result_filter)
    if op_filter != "All":
        clauses.append("operation = %s"); params.append(op_filter)
    if search:
        clauses.append("natural_language_request ILIKE %s"); params.append(f"%{search}%")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    try:
        cols, rows = run_query(
            f"""SELECT id, username, role, natural_language_request, generated_sql,
                       operation, authorization_result, execution_status, timestamp
                FROM audit_logs {where}
                ORDER BY timestamp DESC LIMIT 500;""",
            tuple(params),
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Query failed: {exc}")
        return

    records = rows_to_dicts(cols, rows)
    st.caption(f"{len(records)} record(s)")
    st.dataframe(records, use_container_width=True, hide_index=True)

    if records:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
        st.download_button(
            f"{icon('download', 14)} Export as CSV",
            data=buf.getvalue(),
            file_name="queryforge_audit_trail.csv",
            mime="text/csv",
        )


# ============================================================
# USER MANAGEMENT (admin only)
# ============================================================

def render_user_management():
    st.markdown("<h1 class='qf-hero'>User Management</h1>", unsafe_allow_html=True)
    st.markdown(
        "<div style='color:var(--ink-soft); margin-bottom:1.2rem;'>"
        "Accounts and roles. Role changes take effect immediately — no re-login required."
        "</div>",
        unsafe_allow_html=True,
    )

    try:
        users = get_all_users()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not reach the database: {exc}")
        return

    st.dataframe(users, use_container_width=True, hide_index=True)

    st.markdown("<div class='qf-divider'></div>", unsafe_allow_html=True)
    st.markdown("#### Change a role")

    if users:
        options = {f"{u['username']} ({u['role']})": u for u in users}
        choice = st.selectbox("User", list(options.keys()))
        target = options[choice]
        new_role = st.selectbox("New role", ["employee", "admin"], index=0 if target["role"] == "employee" else 1)

        disabled = target["id"] == st.session_state.user_id
        if disabled:
            st.caption("You can't change your own role from here.")

        if st.button("Apply role change", disabled=disabled):
            try:
                update_user_role(
                    target["id"],
                    new_role,
                    actor={
                        "user_id": st.session_state.user_id,
                        "username": st.session_state.username,
                        "role": st.session_state.role,
                    },
                )
                st.success(f"{target['username']} is now {new_role}.")
                time.sleep(0.6)
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Update failed: {exc}")

    st.markdown("<div class='qf-divider'></div>", unsafe_allow_html=True)
    st.markdown("#### Demo data")
    st.caption("Rebuilds the sample schema and reseeds all demo users, employees, products and orders.")
    confirm = st.checkbox("I understand this drops and recreates the demo tables.")
    if st.button("Reseed demo database", disabled=not confirm):
        with st.spinner("Reseeding…"):
            try:
                seed_database()
                st.success("Demo database reseeded. Please sign in again.")
                time.sleep(1.0)
                do_logout()
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Reseed failed: {exc}")


# ============================================================
# MAIN ROUTER
# ============================================================

def main():
    inject_css()

    if not st.session_state.authenticated or not session_still_valid():
        if st.session_state.authenticated and not session_still_valid():
            do_logout()
            st.info("Your session expired. Please sign in again.")
        render_login()
        return

    render_sidebar()

    page = st.session_state.page
    if page == "Dashboard":
        render_dashboard()
    elif page == "Query Assistant":
        render_query_assistant()
    elif page == "Schema Explorer":
        render_schema_explorer()
    elif page == "Audit Trail" and st.session_state.role == "admin":
        render_audit_trail()
    elif page == "User Management" and st.session_state.role == "admin":
        render_user_management()
    else:
        st.session_state.page = "Dashboard"
        render_dashboard()


if __name__ == "__main__":
    main()