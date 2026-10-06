"""Test fixtures: a temporary DB, a tiny untrained bundle and a small replay file.

The API reads IDS_DB_URL / IDS_APP_CONFIG at import time, so they are set here
before anything from ids.api is imported.
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)  # configs/ and data/ paths are relative to the project root

TMP = Path(os.environ.get("PYTEST_IDS_TMP", ROOT / ".pytest_tmp"))
TMP.mkdir(exist_ok=True)
for f in TMP.glob("test.db*"):
    f.unlink()
os.environ["IDS_DB_URL"] = f"sqlite:///{(TMP / 'test.db').as_posix()}"
os.environ["IDS_APP_CONFIG"] = str(TMP / "app.yaml")


def _make_bundle(path: Path):
    """Random-weight CNN-LSTM with the REAL preprocessor, so shapes are realistic."""
    import torch

    from ids.bundle import build_bundle
    from ids.nn import CNNLSTM, save_model
    from ids.preprocessing import LabelEncoder, Preprocessor
    from ids.uncertainty import Mahalanobis

    art = ROOT / "artifacts/preprocessing"
    pre, enc = Preprocessor.load(art), LabelEncoder.load(art)
    torch.manual_seed(0)
    model = CNNLSTM(len(pre.feature_order), len(enc.classes))
    save_model(model, TMP / "_model")
    rng = np.random.default_rng(0)
    emb = rng.normal(size=(500, 128))
    ood = Mahalanobis().fit(emb, rng.integers(0, len(enc.classes), 500), len(enc.classes))
    # tiny random-forest second opinion (hybrid routing path)
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    rf = RandomForestClassifier(n_estimators=5, random_state=0).fit(
        rng.normal(size=(260, len(pre.feature_order))), np.arange(260) % len(enc.classes))
    joblib.dump(rf, TMP / "_rf.joblib")
    # thresholds low enough that some flows are routed to review
    build_bundle(path, TMP / "_model", art, 1.0, {}, ood,
                 {"entropy": 0.05, "distance": 1e9, "entropy_referral_rate": 0.01,
                  "distance_quantile": 0.995, "rf_uncertainty": 0.5, "rf_referral_rate": 0.005},
                 {"val_metrics": {"accuracy": 0.5, "macro_f1": 0.5, "macro_f1_reliable": 0.5,
                                  "binary": {"fpr": 0.1}},
                  "routing": {"referral_rate": 0.01}, "parent": None},
                 second_opinion_path=TMP / "_rf.joblib")


@pytest.fixture(scope="session")
def app_client():
    bundles = TMP / "bundles"
    if not (bundles / "v1").exists():
        _make_bundle(bundles / "v1")
    replay = TMP / "replay.parquet"
    if not replay.exists():
        df = pd.read_parquet(ROOT / "data/processed/replay.parquet")
        # a mix of benign and attacks
        pd.concat([df[df.hidden_label == "BENIGN"].head(150),
                   df[df.hidden_label != "BENIGN"].head(150)]).to_parquet(replay, index=False)

    cfg = yaml.safe_load(open(ROOT / "configs/app.yaml", encoding="utf-8"))
    cfg["bundle_dir"] = str(bundles)
    cfg["replay_file"] = str(replay)
    cfg["replay"]["mode"] = "sequential"
    cfg["retraining"].update(min_verified_feedback=4, base_train_rows=3000, epochs=1,
                             feedback_repeat=5, benchmark_max_rows=5000)
    (TMP / "app.yaml").write_text(yaml.safe_dump(cfg))

    from fastapi.testclient import TestClient

    from ids.api.main import app
    with TestClient(app) as c:
        yield c


def login(client, username, password):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


sys.modules[__name__].login = login
