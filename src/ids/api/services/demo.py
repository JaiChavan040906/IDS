"""Presentation helper: fill the system with demo analyst decisions in one click, so the
retraining threshold can be shown live without reviewing 20 alerts by hand.

Honesty rules (CLAUDE.md: the hidden label is never used to fill an analyst decision):
  * a demo decision only ACCEPTS THE MODEL'S OWN PREDICTION (benign if the model said
    BENIGN, otherwise malicious with the predicted class); it never reads hidden_label
  * every demo decision is marked: analyst "demo", tag "demo", and a reason that says so
  * "Remove demo decisions" deletes them and reopens their alerts
Can be switched off with `demo_tools: false` in configs/app.yaml.
"""

from ids.api.db import Alert, Feedback, KREntry, audit

DEMO_USER = "demo"
DEMO_REASON = ("Demo decision: auto-generated for the presentation. It accepts the model's "
               "own prediction and is not a real analyst review.")


def seed_feedback(db, count: int, verified: bool, admin: str) -> dict:
    """Create up to `count` demo decisions on open alerts that have no decision yet.
    Review-queue alerts are used first (that is where analysts work), then confident alerts."""
    decided = {a for (a,) in db.query(Feedback.alert_id).all()}
    picked = []
    for decision in ("review", "auto_alert"):
        q = (db.query(Alert).filter(Alert.status == "open", Alert.decision == decision)
             .order_by(Alert.id))
        for a in q:
            if a.id not in decided:
                picked.append(a)
            if len(picked) == count:
                break
        if len(picked) == count:
            break
    if not picked:
        raise ValueError("There are no open alerts without a decision. "
                         "Start the traffic replay for a few seconds first.")

    for a in picked:
        benign = a.predicted_class == "BENIGN"
        verdict, label = ("benign", "BENIGN") if benign else ("malicious", a.predicted_class)
        fb = Feedback(alert_id=a.id, analyst=DEMO_USER, verdict=verdict, attack_class=label,
                      reason=DEMO_REASON, context="", evidence="", confidence="medium",
                      comments="", verified=verified, verified_by=admin if verified else None)
        db.add(fb)
        db.flush()
        db.add(KREntry(alert_id=a.id, feedback_id=fb.id, analyst=DEMO_USER, verdict=verdict,
                       attack_class=label, predicted_class=a.predicted_class,
                       title=f"[demo] {label}: {a.src_ip} -> {a.dst_ip}:{a.dst_port} "
                             f"(model said {a.predicted_class})",
                       text=DEMO_REASON, tags=["demo"], embedding=a.embedding, verified=verified))
        a.status = "resolved"
        a.assigned_to = a.assigned_to or DEMO_USER
    audit(db, admin, "demo.seed", f"{len(picked)} decisions", verified=verified)
    db.commit()
    return {"created": len(picked), "requested": count, "verified": verified}


def remove_demo(db, admin: str) -> dict:
    """Delete every demo decision and its Knowledge Repository entry; reopen the alerts."""
    fbs = db.query(Feedback).filter(Feedback.analyst == DEMO_USER).all()
    for fb in fbs:
        db.query(KREntry).filter(KREntry.feedback_id == fb.id).delete()
        a = db.get(Alert, fb.alert_id)
        if a is not None:
            a.status = "open"
            if a.assigned_to == DEMO_USER:
                a.assigned_to = None
        db.delete(fb)
    audit(db, admin, "demo.remove", f"{len(fbs)} decisions")
    db.commit()
    return {"removed": len(fbs)}


def count_demo(db) -> int:
    return db.query(Feedback).filter(Feedback.analyst == DEMO_USER).count()
