"""External CSV import: column-name matching, label mapping, unlabelled files, and the
upload -> replay -> per-source evaluation path through the API."""

import io

import pandas as pd

from conftest import ROOT, TMP, login
from ids.data import load_config
from ids.flow_import import UNLABELLED, canon, import_flows, map_label
from ids.preprocessing import Preprocessor

# Column names exactly as written in the original CSE-CIC-IDS2018 CSVs
CIC2018 = ("Dst Port,Protocol,Timestamp,Flow Duration,Tot Fwd Pkts,Tot Bwd Pkts,TotLen Fwd Pkts,TotLen Bwd Pkts,"
           "Fwd Pkt Len Max,Fwd Pkt Len Min,Fwd Pkt Len Mean,Fwd Pkt Len Std,Bwd Pkt Len Max,Bwd Pkt Len Min,"
           "Bwd Pkt Len Mean,Bwd Pkt Len Std,Flow Byts/s,Flow Pkts/s,Flow IAT Mean,Flow IAT Std,Flow IAT Max,"
           "Flow IAT Min,Fwd IAT Tot,Fwd IAT Mean,Fwd IAT Std,Fwd IAT Max,Fwd IAT Min,Bwd IAT Tot,Bwd IAT Mean,"
           "Bwd IAT Std,Bwd IAT Max,Bwd IAT Min,Fwd PSH Flags,Bwd PSH Flags,Fwd URG Flags,Bwd URG Flags,"
           "Fwd Header Len,Bwd Header Len,Fwd Pkts/s,Bwd Pkts/s,Pkt Len Min,Pkt Len Max,Pkt Len Mean,Pkt Len Std,"
           "Pkt Len Var,FIN Flag Cnt,SYN Flag Cnt,RST Flag Cnt,PSH Flag Cnt,ACK Flag Cnt,URG Flag Cnt,"
           "CWE Flag Count,ECE Flag Cnt,Down/Up Ratio,Pkt Size Avg,Fwd Seg Size Avg,Bwd Seg Size Avg,"
           "Fwd Byts/b Avg,Fwd Pkts/b Avg,Fwd Blk Rate Avg,Bwd Byts/b Avg,Bwd Pkts/b Avg,Bwd Blk Rate Avg,"
           "Subflow Fwd Pkts,Subflow Fwd Byts,Subflow Bwd Pkts,Subflow Bwd Byts,Init Fwd Win Byts,"
           "Init Bwd Win Byts,Fwd Act Data Pkts,Fwd Seg Size Min,Active Mean,Active Std,Active Max,Active Min,"
           "Idle Mean,Idle Std,Idle Max,Idle Min,Label").split(",")
LABELS_2018 = {"BENIGN": "Benign", "DDoS": "DDOS attack-HOIC", "DoS Hulk": "DoS attacks-Hulk",
               "Portscan": "Infilteration", "FTP-Patator": "FTP-BruteForce"}


def make_2018_style_csv(path, n=400, labelled=True):
    """Real flows from our replay file, re-written with 2018 column names and labels."""
    pre = Preprocessor.load(ROOT / "artifacts/preprocessing")
    df = pd.read_parquet(ROOT / "data/processed/replay.parquet")
    df = pd.concat([df[df.hidden_label == "BENIGN"].head(n // 2), df[df.hidden_label != "BENIGN"].head(n // 2)])
    ours = {canon(c): c for c in [*pre.candidate_cols, "Dst Port", "Timestamp"]}
    out = pd.DataFrame({c: df[ours[canon(c)]].to_numpy() for c in CIC2018 if canon(c) in ours})
    if labelled:
        out["Label"] = [LABELS_2018.get(x, "Brute Force -XSS") for x in df.hidden_label]
    out.to_csv(path, index=False)
    return out


def test_label_mapping_covers_2018_names():
    lm = load_config()["label_map"]
    assert map_label("Benign", lm) == "BENIGN"
    assert map_label("DDOS attack-LOIC-UDP", lm) == "DDoS"
    assert map_label("DoS attacks-SlowHTTPTest", lm) == "DoS Slowhttptest"
    assert map_label("SSH-Bruteforce", lm) == "SSH-Patator"
    assert map_label("Brute Force -Web", lm) == "Web Attack"
    assert map_label("Bot", lm) == "Botnet"
    assert map_label("Something New", lm) == "Something New"
    assert map_label("", lm) == UNLABELLED


def test_import_2018_style_csv(tmp_path):
    src = tmp_path / "wed-2018.csv"
    make_2018_style_csv(src)
    pre = Preprocessor.load(ROOT / "artifacts/preprocessing")
    meta = import_flows(src, pre.candidate_cols, load_config()["label_map"], tmp_path / "out")
    assert meta["features_found"] == 77 and meta["rows_kept"] == 400 and meta["labelled"]
    assert set(meta["features_missing"]) == {"Fwd RST Flags", "Bwd RST Flags", "ICMP Code", "ICMP Type",
                                             "Total TCP Flow Time"}
    assert meta["label_counts"]["BENIGN"] == 200
    df = pd.read_parquet(tmp_path / "out" / f"{meta['id']}.parquet")
    X = pre.transform(df)                       # missing columns are imputed, not an error
    assert X.shape == (400, len(pre.feature_order))


def test_import_rejects_or_warns_on_low_coverage(tmp_path):
    import pytest
    pre = Preprocessor.load(ROOT / "artifacts/preprocessing")
    lm = load_config()["label_map"]
    full = make_2018_style_csv(tmp_path / "full.csv", n=40)
    # unrelated data: refused with an explanation
    pd.DataFrame({"student": ["a", "b"], "marks": [90, 80]}).to_csv(tmp_path / "marks.csv", index=False)
    with pytest.raises(ValueError, match="CICFlowMeter"):
        import_flows(tmp_path / "marks.csv", pre.candidate_cols, lm, tmp_path / "out")
    # only ~20 flow columns: still refused
    full.iloc[:, :20].to_csv(tmp_path / "few.csv", index=False)
    with pytest.raises(ValueError, match="required measurements"):
        import_flows(tmp_path / "few.csv", pre.candidate_cols, lm, tmp_path / "out")
    # ~60 of 82 columns: accepted with a warning
    full.iloc[:, :62].join(full[["Label"]]).to_csv(tmp_path / "partial.csv", index=False)
    meta = import_flows(tmp_path / "partial.csv", pre.candidate_cols, lm, tmp_path / "out")
    assert meta["quality"] == "partial" and meta["quality_note"]
    # extra unknown columns are ignored, not fatal
    full.assign(MyCustomColumn=1, AnotherOne="x").to_csv(tmp_path / "extra.csv", index=False)
    meta = import_flows(tmp_path / "extra.csv", pre.candidate_cols, lm, tmp_path / "out")
    assert meta["quality"] == "good" and {"MyCustomColumn", "AnotherOne"} <= set(meta["columns_ignored"])


def test_import_unlabelled_and_sampling(tmp_path):
    src = tmp_path / "capture.csv"
    make_2018_style_csv(src, n=400, labelled=False)
    pre = Preprocessor.load(ROOT / "artifacts/preprocessing")
    meta = import_flows(src, pre.candidate_cols, {}, tmp_path / "out", max_rows=100)
    assert not meta["labelled"] and meta["sampled"] and 50 < meta["rows_kept"] < 160


def test_upload_replay_and_evaluate(app_client):
    c = app_client
    hadm, ha = login(c, "admin", "admin123"), login(c, "analyst", "analyst123")
    path = TMP / "upload-2018.csv"
    make_2018_style_csv(path)
    with open(path, "rb") as f:
        r = c.post("/api/admin/datasets", headers=hadm,
                   files={"file": ("upload-2018.csv", io.BytesIO(f.read()), "text/csv")})
    assert r.status_code == 200, r.text
    ds = r.json()
    assert ds["features_found"] == 77
    assert c.post("/api/admin/datasets", headers=ha, files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")}).status_code == 403
    bad = c.post("/api/admin/datasets", headers=hadm, files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
    assert bad.status_code == 400

    st = c.post("/api/admin/replay", headers=hadm, json={"action": "configure", "source": ds["id"]}).json()
    assert st["source"] == ds["id"] and st["total"] == 400
    c.app.state.replay.step(400)
    live = c.get("/api/admin/evaluation", headers=hadm).json()["live"]
    row = next(x for x in live if x["source"] == ds["id"])
    assert row["flows"] == 400 and row["attacks"] == 200 and row["detection_rate"] is not None
    for text in (c.get("/api/alerts", params={"status": "all"}, headers=ha).text,):
        assert "hidden_label" not in text

    assert c.delete(f"/api/admin/datasets/{ds['id']}", headers=hadm).status_code == 400   # in use
    c.post("/api/admin/replay", headers=hadm, json={"action": "configure", "source": "test"})
    assert c.delete(f"/api/admin/datasets/{ds['id']}", headers=hadm).status_code == 200
    assert c.post("/api/admin/replay", headers=hadm,
                  json={"action": "configure", "source": "nope"}).status_code == 400
