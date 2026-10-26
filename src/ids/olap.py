"""OLAP queries on the warehouse (DWM Module 1).

A cube = one fact table + the dimensions around it. Each dimension has a hierarchy of
levels (e.g. Time: day -> part of day -> hour -> minute). The UI's OLAP operations map to
the query like this:
  roll-up / drill-down  move a dimension up / down its hierarchy (coarser / finer GROUP BY)
  slice                 fix ONE dimension to one value            (WHERE dim = v)
  dice                  restrict TWO OR MORE dimensions           (WHERE d1 IN .. AND d2 IN ..)
  pivot                 swap the row and column dimensions of the result grid

Every query is built only from the names below (never from raw user text) and values
are passed as SQL parameters.
"""

import json
import sqlite3
import time
from pathlib import Path

TIME = {"label": "Time", "table": "dim_time", "alias": "t", "key": "time_key",
        "levels": [("day", "Day", "t.day_label", "t.time_key"),
                   ("part_of_day", "Part of day", "t.pod_label", "t.time_key"),
                   ("hour", "Hour", "t.hour_label", "t.time_key"),
                   ("minute", "Minute", "t.minute_label", "t.time_key")]}

CUBES = {
    "flows": {
        "label": "Network flows",
        "fact": "fact_flow",
        "grain": "one network flow",
        "about": "All 1.7 million cleaned flows of Improved CIC-IDS2017 (train + validation + test), "
                 "with the dataset's true label.",
        "measures": {
            "flows": ("Flows", "COUNT(*)"),
            "packets": ("Packets", "SUM(f.total_packets)"),
            "bytes": ("Bytes", "SUM(f.total_bytes)"),
            "avg_duration_ms": ("Avg duration (ms)", "ROUND(AVG(f.duration_ms), 2)"),
            "avg_bytes": ("Avg bytes per flow", "ROUND(AVG(f.total_bytes), 1)"),
        },
        "dims": {
            "time": TIME,
            "attack": {"label": "Attack", "table": "dim_attack", "alias": "a", "key": "attack_key",
                       "levels": [("nature", "Benign / malicious", "a.nature", "a.nature"),
                                  ("category", "Category", "a.category", "a.category"),
                                  ("attack_class", "Attack class", "a.attack_class", "a.attack_key")]},
            "service": {"label": "Service", "table": "dim_service", "alias": "s", "key": "service_key",
                        "levels": [("port_range", "Port range", "s.port_range", "s.port_range_order"),
                                   ("service", "Service", "s.service", "s.service"),
                                   ("dst_port", "Destination port", "CAST(s.dst_port AS TEXT)", "s.dst_port")]},
            "protocol": {"label": "Protocol", "table": "dim_protocol", "alias": "p", "key": "protocol_key",
                         "levels": [("protocol", "Protocol", "p.protocol_name", "p.protocol_number")]},
            "split": {"label": "Dataset split", "table": "dim_split", "alias": "d", "key": "split_key",
                      "levels": [("split", "Split", "d.split_name", "d.split_key")]},
        },
        # Aggregate navigator: questions that only need time (down to the hour), attack,
        # protocol and split are answered from the pre-summed agg_flow_hour instead of 1.7M flows.
        "aggregate": {
            "fact": "agg_flow_hour",
            "measures": {
                "flows": "SUM(f.flows)", "packets": "SUM(f.total_packets)", "bytes": "SUM(f.total_bytes)",
                "avg_duration_ms": "ROUND(SUM(f.total_duration_ms) / SUM(f.flows), 2)",
                "avg_bytes": "ROUND(1.0 * SUM(f.total_bytes) / SUM(f.flows), 1)",
            },
            "dims": {
                "time": {"label": "Time", "table": "dim_hour", "alias": "t", "key": "hour_key",
                         "levels": [("day", "Day", "t.day_label", "t.hour_key"),
                                    ("part_of_day", "Part of day", "t.pod_label", "t.hour_key"),
                                    ("hour", "Hour", "t.hour_label", "t.hour_key")]},
                "attack": None,   # same as the base cube
                "protocol": None,
                "split": None,
            },
        },
    },
    "alerts": {
        "label": "Portal alerts",
        "fact": "fact_alert",
        "grain": "one alert raised or referred by the model in the portal",
        "about": "Alerts the portal created during traffic replay (auto alerts and flows sent to "
                 "an analyst). Attack = the MODEL's predicted class. Load new ones with an "
                 "incremental ETL run.",
        "measures": {
            "alerts": ("Alerts", "COUNT(*)"),
            "avg_confidence": ("Avg model confidence", "ROUND(AVG(f.confidence), 4)"),
            "avg_entropy": ("Avg uncertainty (entropy)", "ROUND(AVG(f.entropy), 5)"),
        },
        "dims": {
            "time": TIME,
            "attack": {"label": "Predicted attack", "table": "dim_attack", "alias": "a", "key": "attack_key",
                       "levels": [("nature", "Benign / malicious", "a.nature", "a.nature"),
                                  ("category", "Category", "a.category", "a.category"),
                                  ("attack_class", "Attack class", "a.attack_class", "a.attack_key")]},
            "route": {"label": "Route", "table": "dim_route", "alias": "r", "key": "route_key",
                      "levels": [("route", "Route", "r.route_label", "r.route_key")]},
            "model": {"label": "Model version", "table": "dim_model", "alias": "m", "key": "model_key",
                      "levels": [("version", "Version", "m.version", "m.model_key")]},
            "severity": {"label": "Severity", "table": None, "alias": "f",
                         "levels": [("severity", "Severity", "f.severity", "f.severity")]},
            "source": {"label": "Traffic source", "table": None, "alias": "f",
                       "levels": [("source", "Source", "f.source", "f.source")]},
        },
    },
}

MAX_ROWS = 400
MAX_COLS = 14


class QueryError(ValueError):
    pass


def connect(wh_path: str):
    if not Path(wh_path).exists():
        raise FileNotFoundError("The warehouse has not been built yet. Run the ETL job first.")
    return sqlite3.connect(f"file:{Path(wh_path).as_posix()}?mode=ro", uri=True, timeout=30)


def meta() -> dict:
    """Cube definitions for the UI (also the information package)."""
    return {name: {"label": c["label"], "fact": c["fact"], "grain": c["grain"], "about": c["about"],
                   "measures": [{"id": k, "label": v[0], "sql": v[1]} for k, v in c["measures"].items()],
                   "dims": [{"id": d, "label": dim["label"], "table": dim["table"] or "(on the fact table)",
                             "levels": [{"id": l[0], "label": l[1]} for l in dim["levels"]]}
                            for d, dim in c["dims"].items()]}
            for name, c in CUBES.items()}


def _level(cube: dict, dim: str, level: str):
    d = cube["dims"].get(dim)
    if not d:
        raise QueryError(f"Unknown dimension: {dim}")
    for lid, label, expr, order in d["levels"]:
        if lid == level:
            return d, label, expr, order
    raise QueryError(f"Unknown level {level} for {dim}")


def _join(cube: dict, dim: str) -> str:
    d = cube["dims"][dim]
    if d["table"] is None:
        return ""
    return f"JOIN {d['table']} {d['alias']} ON {d['alias']}.{d['key']} = f.{d['key']}"


def _aggregate_view(cube: dict, axes: list[dict]):
    """The aggregate table as a cube, if every axis can be answered from it (else None)."""
    agg = cube.get("aggregate")
    if not agg:
        return None
    for ax in axes:
        d = agg["dims"].get(ax["dim"], False)
        if d is False:
            return None
        if d and ax["level"] not in {lv[0] for lv in d["levels"]}:
            return None
    dims = {k: (v or cube["dims"][k]) for k, v in agg["dims"].items()}
    return {"fact": agg["fact"], "dims": dims,
            "measures": {k: (cube["measures"][k][0], v) for k, v in agg["measures"].items()}}


def build_query(cube_id: str, measure: str, rows: dict, cols: dict | None, filters: list[dict],
                use_aggregate: bool = True):
    cube = CUBES.get(cube_id)
    if not cube:
        raise QueryError(f"Unknown cube: {cube_id}")
    if measure not in cube["measures"]:
        raise QueryError(f"Unknown measure: {measure}")
    axes = [rows, *([cols] if cols else []), *[f for f in filters or [] if f.get("values")]]
    for ax in axes:
        _level(cube, ax["dim"], ax["level"])        # validate against the base cube
    agg = _aggregate_view(cube, axes) if use_aggregate else None
    if agg:
        cube = agg
    _, _, rexpr, rorder = _level(cube, rows["dim"], rows["level"])
    select = [f"{rexpr} AS row_member"]
    group = ["row_member"]
    order = [f"MIN({rorder})"]
    dims = [rows["dim"]]
    if cols:
        if cols["dim"] == rows["dim"]:
            raise QueryError("Rows and columns must use different dimensions")
        _, _, cexpr, corder = _level(cube, cols["dim"], cols["level"])
        select.append(f"{cexpr} AS col_member")
        select.append(f"MIN({corder}) AS col_order")
        group.append("col_member")
        order.append(f"MIN({corder})")
        dims.append(cols["dim"])
    where, params = [], []
    for flt in filters or []:
        values = [str(v) for v in flt.get("values", [])][:200]
        if not values:
            continue
        _, _, fexpr, _ = _level(cube, flt["dim"], flt["level"])
        where.append(f"{fexpr} IN ({', '.join('?' * len(values))})")
        params += values
        dims.append(flt["dim"])
    select.append(f"{cube['measures'][measure][1]} AS value")
    joins = [j for j in dict.fromkeys(_join(cube, d) for d in dims) if j]
    sql = "SELECT " + ",\n       ".join(select) + f"\nFROM {cube['fact']} f"
    if joins:
        sql += "\n" + "\n".join(joins)
    if where:
        sql += "\nWHERE " + "\n  AND ".join(where)
    sql += "\nGROUP BY " + ", ".join(group) + "\nORDER BY " + ", ".join(order)
    return sql, params, cube["fact"]


def run_query(wh_path: str, cube_id: str, measure: str, rows: dict, cols: dict | None = None,
              filters: list[dict] | None = None, use_aggregate: bool = True) -> dict:
    sql, params, source = build_query(cube_id, measure, rows, cols, filters or [], use_aggregate)
    conn = connect(wh_path)
    try:
        t0 = time.perf_counter()
        data = conn.execute(sql, params).fetchall()
        ms = (time.perf_counter() - t0) * 1000
    finally:
        conn.close()
    row_members, col_members, cells, col_rank = [], [], {}, {}
    for rec in data:
        r = rec[0] if rec[0] is not None else "(none)"
        c = (rec[1] if rec[1] is not None else "(none)") if cols else "value"
        v = rec[-1] or 0
        if r not in cells:
            row_members.append(r)
            cells[r] = {}
        if c not in col_members:
            col_members.append(c)
            if cols:
                col_rank[c] = rec[2]
        elif cols:
            col_rank[c] = min(col_rank[c], rec[2], key=lambda o: (o is None, o))
        cells[r][c] = v
    if cols:   # natural member order (e.g. HOPOPT, ICMP, TCP, UDP), whichever table answered
        col_members.sort(key=lambda c: (col_rank[c] is None, col_rank[c]))
    note = None
    if cols and len(col_members) > MAX_COLS:
        tot = {c: sum(cells[r].get(c, 0) for r in row_members) for c in col_members}
        keep = set(sorted(col_members, key=lambda c: -tot[c])[:MAX_COLS])
        note = f"Showing the {MAX_COLS} largest of {len(col_members)} columns."
        col_members = [c for c in col_members if c in keep]
    if len(row_members) > MAX_ROWS:
        note = (note + " " if note else "") + f"Showing the first {MAX_ROWS} of {len(row_members):,} rows."
        row_members = row_members[:MAX_ROWS]
    additive = cube_measure_is_additive(cube_id, measure)
    return {
        "sql": sql, "params": params, "ms": round(ms, 1), "note": note, "additive": additive,
        "source": source, "used_aggregate": source != CUBES[cube_id]["fact"],
        "rows": row_members, "cols": col_members if cols else [],
        "cells": [[cells[r].get(c) for c in (col_members if cols else ["value"])] for r in row_members],
    }


def cube_measure_is_additive(cube_id: str, measure: str) -> bool:
    """Counts and sums can be totalled across a row; averages cannot."""
    return not CUBES[cube_id]["measures"][measure][1].startswith("ROUND(AVG")


def members(wh_path: str, cube_id: str, dim: str, level: str) -> list[str]:
    cube = CUBES.get(cube_id)
    if not cube:
        raise QueryError(f"Unknown cube: {cube_id}")
    d, _, expr, order = _level(cube, dim, level)
    if d["table"]:
        sql = (f"SELECT {expr} FROM {d['table']} {d['alias']} WHERE {d['alias']}.{d['key']} IN "
               f"(SELECT DISTINCT {d['key']} FROM {cube['fact']}) GROUP BY 1 ORDER BY MIN({order}) LIMIT 1000")
    else:
        sql = f"SELECT {expr} FROM {cube['fact']} f GROUP BY 1 ORDER BY MIN({order}) LIMIT 1000"
    conn = connect(wh_path)
    try:
        return [r[0] for r in conn.execute(sql) if r[0] is not None]
    finally:
        conn.close()


# ---------------------------------------------------------------- schema browser
KIND = {"fact_flow": "fact", "fact_alert": "fact", "fact_review": "factless fact",
        "fact_attack_window": "factless fact", "agg_flow_hour": "aggregate fact",
        "mart_threat_daily": "data mart", "mart_soc": "data mart", "etl_run": "ETL metadata",
        "dim_attack_sf": "snowflake dimension", "dim_category": "snowflake sub-dimension",
        "dim_time_sf": "snowflake dimension", "dim_date": "snowflake sub-dimension",
        "dim_hour": "shrunken dimension"}


def tables(wh_path: str) -> list[dict]:
    conn = connect(wh_path)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        out = []
        for n in names:
            cols = [{"name": c[1], "type": c[2], "pk": bool(c[5])} for c in conn.execute(f"PRAGMA table_info({n})")]
            fks = [{"column": f[3], "table": f[2]} for f in conn.execute(f"PRAGMA foreign_key_list({n})")]
            rows = conn.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0]
            out.append({"name": n, "kind": KIND.get(n, "dimension" if n.startswith("dim_") else "table"),
                        "rows": rows, "columns": cols, "foreign_keys": fks})
        return out
    finally:
        conn.close()


def sample(wh_path: str, table: str, limit: int = 8) -> dict:
    conn = connect(wh_path)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if table not in names:
            raise QueryError(f"Unknown table: {table}")
        cur = conn.execute(f"SELECT * FROM {table} LIMIT ?", (max(1, min(limit, 50)),))
        return {"columns": [d[0] for d in cur.description], "rows": cur.fetchall()}
    finally:
        conn.close()


# ---------------------------------------------------------------- demonstrations
def _timed(conn, sql, repeat=3):
    best, rows = None, None
    for _ in range(repeat):
        t0 = time.perf_counter()
        rows = conn.execute(sql).fetchall()
        dt = (time.perf_counter() - t0) * 1000
        best = dt if best is None else min(best, dt)
    return rows, round(best, 1)


COMPARISONS = {
    "aggregate": {
        "title": "Base fact table vs aggregate fact table",
        "question": "How many flows of each attack class were seen per day?",
        "a": ("fact_flow (1 row per flow)",
              "SELECT t.date, a.attack_class, COUNT(*) AS flows\n"
              "FROM fact_flow f\nJOIN dim_time t ON t.time_key = f.time_key\n"
              "JOIN dim_attack a ON a.attack_key = f.attack_key\n"
              "GROUP BY t.date, a.attack_class ORDER BY 1, 2"),
        "b": ("agg_flow_hour (pre-summed per hour)",
              "SELECT h.date, a.attack_class, SUM(g.flows) AS flows\n"
              "FROM agg_flow_hour g\nJOIN dim_hour h ON h.hour_key = g.hour_key\n"
              "JOIN dim_attack a ON a.attack_key = g.attack_key\n"
              "GROUP BY h.date, a.attack_class ORDER BY 1, 2"),
    },
    "snowflake": {
        "title": "Star schema vs snowflake schema",
        "question": "How many flows per attack category on each day?",
        "a": ("Star: 2 joins (category stored in dim_attack)",
              "SELECT t.date, a.category, COUNT(*) AS flows\n"
              "FROM fact_flow f\nJOIN dim_time t ON t.time_key = f.time_key\n"
              "JOIN dim_attack a ON a.attack_key = f.attack_key\n"
              "GROUP BY t.date, a.category ORDER BY 1, 2"),
        "b": ("Snowflake: 4 joins (dim_time_sf -> dim_date, dim_attack_sf -> dim_category)",
              "SELECT dd.date, c.category, COUNT(*) AS flows\n"
              "FROM fact_flow f\nJOIN dim_time_sf t ON t.time_key = f.time_key\n"
              "JOIN dim_date dd ON dd.date_key = t.date_key\n"
              "JOIN dim_attack_sf a ON a.attack_key = f.attack_key\n"
              "JOIN dim_category c ON c.category_key = a.category_key\n"
              "GROUP BY dd.date, c.category ORDER BY 1, 2"),
    },
}


def compare(wh_path: str, which: str) -> dict:
    spec = COMPARISONS.get(which)
    if not spec:
        raise QueryError(f"Unknown comparison: {which}")
    conn = connect(wh_path)
    try:
        out = {"title": spec["title"], "question": spec["question"], "runs": []}
        results = []
        for key in ("a", "b"):
            label, sql = spec[key]
            table = sql.split("FROM ")[1].split()[0]
            scanned = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            rows, ms = _timed(conn, sql)
            results.append(rows)
            out["runs"].append({"label": label, "sql": sql, "ms": ms, "rows_scanned": scanned,
                                "result_rows": len(rows)})
        out["same_answer"] = results[0] == results[1]
        out["preview"] = results[0][:12]
        return out
    finally:
        conn.close()


def factless(wh_path: str) -> dict:
    conn = connect(wh_path)
    try:
        days = [r[0] for r in conn.execute("SELECT DISTINCT day_label FROM dim_hour ORDER BY hour_key")]
        classes = [r[0] for r in conn.execute(
            "SELECT attack_class FROM dim_attack WHERE nature = 'Malicious' ORDER BY attack_key")]
        hours = {(d, c): n for d, c, n in conn.execute(
            "SELECT h.day_label, a.attack_class, COUNT(*) FROM fact_attack_window w "
            "JOIN dim_hour h ON h.hour_key = w.hour_key JOIN dim_attack a ON a.attack_key = w.attack_key "
            "WHERE a.nature = 'Malicious' GROUP BY 1, 2")}
        not_seen = [r[0] for r in conn.execute(
            "SELECT a.attack_class FROM dim_attack a WHERE a.nature = 'Malicious' AND NOT EXISTS ("
            " SELECT 1 FROM fact_attack_window w JOIN dim_hour h ON h.hour_key = w.hour_key"
            " WHERE w.attack_key = a.attack_key AND h.day_name = 'Monday') ORDER BY a.attack_key")]
        reviews = conn.execute(
            "SELECT an.full_name, v.verdict, COUNT(*) FROM fact_review r "
            "JOIN dim_analyst an ON an.analyst_key = r.analyst_key "
            "JOIN dim_verdict v ON v.verdict_key = r.verdict_key GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
        sent = conn.execute("SELECT COUNT(*) FROM fact_alert f JOIN dim_route r ON r.route_key = f.route_key "
                            "WHERE r.route = 'review'").fetchone()[0]
        unreviewed = conn.execute(
            "SELECT COUNT(*) FROM fact_alert f JOIN dim_route r ON r.route_key = f.route_key "
            "WHERE r.route = 'review' AND NOT EXISTS (SELECT 1 FROM fact_review v WHERE v.alert_key = f.alert_key)"
        ).fetchone()[0]
        return {"days": days, "classes": classes,
                "coverage": [[hours.get((d, c), 0) for c in classes] for d in days],
                "not_seen_monday": not_seen,
                "coverage_sql": "SELECT a.attack_class FROM dim_attack a\nWHERE a.nature = 'Malicious'\n"
                                "  AND NOT EXISTS (SELECT 1 FROM fact_attack_window w\n"
                                "                  JOIN dim_hour h ON h.hour_key = w.hour_key\n"
                                "                  WHERE w.attack_key = a.attack_key\n"
                                "                    AND h.day_name = 'Monday')",
                "reviews": reviews, "sent_to_review": sent, "unreviewed": unreviewed,
                "unreviewed_sql": "SELECT COUNT(*) FROM fact_alert f\nJOIN dim_route r ON r.route_key = f.route_key\n"
                                  "WHERE r.route = 'review'\n  AND NOT EXISTS (SELECT 1 FROM fact_review v\n"
                                  "                  WHERE v.alert_key = f.alert_key)"}
    finally:
        conn.close()


def overview(wh_path: str, oltp_path: str) -> dict:
    out = {"built": Path(wh_path).exists(), "warehouse_path": wh_path, "oltp_path": oltp_path,
           "oltp_mb": round(sum(f.stat().st_size for f in Path(oltp_path).parent.glob(Path(oltp_path).name + "*"))
                            / 1e6, 1) if Path(oltp_path).exists() else 0}
    if Path(oltp_path).exists():
        c = sqlite3.connect(f"file:{Path(oltp_path).as_posix()}?mode=ro", uri=True)
        try:
            out["oltp_tables"] = [{"name": n, "rows": c.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0]}
                                  for (n,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        finally:
            c.close()
    if not out["built"]:
        return out
    out["warehouse_mb"] = round(Path(wh_path).stat().st_size / 1e6, 1)
    out["tables"] = [{k: t[k] for k in ("name", "kind", "rows")} for t in tables(wh_path)]
    conn = connect(wh_path)
    try:
        runs = conn.execute("SELECT run_id, mode, started_at, finished_at, status, steps, alert_watermark, "
                            "review_count FROM etl_run ORDER BY run_id DESC LIMIT 10").fetchall()
        out["runs"] = [{"run_id": r[0], "mode": r[1], "started_at": r[2], "finished_at": r[3], "status": r[4],
                        "steps": json.loads(r[5]), "alert_watermark": r[6],
                        "review_count": r[7]} for r in runs]
        lo, hi = conn.execute("SELECT MIN(time_key), MAX(time_key) FROM fact_flow WHERE time_key > 0").fetchone()
        out["span"] = [r[0] for r in conn.execute(
            "SELECT full_time FROM dim_time WHERE time_key IN (?, ?) ORDER BY time_key", (lo, hi))]
    finally:
        conn.close()
    return out


# ---------------------------------------------------------------- 3-D cube view
def run_cube(wh_path: str, cube_id: str, measure: str, x: dict, y: dict, z: dict,
             filters: list[dict] | None = None, max_members: int = 8) -> dict:
    """The data behind the 3-D cube picture: one cell per (x, y, z) member combination.

    A filter on one of the three axis dimensions at the SAME level is not applied; its
    members are returned as `highlight` so the picture can show the slice / dice inside
    the whole cube. Every other filter is applied as usual.
    """
    cube = CUBES.get(cube_id)
    if not cube:
        raise QueryError(f"Unknown cube: {cube_id}")
    if measure not in cube["measures"]:
        raise QueryError(f"Unknown measure: {measure}")
    axes = [x, y, z]
    if len({a["dim"] for a in axes}) < 3:
        raise QueryError("The three cube axes must use three different dimensions")
    for a in axes:
        _level(cube, a["dim"], a["level"])
    axis_at = {(a["dim"], a["level"]): i for i, a in enumerate(axes)}
    highlight, applied = {}, []
    for f in filters or []:
        if not f.get("values"):
            continue
        key = (f["dim"], f["level"])
        if key in axis_at:
            highlight[axis_at[key]] = [str(v) for v in f["values"]]
        else:
            applied.append(f)
    view = _aggregate_view(cube, axes + applied) or cube
    select, dims, ords = [], [], []
    for i, a in enumerate(axes):
        _, _, expr, order = _level(view, a["dim"], a["level"])
        select.append(f"{expr} AS m{i}")
        ords.append(f"MIN({order}) AS o{i}")
        dims.append(a["dim"])
    where, params = [], []
    for f in applied:
        values = [str(v) for v in f["values"]][:200]
        _, _, fexpr, _ = _level(view, f["dim"], f["level"])
        where.append(f"{fexpr} IN ({', '.join('?' * len(values))})")
        params += values
        dims.append(f["dim"])
    joins = [j for j in dict.fromkeys(_join(view, d) for d in dims) if j]
    sql = ("SELECT " + ", ".join(select + ords) + f", {view['measures'][measure][1]} AS value\n"
           f"FROM {view['fact']} f" + ("\n" + "\n".join(joins) if joins else "")
           + ("\nWHERE " + "\n  AND ".join(where) if where else "")
           + "\nGROUP BY m0, m1, m2")
    conn = connect(wh_path)
    try:
        t0 = time.perf_counter()
        data = conn.execute(sql, params).fetchall()
        ms = (time.perf_counter() - t0) * 1000
    finally:
        conn.close()
    out_axes = []
    for i, a in enumerate(axes):
        order_key, weight = {}, {}
        for rec in data:
            m = rec[i] if rec[i] is not None else "(none)"
            o = rec[3 + i]
            order_key[m] = o if m not in order_key else min(order_key[m], o, key=lambda v: (v is None, v))
            weight[m] = weight.get(m, 0) + abs(rec[-1] or 0)
        members = sorted(order_key, key=lambda m: (order_key[m] is None, order_key[m]))
        dropped = 0
        if len(members) > max_members:
            keep = set(sorted(members, key=lambda m: -weight[m])[:max_members])
            dropped = len(members) - max_members
            members = [m for m in members if m in keep]
        d, label, _, _ = _level(cube, a["dim"], a["level"])
        out_axes.append({"dim": a["dim"], "level": a["level"], "dim_label": d["label"], "level_label": label,
                         "members": members, "dropped": dropped})
    index = [{m: k for k, m in enumerate(ax["members"])} for ax in out_axes]
    cells = []
    for rec in data:
        key = [rec[i] if rec[i] is not None else "(none)" for i in range(3)]
        if all(key[i] in index[i] for i in range(3)):
            cells.append([index[0][key[0]], index[1][key[1]], index[2][key[2]], rec[-1]])
    return {"axes": out_axes, "cells": cells, "highlight": {str(k): v for k, v in highlight.items()},
            "measure": cube["measures"][measure][0], "additive": cube_measure_is_additive(cube_id, measure),
            "source": view["fact"], "ms": round(ms, 1), "sql": sql, "params": params}
