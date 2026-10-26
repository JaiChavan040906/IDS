"""Data warehouse (DWM Module 1): a separate, read-optimised copy of the project's data.

The portal database (data/ids.db) is the operational (OLTP) store: many small writes,
normalised tables, only the current state. The warehouse (data/warehouse.db) is built
from it and from the cleaned dataset by the ETL job below, and is organised as
dimensional models for analysis (OLAP):

  star schema        fact_flow + dim_time, dim_attack, dim_service, dim_protocol, dim_split
  snowflake schema   the same facts, with dim_attack_sf -> dim_category and
                     dim_time_sf -> dim_date normalised into sub-dimensions
  fact constellation fact_alert and fact_review share dim_time, dim_attack and dim_model
  factless facts     fact_review (an analyst reviewed an alert: no measures) and
                     fact_attack_window (which attack was active in which hour)
  aggregate fact     agg_flow_hour (flows per hour, attack class, protocol and split, pre-summed)
  data marts         mart_threat_daily (threat analysis), mart_soc (security operations)

Sources
  1. data/processed/{train,val,test}.parquet  cleaned, de-duplicated flows with label + split
  2. data/raw/<day>.csv                      original timestamps, joined on (day, row id)
  3. data/ids.db                             alerts, analyst decisions, models, users

Nothing here is used by the detector. The warehouse is descriptive only: it never
feeds training, tuning or the analyst's decision.
"""

import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ids.data import LABEL_COL

SPLITS = [(1, "train", "Model training (70%)"),
          (2, "val", "Tuning and calibration (15%)"),
          (3, "test", "Final test, replayed in the portal (15%)")]

CATEGORY = {
    "BENIGN": "Normal traffic",
    "DoS Hulk": "Denial of service", "DoS GoldenEye": "Denial of service",
    "DoS Slowloris": "Denial of service", "DoS Slowhttptest": "Denial of service",
    "DDoS": "Distributed DoS", "Portscan": "Reconnaissance",
    "FTP-Patator": "Brute force", "SSH-Patator": "Brute force",
    "Web Attack": "Web attack", "Botnet": "Botnet",
    "Infiltration": "Infiltration", "Heartbleed": "Exploit",
}

SERVICES = {20: "FTP data", 21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
            80: "HTTP", 88: "Kerberos", 110: "POP3", 123: "NTP", 135: "MS RPC",
            137: "NetBIOS", 138: "NetBIOS", 139: "NetBIOS", 143: "IMAP", 389: "LDAP",
            443: "HTTPS", 444: "HTTPS (alt)", 445: "SMB", 465: "SMTPS", 587: "SMTP",
            993: "IMAPS", 3268: "LDAP (global catalog)", 3389: "RDP", 5353: "mDNS",
            5355: "LLMNR", 8080: "HTTP (alt)", 8443: "HTTPS (alt)"}

PROTOCOLS = {0: "HOPOPT", 1: "ICMP", 6: "TCP", 17: "UDP"}

ROUTES = [(1, "auto_benign", "Closed automatically", "Model sure it is normal (not stored as an alert)"),
          (2, "auto_alert", "Automatic alert", "Model sure it is an attack"),
          (3, "review", "Sent to analyst", "Model unsure, unfamiliar or the RF disagrees")]

VERDICTS = ["malicious", "benign", "unsure"]
CONFIDENCES = ["low", "medium", "high"]

PART_OF_DAY = [(0, 6, "Night"), (6, 12, "Morning"), (12, 17, "Afternoon"), (17, 24, "Evening")]

FLOW_COLS = ["row_id", "day", "Dst Port", "Protocol", "Flow Duration", "Total Fwd Packet",
             "Total Bwd packets", "Total Length of Fwd Packet", "Total Length of Bwd Packet",
             LABEL_COL]

DDL = """
CREATE TABLE dim_time (
  time_key INTEGER PRIMARY KEY,          -- smart key YYYYMMDDHHMM (minute grain), 0 = unknown
  full_time TEXT, date TEXT, day_name TEXT, part_of_day TEXT, hour INTEGER, minute INTEGER,
  day_label TEXT, pod_label TEXT, hour_label TEXT, minute_label TEXT);
CREATE TABLE dim_attack (
  attack_key INTEGER PRIMARY KEY, attack_class TEXT UNIQUE, category TEXT, nature TEXT, severity TEXT);
CREATE TABLE dim_service (
  service_key INTEGER PRIMARY KEY, dst_port INTEGER UNIQUE, service TEXT,
  port_range TEXT, port_range_order INTEGER);
CREATE TABLE dim_protocol (
  protocol_key INTEGER PRIMARY KEY, protocol_number INTEGER UNIQUE, protocol_name TEXT);
CREATE TABLE dim_split (split_key INTEGER PRIMARY KEY, split_name TEXT, purpose TEXT);
CREATE TABLE fact_flow (
  flow_key INTEGER PRIMARY KEY,
  time_key INTEGER REFERENCES dim_time, attack_key INTEGER REFERENCES dim_attack,
  service_key INTEGER REFERENCES dim_service, protocol_key INTEGER REFERENCES dim_protocol,
  split_key INTEGER REFERENCES dim_split,
  source_day TEXT, source_row INTEGER,   -- degenerate dimension: where the row came from
  duration_ms REAL, fwd_packets INTEGER, bwd_packets INTEGER, total_packets INTEGER,
  fwd_bytes INTEGER, bwd_bytes INTEGER, total_bytes INTEGER);

CREATE TABLE dim_category (category_key INTEGER PRIMARY KEY, category TEXT UNIQUE, nature TEXT);
CREATE TABLE dim_attack_sf (
  attack_key INTEGER PRIMARY KEY, attack_class TEXT, severity TEXT,
  category_key INTEGER REFERENCES dim_category);
CREATE TABLE dim_date (date_key INTEGER PRIMARY KEY, date TEXT, day_name TEXT, day_label TEXT);
CREATE TABLE dim_time_sf (
  time_key INTEGER PRIMARY KEY, date_key INTEGER REFERENCES dim_date,
  part_of_day TEXT, hour INTEGER, minute INTEGER);

CREATE TABLE dim_model (model_key INTEGER PRIMARY KEY, version TEXT UNIQUE, status TEXT, parent TEXT, created_at TEXT);
CREATE TABLE dim_route (route_key INTEGER PRIMARY KEY, route TEXT UNIQUE, route_label TEXT, meaning TEXT);
CREATE TABLE dim_analyst (analyst_key INTEGER PRIMARY KEY, username TEXT UNIQUE, full_name TEXT, role TEXT);
CREATE TABLE dim_verdict (verdict_key INTEGER PRIMARY KEY, verdict TEXT, confidence TEXT, UNIQUE (verdict, confidence));
CREATE TABLE fact_alert (
  alert_key INTEGER PRIMARY KEY,         -- = portal alert id
  time_key INTEGER REFERENCES dim_time, attack_key INTEGER REFERENCES dim_attack,  -- predicted class
  model_key INTEGER REFERENCES dim_model, route_key INTEGER REFERENCES dim_route,
  service_key INTEGER REFERENCES dim_service, protocol_key INTEGER REFERENCES dim_protocol,
  severity TEXT, source TEXT,
  confidence REAL, entropy REAL, distance REAL);
CREATE TABLE fact_review (              -- factless: records that a review happened, no measures
  review_key INTEGER PRIMARY KEY,        -- = portal feedback id
  alert_key INTEGER REFERENCES fact_alert, time_key INTEGER REFERENCES dim_time,
  analyst_key INTEGER REFERENCES dim_analyst, attack_key INTEGER REFERENCES dim_attack,  -- analyst's class
  verdict_key INTEGER REFERENCES dim_verdict, model_key INTEGER REFERENCES dim_model,
  reviewed_at TEXT);

CREATE TABLE dim_hour (                  -- shrunken time dimension for the aggregate
  hour_key INTEGER PRIMARY KEY, date TEXT, day_name TEXT, part_of_day TEXT, hour INTEGER,
  day_label TEXT, pod_label TEXT, hour_label TEXT);
CREATE TABLE agg_flow_hour (
  hour_key INTEGER REFERENCES dim_hour, attack_key INTEGER REFERENCES dim_attack,
  protocol_key INTEGER REFERENCES dim_protocol, split_key INTEGER REFERENCES dim_split,
  flows INTEGER, total_packets INTEGER, total_bytes INTEGER, total_duration_ms REAL,
  PRIMARY KEY (hour_key, attack_key, protocol_key, split_key));
CREATE TABLE fact_attack_window (        -- factless coverage: attack class seen in this hour
  hour_key INTEGER REFERENCES dim_hour, attack_key INTEGER REFERENCES dim_attack,
  PRIMARY KEY (hour_key, attack_key));

CREATE TABLE mart_threat_daily (
  date TEXT, day_name TEXT, category TEXT, attack_class TEXT, service TEXT,
  flows INTEGER, total_bytes INTEGER);
CREATE TABLE mart_soc (
  model_version TEXT, route TEXT, predicted_class TEXT, severity TEXT,
  alerts INTEGER, reviewed INTEGER, avg_confidence REAL);

CREATE TABLE etl_run (
  run_id INTEGER PRIMARY KEY, mode TEXT, started_at TEXT, finished_at TEXT, status TEXT,
  steps TEXT, alert_watermark INTEGER, review_count INTEGER);
"""

# fact_flow gets no foreign-key indexes on purpose: OLAP queries read most of it, and one
# sequential scan is ~4x faster in SQLite than 1.7 million index lookups.
INDEXES = """
CREATE INDEX ix_alert_time ON fact_alert(time_key);
CREATE INDEX ix_review_alert ON fact_review(alert_key);
"""


# ---------------------------------------------------------------- helpers
def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def port_range(port: int) -> tuple[str, int]:
    if port <= 1023:
        return "Well-known (0-1023)", 1
    if port <= 49151:
        return "Registered (1024-49151)", 2
    return "Dynamic (49152-65535)", 3


def part_of_day(hour: int) -> str:
    return next(name for lo, hi, name in PART_OF_DAY if lo <= hour < hi)


def time_key_of(ts: pd.Series) -> pd.Series:
    """Timestamp -> YYYYMMDDHHMM integer (0 where the time is unknown)."""
    ts = pd.to_datetime(ts, errors="coerce", format="ISO8601")
    part = lambda x: x.astype("float64")  # noqa: E731  (int32 parts would overflow)
    key = (part(ts.dt.year) * 100_000_000 + part(ts.dt.month) * 1_000_000
           + part(ts.dt.day) * 10_000 + part(ts.dt.hour) * 100 + part(ts.dt.minute))
    return key.fillna(0).astype("int64")


def time_rows(keys) -> list[tuple]:
    out = []
    for k in sorted({int(k) for k in keys}):
        if k == 0:
            out.append((0, None, None, "Unknown", "Unknown", None, None,
                        "Unknown", "Unknown", "Unknown", "Unknown"))
            continue
        d = datetime.strptime(str(k), "%Y%m%d%H%M")
        day = d.strftime("%a %d %b %Y")
        pod = part_of_day(d.hour)
        out.append((k, d.strftime("%Y-%m-%d %H:%M"), d.strftime("%Y-%m-%d"), d.strftime("%A"),
                    pod, d.hour, d.minute, day, f"{day} · {pod}",
                    f"{day} {d.hour:02d}:00", f"{day} {d.hour:02d}:{d.minute:02d}"))
    return out


def attack_rows(severity: dict) -> list[tuple]:
    """(key, class, category, nature, severity) - fixed order so keys never change."""
    rows = []
    for i, cls in enumerate(CATEGORY, start=1):
        nature = "Benign" if cls == "BENIGN" else "Malicious"
        sev = "none" if cls == "BENIGN" else next(
            (lvl for lvl in ("high", "medium") if cls in severity.get(lvl, [])), "low")
        rows.append((i, cls, CATEGORY[cls], nature, sev))
    return rows


def service_row(key: int, port: int) -> tuple:
    rng, order = port_range(port)
    return (key, port, SERVICES.get(port, "Other"), rng, order)


def protocol_row(key: int, number: int) -> tuple:
    return (key, number, PROTOCOLS.get(number, f"IP protocol {number}"))


def insert(conn, table: str, rows, ncols: int | None = None):
    rows = list(rows) if not isinstance(rows, list) else rows
    if not rows:
        return 0
    n = ncols or len(rows[0])
    conn.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * n)})", rows)
    return len(rows)


def df_rows(df: pd.DataFrame):
    """DataFrame -> plain Python tuples (sqlite3 does not accept numpy scalars)."""
    return list(zip(*(df[c].tolist() for c in df.columns)))


class EtlLog:
    """Collects the steps of one ETL run (shown on the ETL page)."""

    def __init__(self, on_step=None):
        self.steps, self.on_step, self.t0 = [], on_step, time.perf_counter()

    def step(self, phase: str, name: str, detail: str, rows: int | None = None):
        now = time.perf_counter()
        self.steps.append({"phase": phase, "name": name, "detail": detail, "rows": rows,
                           "seconds": round(now - self.t0, 2)})
        self.t0 = now
        if self.on_step:
            self.on_step(self.steps[-1])


# ---------------------------------------------------------------- extract
def extract_flows(processed_dir: str) -> pd.DataFrame:
    parts = []
    for key, name, _ in SPLITS:
        df = pd.read_parquet(Path(processed_dir) / f"{name}.parquet", columns=FLOW_COLS)
        df["split_key"] = key
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)
    df["row_id"] = df["row_id"].astype("int64")
    df["day"] = df["day"].astype(str)
    return df


def extract_timestamps(raw_dir: str) -> pd.DataFrame:
    parts = []
    for f in sorted(Path(raw_dir).glob("*.csv")):
        header = pd.read_csv(f, nrows=0).columns
        use = [h for h in header if h.strip() in {"id", "Timestamp"}]
        ts = pd.read_csv(f, usecols=use)
        ts.columns = [c.strip() for c in ts.columns]
        ts = ts.rename(columns={"id": "row_id"})
        ts["day"] = f.stem
        parts.append(ts)
    return pd.concat(parts, ignore_index=True)


def extract_portal(oltp_path: str, alert_after: int = 0) -> dict[str, pd.DataFrame]:
    """Read the operational DB read-only. alert_after > 0 = incremental extraction."""
    empty = {k: pd.DataFrame() for k in ("alerts", "feedback", "users", "models")}
    if not Path(oltp_path).exists():
        return empty
    conn = sqlite3.connect(f"file:{Path(oltp_path).as_posix()}?mode=ro", uri=True)
    try:
        q = lambda sql, *p: pd.read_sql_query(sql, conn, params=p)  # noqa: E731
        return {
            "alerts": q("SELECT id, flow_time, dst_port, protocol, model_version, predicted_class, "
                        "decision, severity, source, confidence, entropy, distance "
                        "FROM alerts WHERE id > ? ORDER BY id", alert_after),
            "feedback": q("SELECT id, alert_id, analyst, verdict, attack_class, confidence, created_at "
                          "FROM feedback ORDER BY id"),
            "users": q("SELECT username, full_name, role FROM users"),
            "models": q("SELECT version, status, parent, created_at FROM model_versions ORDER BY id"),
            "alert_ids": q("SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id FROM alerts"),
        }
    except Exception:
        return empty   # portal DB not initialised yet
    finally:
        conn.close()


# ---------------------------------------------------------------- transform
def transform_flows(flows: pd.DataFrame, ts: pd.DataFrame, log: EtlLog) -> pd.DataFrame:
    df = flows.merge(ts, on=["day", "row_id"], how="left", validate="one_to_one")
    missing = int(df["Timestamp"].isna().sum())
    log.step("transform", "Integrate", "Joined each cleaned flow to its raw row on (day, row id) "
             f"to recover the timestamp. Rows without a match: {missing:,}.", len(df))

    num = ["Flow Duration", "Total Fwd Packet", "Total Bwd packets",
           "Total Length of Fwd Packet", "Total Length of Bwd Packet"]
    bad = df[num].isna() | (df[num] < 0)
    fixed = int(bad.any(axis=1).sum())
    df[num] = df[num].where(~bad, 0)
    log.step("transform", "Clean", f"Missing or negative measures set to 0 in {fixed:,} rows.", fixed)

    out = pd.DataFrame({
        "time_key": time_key_of(df["Timestamp"]),
        "attack": df[LABEL_COL].astype(str),
        "dst_port": df["Dst Port"].fillna(0).astype("int64"),
        "protocol": df["Protocol"].fillna(0).astype("int64"),
        "split_key": df["split_key"].astype("int64"),
        "source_day": df["day"],
        "source_row": df["row_id"],
        "duration_ms": (df["Flow Duration"].astype("float64") / 1000.0).round(3),
        "fwd_packets": df["Total Fwd Packet"].astype("int64"),
        "bwd_packets": df["Total Bwd packets"].astype("int64"),
        "fwd_bytes": df["Total Length of Fwd Packet"].astype("int64"),
        "bwd_bytes": df["Total Length of Bwd Packet"].astype("int64"),
    })
    out["total_packets"] = out["fwd_packets"] + out["bwd_packets"]
    out["total_bytes"] = out["fwd_bytes"] + out["bwd_bytes"]
    log.step("transform", "Derive", "Microseconds -> milliseconds; forward + backward packets and "
             "bytes summed; timestamp -> minute time key; port -> service and port range; "
             "attack class -> category -> benign/malicious.", len(out))
    return out


class Keys:
    """Surrogate-key lookups for the dimensions (warehouse keys, not source ids)."""

    def __init__(self, conn):
        self.conn = conn
        self.attack = dict(conn.execute("SELECT attack_class, attack_key FROM dim_attack"))
        self.service = dict(conn.execute("SELECT dst_port, service_key FROM dim_service"))
        self.protocol = dict(conn.execute("SELECT protocol_number, protocol_key FROM dim_protocol"))
        self.model = dict(conn.execute("SELECT version, model_key FROM dim_model"))
        self.analyst = dict(conn.execute("SELECT username, analyst_key FROM dim_analyst"))
        self.route = dict(conn.execute("SELECT route, route_key FROM dim_route"))
        self.verdict = {(v, c): k for k, v, c in conn.execute("SELECT * FROM dim_verdict")}
        self.times = {r[0] for r in conn.execute("SELECT time_key FROM dim_time")}

    def ensure_services(self, ports) -> int:
        new = sorted({int(p) for p in ports} - set(self.service))
        start = max(self.service.values(), default=0) + 1
        rows = [service_row(start + i, p) for i, p in enumerate(new)]
        insert(self.conn, "dim_service", rows)
        self.service.update({r[1]: r[0] for r in rows})
        return len(rows)

    def ensure_protocols(self, numbers) -> int:
        new = sorted({int(p) for p in numbers} - set(self.protocol))
        start = max(self.protocol.values(), default=0) + 1
        rows = [protocol_row(start + i, p) for i, p in enumerate(new)]
        insert(self.conn, "dim_protocol", rows)
        self.protocol.update({r[1]: r[0] for r in rows})
        return len(rows)

    def ensure_times(self, keys) -> int:
        new = {int(k) for k in keys} - self.times
        rows = time_rows(new)
        insert(self.conn, "dim_time", rows)
        insert(self.conn, "dim_time_sf", [(r[0], int(r[0]) // 10_000 if r[0] else 0, r[4], r[5], r[6])
                                          for r in rows])
        dates = {(int(r[0]) // 10_000 if r[0] else 0, r[2], r[3], r[7]) for r in rows}
        self.conn.executemany("INSERT OR IGNORE INTO dim_date VALUES (?,?,?,?)", list(dates))
        self.times |= new
        return len(rows)

    def ensure_models(self, models: pd.DataFrame, versions) -> int:
        n = 0
        known = {} if models.empty else {r.version: r for r in models.itertuples()}
        for v in [*known, *sorted(set(versions))]:
            r = known.get(v)
            if v in self.model:
                if r is not None:   # type 1 slowly changing dimension: overwrite the status
                    self.conn.execute("UPDATE dim_model SET status=? WHERE version=?", (r.status, v))
                continue
            key = max(self.model.values(), default=0) + 1
            self.conn.execute("INSERT INTO dim_model VALUES (?,?,?,?,?)",
                              (key, v, r.status if r is not None else "unknown",
                               r.parent if r is not None else None,
                               str(r.created_at) if r is not None else None))
            self.model[v] = key
            n += 1
        return n

    def ensure_analysts(self, users: pd.DataFrame, names) -> int:
        n = 0
        known = {} if users.empty else {r.username: r for r in users.itertuples()}
        for u in [*known, *sorted(set(names))]:
            if u in self.analyst:
                continue
            r = known.get(u)
            key = max(self.analyst.values(), default=0) + 1
            self.conn.execute("INSERT INTO dim_analyst VALUES (?,?,?,?)",
                              (key, u, r.full_name if r is not None else u,
                               r.role if r is not None else "demo"))
            self.analyst[u] = key
            n += 1
        return n


# ---------------------------------------------------------------- load
def create_schema(conn, severity: dict):
    conn.executescript(DDL)
    insert(conn, "dim_attack", attack_rows(severity))
    cats = list(dict.fromkeys(CATEGORY.values()))
    insert(conn, "dim_category", [(i, c, "Benign" if c == "Normal traffic" else "Malicious")
                                  for i, c in enumerate(cats, start=1)])
    cat_key = {c: i for i, c in enumerate(cats, start=1)}
    insert(conn, "dim_attack_sf", [(k, cls, sev, cat_key[cat]) for k, cls, cat, _, sev in attack_rows(severity)])
    insert(conn, "dim_split", SPLITS)
    insert(conn, "dim_route", ROUTES)
    insert(conn, "dim_verdict", [(i * 3 + j + 1, v, c) for i, v in enumerate(VERDICTS)
                                 for j, c in enumerate(CONFIDENCES)])


def load_flows(conn, flows: pd.DataFrame, keys: Keys, log: EtlLog):
    nt = keys.ensure_times(flows["time_key"].unique())
    ns = keys.ensure_services(flows["dst_port"].unique())
    np_ = keys.ensure_protocols(flows["protocol"].unique())
    log.step("load", "Load dimensions", f"dim_time {nt:,} minutes, dim_service {ns:,} ports, "
             f"dim_protocol {np_}, dim_attack {len(keys.attack)} classes, dim_split 3 "
             "(+ snowflaked dim_date, dim_time_sf, dim_category, dim_attack_sf).", nt + ns + np_)
    fact = pd.DataFrame({
        "flow_key": np.arange(1, len(flows) + 1),
        "time_key": flows["time_key"],
        "attack_key": flows["attack"].map(keys.attack),
        "service_key": flows["dst_port"].map(keys.service),
        "protocol_key": flows["protocol"].map(keys.protocol),
        "split_key": flows["split_key"],
        "source_day": flows["source_day"], "source_row": flows["source_row"],
        "duration_ms": flows["duration_ms"],
        "fwd_packets": flows["fwd_packets"], "bwd_packets": flows["bwd_packets"],
        "total_packets": flows["total_packets"], "fwd_bytes": flows["fwd_bytes"],
        "bwd_bytes": flows["bwd_bytes"], "total_bytes": flows["total_bytes"],
    })
    if fact["attack_key"].isna().any():
        raise ValueError("flows with an attack class missing from dim_attack")
    for start in range(0, len(fact), 200_000):
        insert(conn, "fact_flow", df_rows(fact.iloc[start:start + 200_000]))
    log.step("load", "Load fact_flow", "One row per network flow (grain = one flow), "
             "foreign keys to every dimension plus the measures.", len(fact))


def load_portal(conn, src: dict, keys: Keys, log: EtlLog, incremental: bool) -> tuple[int, int]:
    alerts, feedback = src["alerts"], src["feedback"]
    nm = keys.ensure_models(src["models"], [] if alerts.empty else alerts["model_version"])
    na = keys.ensure_analysts(src["users"], [] if feedback.empty else feedback["analyst"])
    if not alerts.empty:
        alerts = alerts.assign(time_key=time_key_of(alerts["flow_time"]))
        keys.ensure_times(alerts["time_key"].unique())
        keys.ensure_services(alerts["dst_port"].fillna(0).astype(int).unique())
        keys.ensure_protocols(alerts["protocol"].fillna(0).astype(int).unique())
        rows = [(int(r.id), int(r.time_key), keys.attack.get(r.predicted_class),
                 keys.model[r.model_version], keys.route.get(r.decision),
                 keys.service[int(r.dst_port or 0)], keys.protocol[int(r.protocol or 0)],
                 r.severity, r.source, float(r.confidence), float(r.entropy), float(r.distance))
                for r in alerts.itertuples()]
        insert(conn, "fact_alert", rows)
    log.step("load", "Load fact_alert", ("Incremental append: only alerts newer than the last "
             "watermark." if incremental else "All portal alerts.")
             + f" New model versions {nm}, analysts {na}.", len(alerts))

    # Reviews can be added, verified or removed (demo tools), so this small table is
    # fully refreshed every run instead of appended.
    conn.execute("DELETE FROM fact_review")
    rows = []
    if not feedback.empty:
        tk = dict(conn.execute("SELECT alert_key, time_key FROM fact_alert"))
        mk = dict(conn.execute("SELECT alert_key, model_key FROM fact_alert"))
        for r in feedback.itertuples():
            if r.alert_id not in tk:
                continue
            rows.append((int(r.id), int(r.alert_id), tk[r.alert_id], keys.analyst[r.analyst],
                         keys.attack.get(r.attack_class), keys.verdict.get((r.verdict, r.confidence)),
                         mk[r.alert_id], str(r.created_at)))
        insert(conn, "fact_review", rows)
    log.step("load", "Refresh fact_review", "Factless fact table (no measures): one row per analyst "
             "decision. Small, so it is fully refreshed.", len(rows))
    alert_max = int(conn.execute("SELECT COALESCE(MAX(alert_key), 0) FROM fact_alert").fetchone()[0])
    return alert_max, len(rows)


def build_derived(conn, log: EtlLog, flows_changed: bool):
    if flows_changed:
        conn.executescript("""
            DELETE FROM dim_hour; DELETE FROM agg_flow_hour; DELETE FROM fact_attack_window;
            DELETE FROM mart_threat_daily;
            INSERT INTO dim_hour
              SELECT DISTINCT time_key / 100, date, day_name, part_of_day, hour, day_label, pod_label, hour_label
              FROM dim_time WHERE time_key IN (SELECT DISTINCT time_key FROM fact_flow);
            INSERT INTO agg_flow_hour
              SELECT time_key / 100, attack_key, protocol_key, split_key,
                     COUNT(*), SUM(total_packets), SUM(total_bytes), SUM(duration_ms)
              FROM fact_flow GROUP BY time_key / 100, attack_key, protocol_key, split_key;
            INSERT INTO fact_attack_window SELECT DISTINCT hour_key, attack_key FROM agg_flow_hour;
            INSERT INTO mart_threat_daily
              SELECT t.date, t.day_name, a.category, a.attack_class, s.service, COUNT(*), SUM(f.total_bytes)
              FROM fact_flow f JOIN dim_time t ON t.time_key = f.time_key
              JOIN dim_attack a ON a.attack_key = f.attack_key
              JOIN dim_service s ON s.service_key = f.service_key
              WHERE a.nature = 'Malicious'
              GROUP BY t.date, t.day_name, a.category, a.attack_class, s.service;
        """)
        n = conn.execute("SELECT COUNT(*) FROM agg_flow_hour").fetchone()[0]
        log.step("load", "Build aggregate + coverage", "agg_flow_hour pre-sums flows per hour, "
                 "attack class, protocol and split; fact_attack_window (factless) records which attacks were active "
                 "in which hour; mart_threat_daily is the threat-analysis data mart.", n)
    conn.executescript("""
        DELETE FROM mart_soc;
        INSERT INTO mart_soc
          SELECT m.version, r.route_label, a.attack_class, f.severity, COUNT(*),
                 SUM(CASE WHEN f.alert_key IN (SELECT alert_key FROM fact_review) THEN 1 ELSE 0 END),
                 ROUND(AVG(f.confidence), 4)
          FROM fact_alert f JOIN dim_model m ON m.model_key = f.model_key
          JOIN dim_route r ON r.route_key = f.route_key
          JOIN dim_attack a ON a.attack_key = f.attack_key
          GROUP BY m.version, r.route_label, a.attack_class, f.severity;
    """)
    n = conn.execute("SELECT COUNT(*) FROM mart_soc").fetchone()[0]
    log.step("load", "Refresh mart_soc", "Security-operations data mart: alerts and reviews per "
             "model, route and predicted class.", n)


# ---------------------------------------------------------------- runs
def _record(conn, mode, started, log, alert_wm, n_reviews, status="ok"):
    conn.execute("INSERT INTO etl_run (mode, started_at, finished_at, status, steps, alert_watermark, "
                 "review_count) VALUES (?,?,?,?,?,?,?)",
                 (mode, started, utcnow(), status, json.dumps(log.steps), alert_wm, n_reviews))


def full_load(wh_path: str, processed_dir: str, raw_dir: str, oltp_path: str, severity: dict,
              on_step=None, flows: pd.DataFrame | None = None, timestamps: pd.DataFrame | None = None):
    """Rebuild the whole warehouse in a staging file, then swap it in (readers never see
    a half-built warehouse). `flows` / `timestamps` can be passed in by tests."""
    log, started = EtlLog(on_step), utcnow()
    if flows is None:
        flows = extract_flows(processed_dir)
    log.step("extract", "Extract flows", "Full extraction of the cleaned train / validation / test "
             f"files ({processed_dir}): 9 of 88 columns.", len(flows))
    if timestamps is None:
        timestamps = extract_timestamps(raw_dir)
    log.step("extract", "Extract timestamps", f"Full extraction of id + Timestamp from the "
             f"{flows['day'].nunique()} raw day files ({raw_dir}).", len(timestamps))
    src = extract_portal(oltp_path)
    log.step("extract", "Extract portal", "Read-only extraction from the operational database: "
             f"{len(src['alerts']):,} alerts, {len(src['feedback']):,} decisions, "
             f"{len(src['models'])} model versions, {len(src['users'])} users.",
             len(src["alerts"]) + len(src["feedback"]))

    facts = transform_flows(flows, timestamps, log)
    del flows, timestamps

    stage = Path(str(wh_path) + ".staging")
    stage.unlink(missing_ok=True)
    conn = sqlite3.connect(stage)
    try:
        conn.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;")
        create_schema(conn, severity)
        keys = Keys(conn)
        load_flows(conn, facts, keys, log)
        del facts
        alert_wm, n_rev = load_portal(conn, src, keys, log, incremental=False)
        build_derived(conn, log, flows_changed=True)
        conn.executescript(INDEXES)
        conn.execute("ANALYZE")
        log.step("load", "Index + publish", "Indexes on the small alert facts (fact_flow is read by "
                 "full scans), statistics for the query planner, then the staging file replaces "
                 "the live warehouse in one step.")
        _record(conn, "full", started, log, alert_wm, n_rev)
        conn.commit()
    finally:
        conn.close()
    for attempt in range(40):   # a reader may hold the old file open for a moment (Windows)
        try:
            os.replace(stage, wh_path)
            break
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.25)
    return log.steps


def incremental_load(wh_path: str, oltp_path: str, on_step=None):
    """Append only portal alerts newer than the last watermark; refresh reviews and marts."""
    log, started = EtlLog(on_step), utcnow()
    conn = sqlite3.connect(wh_path, timeout=30)
    try:
        wm = conn.execute("SELECT alert_watermark FROM etl_run ORDER BY run_id DESC LIMIT 1").fetchone()
        wm = int(wm[0] or 0) if wm else 0
        loaded = conn.execute("SELECT COUNT(*) FROM fact_alert").fetchone()[0]
        probe = extract_portal(oltp_path, alert_after=wm)
        ids = probe.get("alert_ids")
        src_n, src_max = (0, 0) if ids is None or ids.empty else (int(ids.n[0]), int(ids.max_id[0]))
        # alerts with id <= watermark in the source must equal what we already loaded,
        # otherwise the portal was reset or rows were deleted -> reload the portal facts.
        src_old = src_n - len(probe["alerts"])
        if src_max < wm or src_old != loaded:
            conn.execute("DELETE FROM fact_alert")
            probe = extract_portal(oltp_path, alert_after=0)
            wm = 0
            log.step("extract", "Detect change", "The portal database no longer matches the last "
                     "load (it was reset or alerts were removed), so all portal alerts are "
                     "re-extracted.", len(probe["alerts"]))
        log.step("extract", "Extract new alerts", f"Incremental extraction: alerts with id > {wm} "
                 f"(the watermark saved by the previous run), plus all {len(probe['feedback']):,} "
                 "decisions.", len(probe["alerts"]))
        keys = Keys(conn)
        log.step("transform", "Map keys", "Flow time -> minute time key; model version, route, "
                 "port, protocol and analyst -> warehouse surrogate keys (new members are added "
                 "to their dimension first).", len(probe["alerts"]))
        alert_wm, n_rev = load_portal(conn, probe, keys, log, incremental=True)
        build_derived(conn, log, flows_changed=False)
        _record(conn, "incremental", started, log, alert_wm, n_rev)
        conn.commit()
    finally:
        conn.close()
    return log.steps


class EtlRunner:
    """Runs one ETL job at a time in a background thread (the API stays responsive)."""

    def __init__(self, cfg: dict, oltp_path: str, severity: dict):
        self.cfg, self.oltp_path, self.severity = cfg, oltp_path, severity
        self.lock = threading.Lock()
        self.state = {"running": False, "mode": None, "steps": [], "error": None}

    @property
    def wh_path(self) -> str:
        return self.cfg["warehouse_path"]

    def start(self, mode: str) -> bool:
        if not self.lock.acquire(blocking=False):
            return False
        self.state = {"running": True, "mode": mode, "steps": [], "error": None,
                      "started_at": utcnow()}
        threading.Thread(target=self._run, args=(mode,), daemon=True).start()
        return True

    def _run(self, mode: str):
        try:
            if mode == "incremental" and Path(self.wh_path).exists():
                incremental_load(self.wh_path, self.oltp_path, self.state["steps"].append)
            else:
                self.state["mode"] = "full"
                full_load(self.wh_path, self.cfg["processed_dir"], self.cfg["raw_dir"],
                          self.oltp_path, self.severity, self.state["steps"].append)
        except Exception as e:  # shown on the ETL page
            self.state["error"] = f"{type(e).__name__}: {e}"
        finally:
            self.state["running"] = False
            self.lock.release()
