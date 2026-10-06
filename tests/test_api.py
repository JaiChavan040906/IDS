"""End-to-end API scenario: replay -> alerts -> analyst feedback -> KR -> admin
verification -> retraining -> approve/deploy -> rollback, plus access rules."""

import json
import time

from conftest import login


def analyst_payloads(client, h):
    """Every analyst-facing response we can reach, as text (for leak checks)."""
    out = [client.get("/api/alerts", params={"status": "all"}, headers=h).text]
    for a in client.get("/api/alerts", params={"status": "all"}, headers=h).json()["items"][:5]:
        out.append(client.get(f"/api/alerts/{a['id']}", headers=h).text)
    out.append(client.get("/api/kr", headers=h).text)
    return out


def test_login_and_roles(app_client):
    c = app_client
    assert c.post("/api/auth/login", json={"username": "analyst", "password": "nope"}).status_code == 401
    assert c.get("/api/alerts").status_code == 401
    ha = login(c, "analyst", "analyst123")
    assert c.get("/api/auth/me", headers=ha).json()["role"] == "analyst"
    assert c.get("/api/admin/users", headers=ha).status_code == 403
    hadm = login(c, "admin", "admin123")
    assert c.get("/api/admin/users", headers=hadm).status_code == 200
    assert c.get("/api/public/summary").json()["model_version"] == "v1"


def test_full_hitl_scenario(app_client):
    c = app_client
    ha, hadm = login(c, "analyst", "analyst123"), login(c, "admin", "admin123")
    replay = c.app.state.replay

    # 1. replay traffic (stepped directly for determinism)
    for _ in range(6):
        replay.step(50)
    alerts = c.get("/api/alerts", params={"status": "all", "limit": 500}, headers=ha).json()
    assert alerts["total"] > 0
    ov = c.get("/api/stats/overview", headers=ha).json()
    assert ov["flows"] == 300 and ov["auto_benign"] + ov["auto_alert"] + ov["review"] == 300

    # 2. the hidden label must never reach the analyst
    for text in analyst_payloads(c, ha):
        assert "hidden_label" not in text

    # 3. analyst decisions -> feedback + KR entries
    items = alerts["items"]
    classes = c.get("/api/meta", headers=ha).json()["classes"]
    decisions = [("malicious", "DDoS"), ("benign", "BENIGN"), ("malicious", "Portscan"),
                 ("benign", "BENIGN"), ("malicious", "DoS Hulk"), ("unsure", "UNKNOWN_ATTACK")]
    for a, (verdict, cls) in zip(items, decisions):
        assert cls in classes + ["UNKNOWN_ATTACK"]
        r = c.post(f"/api/alerts/{a['id']}/feedback", headers=ha, json={
            "verdict": verdict, "attack_class": cls, "reason": "test decision",
            "context": "scenario test", "evidence": "none", "confidence": "high", "tags": ["test"]})
        assert r.status_code == 200, r.text
    bad = c.post(f"/api/alerts/{items[7]['id']}/feedback", headers=ha, json={
        "verdict": "malicious", "attack_class": "NotAClass", "reason": "x" * 5, "confidence": "low"})
    assert bad.status_code == 422
    assert len(c.get("/api/kr", headers=ha).json()) == 6

    # similar incidents come back for a new alert
    detail = c.get(f"/api/alerts/{items[10]['id']}", headers=ha).json()
    assert detail["similar_incidents"] and "similarity" in detail["similar_incidents"][0]
    assert len(detail["evidence"]) == 6
    assert detail["second_opinion"] and "class" in detail["second_opinion"]

    # 4. retraining is refused until enough feedback is VERIFIED
    assert c.post("/api/admin/retrain", headers=hadm).status_code == 400
    fb = c.get("/api/admin/feedback", params={"verified": False}, headers=hadm).json()
    for f in fb:
        if f["verdict"] != "unsure":
            assert c.post(f"/api/admin/feedback/{f['id']}/verify", headers=hadm,
                          json={"verified": True}).status_code == 200
    info = c.get("/api/admin/retrain", headers=hadm).json()
    assert info["usable_feedback"] == 5          # unsure / unknown excluded

    # 5. retrain -> candidate with fixed criteria
    job = c.post("/api/admin/retrain", headers=hadm).json()
    assert job["criteria"]["max_macro_f1_drop"] == 0.005
    for _ in range(600):
        job = c.get(f"/api/admin/retrain/{job['id']}", headers=hadm).json()
        if job["status"] in ("evaluated", "failed"):
            break
        time.sleep(1)
    assert job["status"] == "evaluated", job["log"]
    cand = job["candidate_version"]
    from pathlib import Path
    assert (Path(c.app.state.cfg["bundle_dir"]) / cand / "second_opinion.joblib").exists()
    assert set(job["results"]["checks"]) == {"macro_f1_drop", "fpr_increase", "feedback_accuracy_gain"}

    # 6. approve (force-pass for the test if the random model failed), deploy, rollback
    from ids.api.db import ModelVersion, SessionLocal
    db = SessionLocal()
    mv = db.query(ModelVersion).filter_by(version=cand).one()
    mv.metrics = {**mv.metrics, "passed": True}
    db.commit()
    db.close()
    assert c.post(f"/api/admin/models/{cand}/deploy", headers=hadm, json={}).status_code == 400
    assert c.post(f"/api/admin/models/{cand}/approve", headers=hadm, json={"note": "ok"}).status_code == 200
    assert c.post(f"/api/admin/models/{cand}/deploy", headers=hadm, json={}).status_code == 200
    assert c.app.state.models.version == cand
    used = c.get("/api/admin/feedback", params={"verified": True}, headers=hadm).json()
    assert any(f["used_in_version"] == cand for f in used)
    replay.step(20)                                   # new model scores traffic
    assert c.post("/api/admin/models/rollback", headers=hadm, json={"note": "test"}).status_code == 200
    assert c.app.state.models.version == "v1"

    # 7. everything important was audited
    actions = {a["action"] for a in c.get("/api/admin/audit", headers=hadm).json()}
    assert {"feedback.create", "feedback.verify", "retrain.create", "model.approve",
            "model.deploy", "model.rollback"} <= actions

    # 8. admin evaluation uses hidden labels (admin only)
    ev = c.get("/api/admin/evaluation", headers=hadm).json()
    assert ev["analyst_vs_truth"]["decisive_feedback"] == 5
    assert c.get("/api/admin/evaluation", headers=ha).status_code == 403


def test_user_management(app_client):
    c = app_client
    hadm = login(c, "admin", "admin123")
    r = c.post("/api/admin/users", headers=hadm, json={
        "username": "newbie", "full_name": "New Analyst", "role": "analyst", "password": "secret1"})
    assert r.status_code == 200
    uid = r.json()["id"]
    assert login(c, "newbie", "secret1")
    assert c.patch(f"/api/admin/users/{uid}", headers=hadm, json={"active": False}).status_code == 200
    assert c.post("/api/auth/login", json={"username": "newbie", "password": "secret1"}).status_code == 401
    me = c.get("/api/auth/me", headers=hadm).json()
    assert c.patch(f"/api/admin/users/{me['id']}", headers=hadm, json={"active": False}).status_code == 400
    json.dumps(c.get("/api/admin/health", headers=hadm).json())
