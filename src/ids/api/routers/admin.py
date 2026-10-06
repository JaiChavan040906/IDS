"""Administrator endpoints (Stage 10) + retraining control (Stage 11)."""

import os
import time
from datetime import datetime, timezone
from typing import Literal

import psutil
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func

from ids.api.db import (Alert, AuditLog, Feedback, KREntry, ModelVersion, RetrainJob,
                        TrafficStat, User, audit, engine)
from ids.api.routers.analyst import feedback_out
from ids.api.routers.auth import user_out
from ids.api.security import admin_only, get_db, hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"])
STARTED = time.time()


# ---------------- users ----------------
class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    full_name: str
    role: Literal["analyst", "admin"]
    password: str = Field(min_length=6)


class UserPatch(BaseModel):
    full_name: str | None = None
    role: Literal["analyst", "admin"] | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=6)


@router.get("/users")
def users(admin: User = Depends(admin_only), db=Depends(get_db)):
    return [user_out(u) for u in db.query(User).order_by(User.id)]


@router.post("/users")
def create_user(body: UserIn, admin: User = Depends(admin_only), db=Depends(get_db)):
    if db.query(User).filter_by(username=body.username).count():
        raise HTTPException(409, "Username already exists")
    u = User(username=body.username, full_name=body.full_name, role=body.role,
             password_hash=hash_password(body.password))
    db.add(u)
    audit(db, admin.username, "user.create", body.username, role=body.role)
    db.commit()
    return user_out(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserPatch, admin: User = Depends(admin_only),
                db=Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id and (body.active is False or body.role == "analyst"):
        raise HTTPException(400, "You cannot deactivate or demote yourself")
    changes = body.model_dump(exclude_none=True)
    if "password" in changes:
        u.password_hash = hash_password(changes.pop("password"))
        changes["password"] = "reset"
    for k, v in changes.items():
        if k != "password":
            setattr(u, k, v)
    audit(db, admin.username, "user.update", u.username, **changes)
    db.commit()
    return user_out(u)


# ---------------- models ----------------
def model_out(m: ModelVersion) -> dict:
    return {k: getattr(m, k) for k in ("id", "version", "status", "parent", "metrics", "notes",
                                       "created_at", "decided_by", "deployed_at", "path")}


@router.get("/models")
def models(admin: User = Depends(admin_only), db=Depends(get_db)):
    return [model_out(m) for m in db.query(ModelVersion).order_by(ModelVersion.id.desc())]


class Decision(BaseModel):
    note: str = ""


def _get_model(db, version) -> ModelVersion:
    m = db.query(ModelVersion).filter_by(version=version).one_or_none()
    if not m:
        raise HTTPException(404, "Model version not found")
    return m


@router.post("/models/{version}/approve")
def approve(version: str, body: Decision, admin: User = Depends(admin_only), db=Depends(get_db)):
    m = _get_model(db, version)
    if m.status != "candidate":
        raise HTTPException(400, f"Only candidates can be approved (status: {m.status})")
    if not m.metrics.get("passed"):
        raise HTTPException(400, "This candidate failed its acceptance criteria; reject it")
    m.status, m.decided_by = "approved", admin.username
    m.notes = (m.notes + f"\nApproved: {body.note}").strip()
    audit(db, admin.username, "model.approve", version, note=body.note)
    db.commit()
    return model_out(m)


@router.post("/models/{version}/reject")
def reject(version: str, body: Decision, admin: User = Depends(admin_only), db=Depends(get_db)):
    m = _get_model(db, version)
    if m.status not in ("candidate", "approved"):
        raise HTTPException(400, f"Cannot reject a model with status {m.status}")
    m.status, m.decided_by = "rejected", admin.username
    m.notes = (m.notes + f"\nRejected: {body.note}").strip()
    audit(db, admin.username, "model.reject", version, note=body.note)
    db.commit()
    return model_out(m)


def _activate(request: Request, db, m: ModelVersion, admin: User, action: str, note: str):
    request.app.state.models.activate(m.path)          # fails before DB changes if broken
    for cur in db.query(ModelVersion).filter_by(status="active"):
        cur.status = "retired"
    m.status, m.deployed_at = "active", datetime.now(timezone.utc)
    m.decided_by = m.decided_by or admin.username
    audit(db, admin.username, action, m.version, note=note)


@router.post("/models/{version}/deploy")
def deploy(version: str, body: Decision, request: Request, admin: User = Depends(admin_only),
           db=Depends(get_db)):
    m = _get_model(db, version)
    if m.status != "approved":
        raise HTTPException(400, "Only approved models can be deployed")
    _activate(request, db, m, admin, "model.deploy", body.note)
    job = db.query(RetrainJob).filter_by(candidate_version=version).one_or_none()
    if job:
        for fid in job.results.get("feedback_ids", []):
            fb = db.get(Feedback, fid)
            if fb and not fb.used_in_version:
                fb.used_in_version = version
    db.commit()
    return model_out(m)


@router.post("/models/rollback")
def rollback(body: Decision, request: Request, admin: User = Depends(admin_only),
             db=Depends(get_db)):
    cur = db.query(ModelVersion).filter_by(status="active").one_or_none()
    if not cur or not cur.parent:
        raise HTTPException(400, "Active model has no parent to roll back to")
    prev = _get_model(db, cur.parent)
    _activate(request, db, prev, admin, "model.rollback", body.note or f"from {cur.version}")
    cur.status = "rolled_back"
    db.commit()
    return model_out(prev)


# ---------------- retraining ----------------
def job_out(j: RetrainJob) -> dict:
    return {k: getattr(j, k) for k in ("id", "created_by", "status", "base_version",
                                       "candidate_version", "n_feedback", "criteria", "results",
                                       "passed", "log", "created_at", "finished_at")}


@router.get("/retrain")
def retrain_jobs(request: Request, admin: User = Depends(admin_only), db=Depends(get_db)):
    from ids.api.services.retrain import usable_feedback
    svc = request.app.state.retrain
    return {"busy": svc.busy,
            "usable_feedback": len(usable_feedback(db, request.app.state.models.detector.enc.classes)),
            "config": svc.cfg,
            "jobs": [job_out(j) for j in db.query(RetrainJob).order_by(RetrainJob.id.desc())]}


@router.post("/retrain")
def start_retrain(request: Request, admin: User = Depends(admin_only), db=Depends(get_db)):
    try:
        job = request.app.state.retrain.create_job(db, admin.username)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return job_out(job)


@router.get("/retrain/{job_id}")
def retrain_job(job_id: int, admin: User = Depends(admin_only), db=Depends(get_db)):
    j = db.get(RetrainJob, job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return job_out(j)


# ---------------- feedback verification ----------------
@router.get("/feedback")
def feedback_list(verified: bool | None = None, admin: User = Depends(admin_only),
                  db=Depends(get_db)):
    q = db.query(Feedback, Alert).join(Alert, Alert.id == Feedback.alert_id)
    if verified is not None:
        q = q.filter(Feedback.verified.is_(verified))
    return [{**feedback_out(f), "predicted_class": a.predicted_class, "src_ip": a.src_ip,
             "dst_ip": a.dst_ip, "dst_port": a.dst_port, "decision": a.decision}
            for f, a in q.order_by(Feedback.id.desc()).limit(500)]


class VerifyIn(BaseModel):
    verified: bool


@router.post("/feedback/{fb_id}/verify")
def verify(fb_id: int, body: VerifyIn, admin: User = Depends(admin_only), db=Depends(get_db)):
    f = db.get(Feedback, fb_id)
    if not f:
        raise HTTPException(404, "Feedback not found")
    if f.used_in_version and not body.verified:
        raise HTTPException(400, f"Already used to train {f.used_in_version}")
    f.verified, f.verified_by = body.verified, admin.username if body.verified else None
    kr = db.query(KREntry).filter_by(feedback_id=f.id).one_or_none()
    if kr:
        kr.verified = body.verified
    audit(db, admin.username, "feedback.verify" if body.verified else "feedback.unverify",
          f"feedback:{f.id}")
    db.commit()
    return feedback_out(f)


# ---------------- audit, health, replay, evaluation ----------------
@router.get("/audit")
def audit_log(limit: int = 200, action: str | None = None, admin: User = Depends(admin_only),
              db=Depends(get_db)):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action.startswith(action))
    return [{k: getattr(a, k) for k in ("id", "ts", "username", "action", "target", "details")}
            for a in q.order_by(AuditLog.id.desc()).limit(min(limit, 1000))]


@router.get("/health")
def health(request: Request, admin: User = Depends(admin_only), db=Depends(get_db)):
    import torch
    st = request.app.state
    proc = psutil.Process(os.getpid())
    db_file = engine.url.database or ""
    return {
        "uptime_seconds": int(time.time() - STARTED),
        "active_model": st.models.version,
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_percent": psutil.virtual_memory().percent,
        "process_memory_mb": round(proc.memory_info().rss / 2**20, 1),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "db_size_mb": round(os.path.getsize(db_file) / 2**20, 2) if os.path.exists(db_file) else None,
        "counts": {"alerts": db.query(Alert).count(), "feedback": db.query(Feedback).count(),
                   "kr_entries": db.query(KREntry).count(), "users": db.query(User).count(),
                   "model_versions": db.query(ModelVersion).count()},
        "replay": st.replay.status(),
        "retraining_busy": st.retrain.busy,
    }


class ReplayIn(BaseModel):
    action: Literal["start", "stop", "reset", "configure"]
    mode: Literal["sequential", "attack_mix"] | None = None
    batch_size: int | None = Field(default=None, ge=1, le=2000)
    interval_seconds: float | None = Field(default=None, ge=0.1, le=60)
    attack_share: float | None = Field(default=None, gt=0, lt=1)


@router.get("/replay")
def replay_status(request: Request, admin: User = Depends(admin_only)):
    return request.app.state.replay.status()


@router.post("/replay")
def replay_control(body: ReplayIn, request: Request, admin: User = Depends(admin_only),
                   db=Depends(get_db)):
    r = request.app.state.replay
    if body.action == "start":
        r.start()
    elif body.action == "stop":
        r.stop()
    elif body.action == "reset":
        r.reset()
    else:
        r.configure(**body.model_dump(exclude={"action"}, exclude_none=True))
    audit(db, admin.username, f"replay.{body.action}", "",
          **body.model_dump(exclude={"action"}, exclude_none=True))
    db.commit()
    return r.status()


@router.get("/evaluation")
def evaluation(admin: User = Depends(admin_only), db=Depends(get_db)):
    """EVALUATION ONLY: compares model and analysts against the hidden labels."""
    per_version = (db.query(TrafficStat.model_version, func.sum(TrafficStat.n_flows),
                            func.sum(TrafficStat.n_correct), func.sum(TrafficStat.n_review),
                            func.sum(TrafficStat.n_missed_attacks))
                   .group_by(TrafficStat.model_version).all())
    rows = db.query(Feedback, Alert).join(Alert, Alert.id == Feedback.alert_id).all()
    decisive = [(f, a) for f, a in rows if f.verdict != "unsure"]
    analyst_right = sum(f.attack_class == a.hidden_label for f, a in decisive)
    model_right_on_same = sum(a.predicted_class == a.hidden_label for f, a in decisive)
    review = db.query(Alert).filter(Alert.decision == "review").all()
    return {
        "note": "Uses hidden ground-truth labels. For evaluation only; never shown to analysts.",
        "live_by_model_version": [
            {"version": v, "flows": n, "accuracy": c / n if n else None,
             "referral_rate": r / n if n else None, "missed_attacks": m}
            for v, n, c, r, m in per_version],
        "analyst_vs_truth": {
            "decisive_feedback": len(decisive),
            "analyst_accuracy": analyst_right / len(decisive) if decisive else None,
            "model_accuracy_on_same_alerts": model_right_on_same / len(decisive) if decisive else None,
        },
        "review_queue_model_accuracy":
            sum(a.predicted_class == a.hidden_label for a in review) / len(review) if review else None,
        "review_queue_size": len(review),
    }
