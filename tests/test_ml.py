"""Unit tests for preprocessing, metrics and uncertainty (no API)."""

import numpy as np
import pandas as pd

from ids.metrics import compute_metrics
from ids.preprocessing import LabelEncoder, Preprocessor, signed_log1p
from ids.uncertainty import (AUTO_ALERT, AUTO_BENIGN, REVIEW, Mahalanobis, coverage_risk,
                             fit_temperature, normalized_entropy, route, softmax)


def test_signed_log1p_keeps_sign():
    x = np.array([[-10.0, 0.0, 10.0]], dtype="float32")
    out = signed_log1p(x.copy())
    assert out[0, 0] < 0 and out[0, 1] == 0 and out[0, 2] > 0
    assert np.isclose(out[0, 2], np.log1p(10))


def test_preprocessor_fit_transform_handles_inf_nan_and_drops_duplicates():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"a": rng.normal(size=200), "b": rng.normal(size=200)})
    df["a_copy"] = df["a"] * 2          # perfectly correlated -> dropped
    df["const"] = 5.0                   # constant -> dropped
    pre = Preprocessor(corr_threshold=0.99, corr_sample_rows=200).fit(df, list(df.columns))
    assert pre.feature_order == ["a", "b"]
    assert set(pre.dropped) == {"a_copy", "const"}
    bad = df.head(3).copy()
    bad.loc[0, "a"] = np.inf
    bad.loc[1, "b"] = np.nan
    X = pre.transform(bad)
    assert X.shape == (3, 2) and np.isfinite(X).all()


def test_saved_preprocessor_and_label_map():
    pre = Preprocessor.load("artifacts/preprocessing")
    enc = LabelEncoder.load("artifacts/preprocessing")
    assert enc.classes[0] == "BENIGN" and len(enc.classes) == 13
    assert "Dst Port" not in pre.feature_order and "Src IP" not in pre.candidate_cols
    assert enc.decode(enc.encode(["DDoS", "BENIGN"])) == ["DDoS", "BENIGN"]


def test_metrics_binary_view():
    classes = ["BENIGN", "A", "B"]
    y = np.array([0, 0, 1, 2, 2])
    p = np.array([0, 1, 1, 2, 0])          # 1 false alarm, 1 missed attack
    m = compute_metrics(y, p, classes)
    b = m["binary"]
    assert (b["tp"], b["fp"], b["tn"], b["fn"]) == (2, 1, 1, 1)
    assert np.isclose(b["fpr"], 0.5) and np.isclose(b["fnr"], 1 / 3)
    assert m["per_class"]["B"]["recall"] == 0.5


def test_temperature_softens_overconfident_logits():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 3, 2000)
    logits = rng.normal(size=(2000, 3))
    logits[np.arange(2000), y] += 1.0
    logits *= 8                            # far too confident for 1.0 margin
    assert fit_temperature(logits, y) > 2


def test_entropy_range_and_routing():
    p = softmax(np.array([[10.0, 0, 0], [0.0, 0, 0], [0, 10.0, 0]]))
    ent = normalized_entropy(p)
    assert ent[0] < 0.01 and np.isclose(ent[1], 1.0)
    dec = route(p.argmax(1), ent, np.array([0, 0, 99.0]), tau_entropy=0.5, tau_distance=10)
    assert list(dec) == [AUTO_BENIGN, REVIEW, REVIEW]
    dec = route(p.argmax(1), ent, np.zeros(3), tau_entropy=0.5, tau_distance=10)
    assert dec[2] == AUTO_ALERT


def test_mahalanobis_skips_missing_class_and_flags_outliers():
    rng = np.random.default_rng(0)
    emb = np.concatenate([rng.normal(0, 1, (300, 4)), rng.normal(5, 1, (300, 4))])
    y = np.r_[np.zeros(300, int), np.full(300, 2)]      # class 1 absent
    m = Mahalanobis().fit(emb, y, n_classes=3)
    assert m.means.shape == (2, 4)
    near, far = m.score(np.zeros((1, 4))), m.score(np.full((1, 4), 30.0))
    assert far[0] > 50 * near[0]


def test_coverage_risk_referring_uncertain_errors_lowers_risk():
    correct = np.array([True] * 90 + [False] * 10)
    unc = np.r_[np.zeros(90), np.ones(10)]              # errors are the uncertain ones
    r, risk = coverage_risk(unc, correct, n_points=101)
    assert np.isclose(risk[0], 0.10) and risk[np.searchsorted(r, 0.10)] == 0
