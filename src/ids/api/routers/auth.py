import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ids.api.db import Session as DBSession
from ids.api.db import User, audit
from ids.api.security import current_user, get_db, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


def user_out(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "role": u.role,
            "active": u.active}


@router.post("/login")
def login(body: LoginIn, db=Depends(get_db)):
    u = db.query(User).filter_by(username=body.username).one_or_none()
    if not u or not u.active or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Wrong username or password")
    token = secrets.token_hex(24)
    db.add(DBSession(token=token, user_id=u.id))
    audit(db, u.username, "auth.login")
    db.commit()
    return {"token": token, "user": user_out(u)}


@router.post("/logout")
def logout(user: User = Depends(current_user), db=Depends(get_db)):
    db.query(DBSession).filter_by(user_id=user.id).delete()
    audit(db, user.username, "auth.logout")
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)
