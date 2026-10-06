"""SQLite database (SQLAlchemy 2.0). One file: data/ids.db.

Tables
  users            analysts and admins (simulated login, hashed passwords)
  sessions         login tokens
  model_versions   registry of bundles: candidate / approved / active / retired / rejected
  alerts           flows the model flagged (auto_alert) or referred (review)
  feedback         the analyst's contextual decision on an alert
  kr_entries       Knowledge Repository: verified incidents, searchable + similar-incident retrieval
  retrain_jobs     controlled retraining runs and their evaluation
  traffic_stats    per-batch counters (incl. auto_benign flows, which are not stored as alerts)
  audit_log        who did what, when
"""

import os
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary,
                        String, Text, TypeDecorator, create_engine, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DB_URL = os.environ.get("IDS_DB_URL", "sqlite:///data/ids.db")


def now():
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """SQLite forgets time zones; store UTC and hand it back marked as UTC, so the
    browser does not mistake it for local time."""
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16))           # analyst | admin
    password_hash: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class Session(Base):
    __tablename__ = "sessions"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(32), unique=True)
    path: Mapped[str] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16))  # candidate|approved|active|retired|rejected
    parent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now, index=True)
    # where the flow came from + analyst context (never model inputs)
    flow_day: Mapped[str] = mapped_column(String(16))
    flow_row_id: Mapped[int] = mapped_column(Integer)
    flow_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    src_ip: Mapped[str] = mapped_column(String(64))
    src_port: Mapped[int] = mapped_column(Integer)
    dst_ip: Mapped[str] = mapped_column(String(64))
    dst_port: Mapped[int] = mapped_column(Integer)
    protocol: Mapped[int] = mapped_column(Integer)
    features: Mapped[dict] = mapped_column(JSON)            # raw candidate features (for retraining)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)   # float32[128] (similarity search)
    # model output
    model_version: Mapped[str] = mapped_column(String(32))
    predicted_class: Mapped[str] = mapped_column(String(32), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    entropy: Mapped[float] = mapped_column(Float)
    distance: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(16), index=True)   # review | auto_alert
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    top_classes: Mapped[list] = mapped_column(JSON, default=list)
    second_opinion: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # RF class + confidence
    severity: Mapped[str] = mapped_column(String(8))                # high | medium | low
    # workflow
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open|resolved
    assigned_to: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # EVALUATION ONLY - never returned by analyst endpoints, never used for prediction
    hidden_label: Mapped[str] = mapped_column(String(32))


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), index=True)
    analyst: Mapped[str] = mapped_column(String(64))
    verdict: Mapped[str] = mapped_column(String(16))        # malicious | benign | unsure
    attack_class: Mapped[str] = mapped_column(String(32))   # analyst's label (BENIGN if benign)
    reason: Mapped[str] = mapped_column(Text)
    context: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String(8))      # low | medium | high
    comments: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    used_in_version: Mapped[str | None] = mapped_column(String(32), nullable=True)


class KREntry(Base):
    __tablename__ = "kr_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"))
    feedback_id: Mapped[int] = mapped_column(ForeignKey("feedback.id"))
    title: Mapped[str] = mapped_column(String(200))
    verdict: Mapped[str] = mapped_column(String(16))
    attack_class: Mapped[str] = mapped_column(String(32), index=True)
    predicted_class: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)                 # reason + context + evidence + comments
    tags: Mapped[list] = mapped_column(JSON, default=list)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)
    analyst: Mapped[str] = mapped_column(String(64))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class RetrainJob(Base):
    __tablename__ = "retrain_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_by: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))  # queued|running|evaluated|failed
    base_version: Mapped[str] = mapped_column(String(32))
    candidate_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    n_feedback: Mapped[int] = mapped_column(Integer, default=0)
    criteria: Mapped[dict] = mapped_column(JSON, default=dict)   # fixed BEFORE training
    results: Mapped[dict] = mapped_column(JSON, default=dict)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    log: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class TrafficStat(Base):
    __tablename__ = "traffic_stats"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=now, index=True)
    model_version: Mapped[str] = mapped_column(String(32))
    n_flows: Mapped[int] = mapped_column(Integer)
    n_auto_benign: Mapped[int] = mapped_column(Integer)
    n_auto_alert: Mapped[int] = mapped_column(Integer)
    n_review: Mapped[int] = mapped_column(Integer)
    ms_per_flow: Mapped[float] = mapped_column(Float)
    # evaluation only (hidden labels), for the admin's live-accuracy panel
    n_correct: Mapped[int] = mapped_column(Integer)
    n_missed_attacks: Mapped[int] = mapped_column(Integer)   # true attack, auto_benign


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=now, index=True)
    username: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(128), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)


def make_engine(url: str = DB_URL):
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")   # replay thread writes while API reads
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


engine = make_engine()
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db(eng=None):
    Base.metadata.create_all(eng or engine)


def audit(db, username: str, action: str, target: str = "", **details):
    db.add(AuditLog(username=username, action=action, target=target, details=details))
