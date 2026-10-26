"""Retraining-demo helper: clearly marked, never uses hidden labels, counts toward the
retraining threshold, and can be removed completely."""

from conftest import login


def test_demo_decisions_seed_and_remove(app_client):
    c = app_client
    hadm, ha = login(c, "admin", "admin123"), login(c, "analyst", "analyst123")
    c.app.state.replay.step(100)                       # make sure open alerts exist
    before = c.get("/api/admin/retrain", headers=hadm).json()
    assert before["demo_tools"] is True

    assert c.post("/api/admin/demo/feedback", headers=ha, json={"count": 3}).status_code == 403
    r = c.post("/api/admin/demo/feedback", headers=hadm, json={"count": 3, "verified": True})
    assert r.status_code == 200 and r.json()["created"] == 3

    after = c.get("/api/admin/retrain", headers=hadm).json()
    assert after["usable_feedback"] == before["usable_feedback"] + 3
    assert after["demo_decisions"] == before["demo_decisions"] + 3

    demo_fb = [f for f in c.get("/api/admin/feedback", headers=hadm).json() if f["analyst"] == "demo"]
    assert len(demo_fb) == 3
    for f in demo_fb:
        assert f["verified"] and "Demo decision" in f["reason"]
        # the demo only accepts the model's own prediction - never the hidden label
        expected = "BENIGN" if f["predicted_class"] == "BENIGN" else f["predicted_class"]
        assert f["attack_class"] == expected
        assert c.get(f"/api/alerts/{f['alert_id']}", headers=ha).json()["status"] == "resolved"
    assert any(e["title"].startswith("[demo]") for e in c.get("/api/kr", headers=ha).json())

    removed = c.request("DELETE", "/api/admin/demo/feedback", headers=hadm).json()["removed"]
    assert removed == after["demo_decisions"]
    final = c.get("/api/admin/retrain", headers=hadm).json()
    assert final["demo_decisions"] == 0
    assert final["usable_feedback"] == before["usable_feedback"] - before["demo_decisions"]
    for f in demo_fb:
        assert c.get(f"/api/alerts/{f['alert_id']}", headers=ha).json()["status"] == "open"
    assert not any(e["title"].startswith("[demo]") for e in c.get("/api/kr", headers=ha).json())
