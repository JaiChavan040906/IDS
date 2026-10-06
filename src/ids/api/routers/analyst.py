"""Analyst endpoints: alert queue, alert detail, contextual feedback, KR, dashboard stats.

The hidden (true) label is NEVER included in any response from this router.
"""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func

from ids.api.db import Alert, Feedback, KREntry, TrafficStat, User, audit
from ids.api.security import analyst_or_admin, get_db

router = APIRouter(prefix="/api", tags=["analyst"])


def alert_out(a: Alert, full: bool = False) -> dict:
    d = {"id": a.id, "created_at": a.created_at, "flow_time": a.flow_time,
         "src_ip": a.src_ip, "src_port": a.src_port, "dst_ip": a.dst_ip, "dst_port": a.dst_port,
         "protocol": a.protocol, "predicted_class": a.predicted_class,
         "confidence": a.confidence, "entropy": a.entropy, "distance": a.distance,
         "decision": a.decision, "severity": a.severity, "status": a.status,
         "assigned_to": a.assigned_to, "model_version": a.model_version, "reasons": a.reasons}
    if full:
        d.update(top_classes=a.top_classes, features=a.features, flow_day=a.flow_day,
                 flow_row_id=a.flow_row_id, second_opinion=a.second_opinion)
    return d


def feedback_out(f: Feedback) -> dict:
    return {k: getattr(f, k) for k in (
        "id", "alert_id", "analyst", "verdict", "attack_class", "reason", "context", "evidence",
        "confidence", "comments", "created_at", "verified", "verified_by", "used_in_version")}


def kr_out(e: KREntry, similarity: float | None = None) -> dict:
    d = {k: getattr(e, k) for k in ("id", "alert_id", "feedback_id", "title", "verdict",
                                    "attack_class", "predicted_class", "text", "tags",
                                    "analyst", "verified", "created_at")}
    if similarity is not None:
        d["similarity"] = round(similarity, 4)
    return d


@router.get("/alerts")
def list_alerts(decision: str | None = None, status: str | None = "open",
                predicted_class: str | None = None, severity: str | None = None,
                q: str | None = None, limit: int = 100, offset: int = 0,
                user: User = Depends(analyst_or_admin), db=Depends(get_db)):
    query = db.query(Alert)
    if decision:
        query = query.filter(Alert.decision == decision)
    if status and status != "all":
        query = query.filter(Alert.status == status)
    if predicted_class:
        query = query.filter(Alert.predicted_class == predicted_class)
    if severity:
        query = query.filter(Alert.severity == severity)
    if q:
        query = query.filter((Alert.src_ip.contains(q)) | (Alert.dst_ip.contains(q)))
    total = query.count()
    rows = query.order_by(Alert.id.desc()).offset(offset).limit(min(limit, 500)).all()
    return {"total": total, "items": [alert_out(a) for a in rows]}


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: int, request: Request, user: User = Depends(analyst_or_admin),
              db=Depends(get_db)):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    st = request.app.state
    similar = st.kr.similar(db, a.features, k=5, exclude_alert=a.id)
    fb = db.query(Feedback).filter_by(alert_id=a.id).order_by(Feedback.id).all()
    return {**alert_out(a, full=True),
            "evidence": st.models.evidence(a.features),
            "similar_incidents": [kr_out(e, s) for e, s in similar],
            "feedback": [feedback_out(f) for f in fb]}


@router.post("/alerts/{alert_id}/claim")
def claim(alert_id: int, user: User = Depends(analyst_or_admin), db=Depends(get_db)):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    a.assigned_to = user.username
    audit(db, user.username, "alert.claim", f"alert:{a.id}")
    db.commit()
    return alert_out(a)


class FeedbackIn(BaseModel):
    verdict: Literal["malicious", "benign", "unsure"]
    attack_class: str = Field(description="Model class, BENIGN, or UNKNOWN_ATTACK")
    reason: str = Field(min_length=3)
    context: str = ""
    evidence: str = ""
    confidence: Literal["low", "medium", "high"]
    comments: str = ""
    tags: list[str] = []


@router.post("/alerts/{alert_id}/feedback")
def give_feedback(alert_id: int, body: FeedbackIn, request: Request,
                  user: User = Depends(analyst_or_admin), db=Depends(get_db)):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "Alert not found")
    classes = request.app.state.models.detector.enc.classes
    label = "BENIGN" if body.verdict == "benign" else body.attack_class
    if body.verdict == "malicious" and label not in [*classes, "UNKNOWN_ATTACK"]:
        raise HTTPException(422, f"attack_class must be one of {classes} or UNKNOWN_ATTACK")
    if body.verdict == "malicious" and label == "BENIGN":
        raise HTTPException(422, "A malicious verdict needs an attack class")

    fb = Feedback(alert_id=a.id, analyst=user.username, verdict=body.verdict,
                  attack_class=label, reason=body.reason, context=body.context,
                  evidence=body.evidence, confidence=body.confidence, comments=body.comments)
    db.add(fb)
    db.flush()
    text = "\n".join(x for x in (body.reason, body.context, body.evidence, body.comments) if x)
    db.add(KREntry(
        alert_id=a.id, feedback_id=fb.id, analyst=user.username, verdict=body.verdict,
        attack_class=label, predicted_class=a.predicted_class,
        title=f"{label if body.verdict != 'unsure' else 'Unresolved'}: {a.src_ip} -> "
              f"{a.dst_ip}:{a.dst_port} (model said {a.predicted_class})",
        text=text, tags=body.tags, embedding=a.embedding))
    a.status = "resolved"
    a.assigned_to = a.assigned_to or user.username
    audit(db, user.username, "feedback.create", f"alert:{a.id}", verdict=body.verdict,
          label=label, model_said=a.predicted_class)
    db.commit()
    return feedback_out(fb)


@router.get("/kr")
def kr_search(q: str = "", attack_class: str | None = None, verdict: str | None = None,
              verified: bool | None = None, request: Request = None,
              user: User = Depends(analyst_or_admin), db=Depends(get_db)):
    rows = request.app.state.kr.search(db, q, attack_class, verdict, verified)
    return [kr_out(e) for e in rows]


@router.get("/kr/{entry_id}")
def kr_entry(entry_id: int, request: Request, user: User = Depends(analyst_or_admin),
             db=Depends(get_db)):
    e = db.get(KREntry, entry_id)
    if not e:
        raise HTTPException(404, "Entry not found")
    a = db.get(Alert, e.alert_id)
    similar = request.app.state.kr.similar(db, a.features, k=5, exclude_alert=a.id)
    return {**kr_out(e), "alert": alert_out(a, full=True),
            "feedback": feedback_out(db.get(Feedback, e.feedback_id)),
            "similar_incidents": [kr_out(x, s) for x, s in similar]}


@router.get("/stats/overview")
def overview(minutes: int = 60, user: User = Depends(analyst_or_admin), db=Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    t = db.query(func.sum(TrafficStat.n_flows), func.sum(TrafficStat.n_auto_benign),
                 func.sum(TrafficStat.n_auto_alert), func.sum(TrafficStat.n_review),
                 func.avg(TrafficStat.ms_per_flow)).filter(TrafficStat.ts >= since).one()
    by_class = (db.query(Alert.predicted_class, func.count()).filter(Alert.created_at >= since)
                .group_by(Alert.predicted_class).all())
    queue = (db.query(Alert.decision, Alert.severity, func.count())
             .filter(Alert.status == "open").group_by(Alert.decision, Alert.severity).all())
    timeline = (db.query(TrafficStat.ts, TrafficStat.n_flows, TrafficStat.n_auto_alert,
                         TrafficStat.n_review).filter(TrafficStat.ts >= since)
                .order_by(TrafficStat.ts).all())
    # bucket the timeline into at most 60 points
    step = max(1, len(timeline) // 60)
    points = []
    for i in range(0, len(timeline), step):
        chunk = timeline[i:i + step]
        points.append({"ts": chunk[-1][0], "flows": sum(c[1] for c in chunk),
                       "alerts": sum(c[2] for c in chunk), "review": sum(c[3] for c in chunk)})
    return {
        "window_minutes": minutes,
        "flows": t[0] or 0, "auto_benign": t[1] or 0, "auto_alert": t[2] or 0,
        "review": t[3] or 0, "ms_per_flow": round(t[4] or 0, 4),
        "alerts_by_class": {c: n for c, n in by_class},
        "open_queue": [{"decision": d, "severity": s, "count": n} for d, s, n in queue],
        "reviewed_total": db.query(Feedback).count(),
        "kr_total": db.query(KREntry).count(),
        "timeline": points,
    }


@router.get("/meta")
def meta(request: Request, user: User = Depends(analyst_or_admin)):
    det = request.app.state.models.detector
    return {"classes": det.enc.classes, "model_version": det.version,
            "thresholds": det.thresholds}
