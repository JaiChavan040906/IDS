"""Data warehouse (DWM Module 1): ETL full + incremental loads and OLAP queries,
on a tiny synthetic dataset and a throwaway portal database."""

import sqlite3
from datetime import datetime

import pandas as pd
from sqlalchemy.orm import sessionmaker

from conftest import login
from ids import olap
from ids.api.db import Alert, Base, Feedback, ModelVersion, User, make_engine
from ids.warehouse import FLOW_COLS, full_load, incremental_load

SEVERITY = {"high": ["DoS Hulk"], "medium": ["Portscan"]}


def _flows():
    rows = [  # (row_id, day, port, proto, duration_us, fwd, bwd, fwd_bytes, bwd_bytes, label, ts)
        (1, "monday", 80, 6, 1500, 3, 2, 300, 200, "BENIGN", "2017-07-03 09:00:01"),
        (2, "monday", 53, 17, 100, 1, 1, 60, 90, "BENIGN", "2017-07-03 09:00:30"),
        (3, "wednesday", 80, 6, 9000, 10, 0, 0, 0, "DoS Hulk", "2017-07-05 14:10:00"),
        (4, "wednesday", 80, 6, 8000, 8, 0, 0, 0, "DoS Hulk", "2017-07-05 14:40:00"),
        (5, "wednesday", 443, 6, 50, 2, 2, 100, 100, "BENIGN", "2017-07-05 18:00:00"),
        (6, "friday", 22, 6, 70, 1, 1, 40, 40, "Portscan", "2017-07-07 13:00:00"),
    ]
    df = pd.DataFrame([r[:-1] for r in rows], columns=FLOW_COLS)
    df["split_key"] = [1, 1, 1, 2, 3, 3]
    ts = pd.DataFrame({"row_id": [r[0] for r in rows], "day": [r[1] for r in rows],
                       "Timestamp": [r[-1] for r in rows]})
    return df, ts


def _portal(path):
    eng = make_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(eng)
    db = sessionmaker(eng)()
    db.add(ModelVersion(version="v1", path="x", status="active"))
    db.add(User(username="analyst", full_name="Asha Analyst", role="analyst", password_hash="x"))
    db.commit()
    return eng, db


def _alert(db, decision="review", cls="DoS Hulk"):
    a = Alert(flow_day="wednesday", flow_row_id=3, flow_time=datetime(2017, 7, 5, 14, 10),
              src_ip="1.1.1.1", src_port=1, dst_ip="2.2.2.2", dst_port=80, protocol=6, features={},
              embedding=b"", model_version="v1", predicted_class=cls, confidence=0.6, entropy=0.1,
              distance=1.0, decision=decision, severity="high", hidden_label="DoS Hulk")
    db.add(a)
    db.commit()
    return a


def test_full_and_incremental_load(tmp_path):
    eng, db = _portal(tmp_path / "ids.db")
    a1 = _alert(db)
    _alert(db, decision="auto_alert")
    db.add(Feedback(alert_id=a1.id, analyst="analyst", verdict="malicious", attack_class="DoS Hulk",
                    reason="r", confidence="high"))
    db.commit()
    wh = str(tmp_path / "wh.db")
    flows, ts = _flows()
    steps = full_load(wh, "", "", str(tmp_path / "ids.db"), SEVERITY, flows=flows, timestamps=ts)
    assert [s["phase"] for s in steps][:3] == ["extract"] * 3

    conn = sqlite3.connect(wh)
    count = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: E731
    assert count("fact_flow") == 6 and count("fact_alert") == 2 and count("fact_review") == 1
    # every flow kept its timestamp and bytes were derived
    assert conn.execute("SELECT COUNT(*) FROM fact_flow WHERE time_key = 0").fetchone()[0] == 0
    assert conn.execute("SELECT total_bytes, duration_ms FROM fact_flow WHERE source_row = 1").fetchone() == (500, 1.5)
    # snowflake and star agree; the aggregate holds the same totals as the base fact table
    assert conn.execute("SELECT SUM(flows) FROM agg_flow_hour").fetchone()[0] == 6
    assert count("dim_category") == 9 and count("dim_date") == 3
    conn.close()

    # OLAP: per-day x category totals, roll-up equals the sum of the drill-down
    r = olap.run_query(wh, "flows", "flows", {"dim": "time", "level": "day"}, {"dim": "attack", "level": "nature"})
    assert r["used_aggregate"] and sum(sum(v or 0 for v in row) for row in r["cells"]) == 6
    base = olap.run_query(wh, "flows", "flows", {"dim": "time", "level": "day"}, {"dim": "attack", "level": "nature"},
                          use_aggregate=False)
    assert base["source"] == "fact_flow" and base["cells"] == r["cells"]
    dice = olap.run_query(wh, "flows", "bytes", {"dim": "attack", "level": "attack_class"}, None,
                          [{"dim": "time", "level": "day", "values": ["Wed 05 Jul 2017"]},
                           {"dim": "service", "level": "service", "values": ["HTTPS"]}])
    assert dice["rows"] == ["BENIGN"] and dice["cells"] == [[200]] and not dice["used_aggregate"]
    assert "?" in dice["sql"] and "HTTPS" not in dice["sql"]   # values are parameters
    assert olap.compare(wh, "aggregate")["same_answer"] and olap.compare(wh, "snowflake")["same_answer"]
    fl = olap.factless(wh)
    assert fl["sent_to_review"] == 1 and fl["unreviewed"] == 0 and "Portscan" in fl["not_seen_monday"]

    # incremental: only the new alert is appended
    _alert(db, cls="Portscan")
    steps = incremental_load(wh, str(tmp_path / "ids.db"))
    assert any(s["name"] == "Extract new alerts" and s["rows"] == 1 for s in steps)
    assert olap.run_query(wh, "alerts", "alerts", {"dim": "route", "level": "route"})["cells"] == [[1], [2]]  # auto, review

    # portal reset: alerts removed -> detected, portal facts reloaded from scratch
    db.query(Feedback).delete()
    db.query(Alert).delete()
    db.commit()
    _alert(db)
    steps = incremental_load(wh, str(tmp_path / "ids.db"))
    assert any(s["name"] == "Detect change" for s in steps)
    conn = sqlite3.connect(wh)
    assert conn.execute("SELECT COUNT(*) FROM fact_alert").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM fact_review").fetchone()[0] == 0
    conn.close()
    db.close()
    eng.dispose()


def test_olap_rejects_unknown_names(tmp_path):
    import pytest
    with pytest.raises(olap.QueryError):
        olap.build_query("flows", "flows", {"dim": "time; DROP TABLE x", "level": "day"}, None, [])
    with pytest.raises(olap.QueryError):
        olap.build_query("flows", "flows", {"dim": "time", "level": "day"}, {"dim": "time", "level": "hour"}, [])


def test_warehouse_api_roles(app_client):
    c = app_client
    ha, hadm = login(c, "analyst", "analyst123"), login(c, "admin", "admin123")
    assert c.get("/api/dw/meta", headers=ha).status_code == 200
    assert c.get("/api/dw/overview", headers=ha).json()["built"] is False
    assert c.post("/api/dw/olap", headers=ha, json={"rows": {"dim": "time", "level": "day"}}).status_code == 404
    assert c.post("/api/dw/etl", headers=ha, json={"mode": "full"}).status_code == 403
    assert c.get("/api/dw/meta").status_code == 401
    assert c.get("/api/dw/overview", headers=hadm).status_code == 200


def test_warehouse_switched_off(app_client):
    """Practicals without the warehouse: tab, API and audit entries all disappear."""
    c = app_client
    hadm = login(c, "admin", "admin123")
    from ids.api.db import SessionLocal, audit
    db = SessionLocal()
    audit(db, "admin", "warehouse.etl", "full")
    db.commit()
    db.close()
    state = c.app.state
    assert c.get("/api/health").json()["features"]["warehouse"] is True
    try:
        state.warehouse_enabled = False
        assert c.get("/api/health").json()["features"]["warehouse"] is False
        assert c.get("/api/dw/meta", headers=hadm).status_code == 404
        assert c.get("/api/dw/meta").status_code == 404                     # no hint it exists
        assert c.post("/api/dw/etl", headers=hadm, json={"mode": "full"}).status_code == 404
        actions = [a["action"] for a in c.get("/api/admin/audit", headers=hadm).json()]
        assert not any(a.startswith("warehouse.") for a in actions)
    finally:
        state.warehouse_enabled = True
    actions = [a["action"] for a in c.get("/api/admin/audit", headers=hadm).json()]
    assert "warehouse.etl" in actions                                       # hidden, never deleted


def test_admin_warehouse_switch(app_client):
    """The On/Off switch on Admin -> Overview: admin only, takes effect immediately."""
    c = app_client
    ha, hadm = login(c, "analyst", "analyst123"), login(c, "admin", "admin123")
    assert c.post("/api/admin/features", headers=ha, json={"warehouse": False}).status_code == 403
    try:
        r = c.post("/api/admin/features", headers=hadm, json={"warehouse": False})
        assert r.status_code == 200 and r.json()["features"]["warehouse"] is False
        assert c.get("/api/health").json()["features"]["warehouse"] is False
        assert c.get("/api/dw/meta", headers=hadm).status_code == 404
        r = c.post("/api/admin/features", headers=hadm, json={"warehouse": True})
        assert r.json()["features"]["warehouse"] is True
        assert c.get("/api/dw/meta", headers=hadm).status_code == 200
    finally:
        c.app.state.warehouse_enabled = True


def test_cube_view(tmp_path):
    """3-D cube data: totals match the flows; a filter on an axis is highlighted, not applied."""
    flows, ts = _flows()
    wh = str(tmp_path / "wh.db")
    full_load(wh, "", "", str(tmp_path / "none.db"), SEVERITY, flows=flows, timestamps=ts)
    x, y, z = ({"dim": "attack", "level": "nature"}, {"dim": "time", "level": "day"},
               {"dim": "protocol", "level": "protocol"})
    r = olap.run_cube(wh, "flows", "flows", x, y, z)
    assert r["source"] == "agg_flow_hour"                       # aggregate navigator covers protocol too
    assert sum(c[3] for c in r["cells"]) == 6
    assert [a["members"] for a in r["axes"]][2] == ["TCP", "UDP"]
    lit = olap.run_cube(wh, "flows", "flows", x, y, z,
                        [{"dim": "time", "level": "day", "values": ["Wed 05 Jul 2017"]}])
    assert lit["highlight"] == {"1": ["Wed 05 Jul 2017"]} and sum(c[3] for c in lit["cells"]) == 6
    applied = olap.run_cube(wh, "flows", "flows", x, y, z,
                            [{"dim": "service", "level": "service", "values": ["HTTP"]}])
    assert sum(c[3] for c in applied["cells"]) == 3 and applied["highlight"] == {}
    base = olap.run_query(wh, "flows", "flows", {"dim": "time", "level": "day"},
                          {"dim": "protocol", "level": "protocol"}, use_aggregate=False)
    agg = olap.run_query(wh, "flows", "flows", {"dim": "time", "level": "day"},
                         {"dim": "protocol", "level": "protocol"})
    assert agg["used_aggregate"] and agg["cells"] == base["cells"] and agg["cols"] == base["cols"]
