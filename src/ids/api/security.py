"""Simulated login: PBKDF2 password hashes + random bearer tokens stored in SQLite."""

import hashlib
import hmac
import secrets

from fastapi import Depends, Header, HTTPException

from ids.api.db import Session as DBSession
from ids.api.db import SessionLocal, User


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt, _ = stored.split("$", 1)
    return hmac.compare_digest(hash_password(password, salt), stored)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(authorization: str = Header(default=""), db=Depends(get_db)) -> User:
    token = authorization.removeprefix("Bearer ").strip()
    sess = db.get(DBSession, token) if token else None
    user = db.get(User, sess.user_id) if sess else None
    if not user or not user.active:
        raise HTTPException(401, "Not logged in")
    return user


def require(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"Requires role: {', '.join(roles)}")
        return user
    return dep


analyst_or_admin = require("analyst", "admin")
admin_only = require("admin")
