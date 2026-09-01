"""Authentication: password hashing and JWT issuing/verification.

This module only proves identity. It never decides what a user is
allowed to do — that's rbac.py's job, using the role looked up fresh
from the database on every request.
"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from dotenv import load_dotenv

load_dotenv()

# JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
# JWT_ALGORITHM = "HS256"
# JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

# if not JWT_SECRET_KEY:
#     raise RuntimeError("JWT_SECRET_KEY must be set in .env")

import streamlit as st

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not JWT_SECRET_KEY:
    JWT_SECRET_KEY = st.secrets.get("JWT_SECRET_KEY")

JWT_ALGORITHM = "HS256"

JWT_EXPIRE_MINUTES = int(
    os.getenv(
        "JWT_EXPIRE_MINUTES",
        st.secrets.get("JWT_EXPIRE_MINUTES", 60)
    )
)

if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is not configured")


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), password_hash.encode())


def create_access_token(user_id: int, username: str) -> str:
    """The token carries only identity (user id, username) — deliberately
    NOT role. Role is re-fetched from the database on every request, so
    a role change (e.g. demoting an admin) takes effect immediately
    instead of waiting for an old token to expire.
    """
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError (expired/invalid signature/malformed) on failure."""
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])