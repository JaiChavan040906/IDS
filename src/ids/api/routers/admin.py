"""Administrator endpoints (Stage 10) + retraining control (Stage 11)."""

import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import psutil
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func

from ids.api.db import (Alert, AuditLog, Feedback, KREntry, ModelVersion, RetrainJob,
                        TrafficStat, User, audit, engine)
from ids.api.routers.analyst import feedback_out
from ids.api.routers.auth import user_out
from ids.api.security import admin_only, get_db, hash_password
from ids.api.services import demo
from ids.flow_import import UNLABELLED, import_flows

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
            "demo_tools": request.app.state.cfg.get("demo_tools", True),
            "demo_decisions": demo.count_demo(db),
            "jobs": [job_out(j) for j in db.query(RetrainJob).order_by(RetrainJob.id.desc())]}


# ---------------- presentation helper (see services/demo.py) ----------------
class DemoSeedIn(BaseModel):
    count: int = Field(default=19, ge=1, le=200)
    verified: bool = True


def _demo_enabled(request: Request):
    if not request.app.state.cfg.get("demo_tools", True):
        raise HTTPException(403, "Demo tools are switched off (demo_tools: false in configs/app.yaml)")


@router.post("/demo/feedback")
def demo_seed(body: DemoSeedIn, request: Request, admin: User = Depends(admin_only),
              db=Depends(get_db)):
    _demo_enabled(request)
    try:
        return demo.seed_feedback(db, body.count, body.verified, admin.username)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/demo/feedback")
def demo_remove(request: Request, admin: User = Depends(admin_only), db=Depends(get_db)):
    _demo_enabled(request)
    return demo.remove_demo(db, admin.username)


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
def audit_log(request: Request, limit: int = 200, action: str | None = None,
              admin: User = Depends(admin_only), db=Depends(get_db)):
    q = db.query(AuditLog)
    if not getattr(request.app.state, "warehouse_enabled", False):
        q = q.filter(~AuditLog.action.startswith("warehouse."))   # hidden, not deleted
    if action:
        q = q.filter(AuditLog.action.startswith(action))
    return [{k: getattr(a, k) for k in ("id", "ts", "username", "action", "target", "details")}
            for a in q.order_by(AuditLog.id.desc()).limit(min(limit, 1000))]


class FeaturesIn(BaseModel):
    warehouse: bool


@router.post("/features")
def set_features(body: FeaturesIn, request: Request, admin: User = Depends(admin_only),
                 db=Depends(get_db)):
    """Admin on/off switch for the Warehouse tab. Lasts until the portal restarts; every start
    begins with the mode chosen by the start file (start_portal.bat = off)."""
    request.app.state.warehouse_enabled = body.warehouse
    # named warehouse.* so it is hidden from the audit list while the warehouse is off
    audit(db, admin.username, "warehouse.switch", "on" if body.warehouse else "off")
    db.commit()
    return {"features": {"warehouse": request.app.state.warehouse_enabled}}


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
    source: str | None = None


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
        try:
            r.configure(**body.model_dump(exclude={"action"}, exclude_none=True))
        except ValueError as e:
            raise HTTPException(400, str(e))
    audit(db, admin.username, f"replay.{body.action}", "",
          **body.model_dump(exclude={"action"}, exclude_none=True))
    db.commit()
    return r.status()


@router.get("/evaluation")
def evaluation(request: Request, admin: User = Depends(admin_only), db=Depends(get_db)):
    """EVALUATION ONLY: compares model and analysts against the hidden labels."""
    T = TrafficStat
    per = (db.query(T.source, T.model_version, func.sum(T.n_flows), func.sum(T.n_labelled),
                    func.sum(T.n_correct), func.sum(T.n_review), func.sum(T.n_missed_attacks),
                    func.sum(T.n_attacks), func.sum(T.n_caught), func.sum(T.n_benign),
                    func.sum(T.n_false_alarms))
           .group_by(T.source, T.model_version).all())
    names = {d["id"]: d["name"] for d in request.app.state.replay.datasets()}

    def ratio(a, b):
        return a / b if b else None

    rows = db.query(Feedback, Alert).join(Alert, Alert.id == Feedback.alert_id).all()
    decisive = [(f, a) for f, a in rows if f.verdict != "unsure" and a.hidden_label != UNLABELLED]
    analyst_right = sum(f.attack_class == a.hidden_label for f, a in decisive)
    model_right_on_same = sum(a.predicted_class == a.hidden_label for f, a in decisive)
    review = db.query(Alert).filter(Alert.decision == "review", Alert.hidden_label != UNLABELLED).all()
    return {
        "note": "Uses hidden ground-truth labels. For evaluation only; never shown to analysts.",
        "live": [
            {"source": src, "source_name": names.get(src, src), "version": v, "flows": n,
             "labelled_flows": nl, "accuracy": ratio(c, nl), "referral_rate": ratio(r, n),
             "attacks": na, "detection_rate": ratio(nc, na), "missed_attacks": m,
             "benign": nb, "false_alarm_rate": ratio(fa, nb)}
            for src, v, n, nl, c, r, m, na, nc, nb, fa in per],
        "analyst_vs_truth": {
            "decisive_feedback": len(decisive),
            "analyst_accuracy": ratio(analyst_right, len(decisive)),
            "model_accuracy_on_same_alerts": ratio(model_right_on_same, len(decisive)),
        },
        "review_queue_model_accuracy":
            ratio(sum(a.predicted_class == a.hidden_label for a in review), len(review)),
        "review_queue_size": len(review),
    }


# ---------------- traffic sources (uploaded CSVs) ----------------
MAX_UPLOAD_MB = 600


@router.get("/datasets")
def datasets(request: Request, admin: User = Depends(admin_only)):
    r = request.app.state.replay
    return {"current": r.source, "datasets": r.datasets(),
            "max_upload_mb": MAX_UPLOAD_MB, "max_rows": request.app.state.cfg.get("import_max_rows", 300_000)}


@router.post("/datasets")
def upload_dataset(request: Request, file: UploadFile = File(...),
                   admin: User = Depends(admin_only), db=Depends(get_db)):
    """Upload a CICFlowMeter CSV; it is checked, mapped to our columns and saved as a
    new traffic source for the replay. Large files are randomly sampled."""
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Please upload a .csv file")
    st = request.app.state
    uploads = Path(st.replay.uploads_dir)
    raw_dir = uploads / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / f"{int(time.time())}_{Path(file.filename).name}"
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out, length=4 * 2**20)
    if dest.stat().st_size > MAX_UPLOAD_MB * 2**20:
        dest.unlink()
        raise HTTPException(400, f"File is larger than {MAX_UPLOAD_MB} MB")
    pre = st.models.detector.pre
    try:
        meta = import_flows(dest, pre.candidate_cols, st.cfg_label_map, uploads,
                            name=Path(file.filename).stem,
                            max_rows=st.cfg.get("import_max_rows", 300_000))
    except ValueError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    audit(db, admin.username, "dataset.upload", meta["id"], name=meta["name"],
          rows=meta["rows_kept"], labelled=meta["labelled"],
          features_found=f"{meta['features_found']}/{meta['features_total']}")
    db.commit()
    return meta


@router.delete("/datasets/{ds_id}")
def delete_dataset(ds_id: str, request: Request, admin: User = Depends(admin_only),
                   db=Depends(get_db)):
    r = request.app.state.replay
    if ds_id == "test":
        raise HTTPException(400, "The built-in test split cannot be deleted")
    if ds_id == r.source:
        raise HTTPException(400, "Switch the replay to another source before deleting this one")
    uploads = Path(r.uploads_dir)
    if not (uploads / f"{ds_id}.json").exists():
        raise HTTPException(404, "Dataset not found")
    for ext in (".json", ".parquet"):
        (uploads / f"{ds_id}{ext}").unlink(missing_ok=True)
    audit(db, admin.username, "dataset.delete", ds_id)
    db.commit()
    return {"ok": True}
