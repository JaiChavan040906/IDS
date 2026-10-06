"""Stage 5 - calibration, uncertainty signals and the routing policy.

Two uncertainty signals:
  1. entropy of the temperature-scaled softmax, divided by log(K) so it is in [0, 1].
     High = the model hesitates between classes.
  2. Mahalanobis distance of the 128-d embedding to the nearest class centre
     (Lee et al. 2018). High = the flow looks unlike ANY training class,
     which is what an unseen attack often looks like even when the softmax is
     confidently wrong.

3. (hybrid, optional) a Random Forest "second opinion": its own uncertainty
     (1 - max vote share), and whether it disagrees with the CNN-LSTM. Added
     after leave-one-attack-out showed the tree ensemble notices unseen attacks
     far more often than the network does.

Routing (per flow):
  review       if entropy > tau_entropy or distance > tau_distance
               or (hybrid) RF uncertainty > tau_rf or RF class != CNN-LSTM class
  auto_alert   else, if predicted class != BENIGN
  auto_benign  else
"""

import numpy as np
import torch

REVIEW, AUTO_ALERT, AUTO_BENIGN = "review", "auto_alert", "auto_benign"


def softmax(logits: np.ndarray, T: float = 1.0) -> np.ndarray:
    z = logits / T
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def fit_temperature(logits: np.ndarray, y: np.ndarray, max_iter: int = 200) -> float:
    """One scalar T minimising validation NLL. T > 1 softens over-confident models."""
    lt = torch.from_numpy(logits.astype("float64"))
    yt = torch.from_numpy(y.astype("int64"))
    log_t = torch.zeros(1, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=max_iter)

    def closure():
        opt.zero_grad()
        loss = torch.nn.functional.cross_entropy(lt / log_t.exp(), yt)
        loss.backward()
        return loss

    opt.step(closure)
    return float(log_t.detach().exp())


def normalized_entropy(p: np.ndarray) -> np.ndarray:
    ent = -(p * np.log(np.clip(p, 1e-12, 1))).sum(axis=1)
    return ent / np.log(p.shape[1])


def nll(p: np.ndarray, y: np.ndarray) -> float:
    return float(-np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1)).mean())


def ece(p: np.ndarray, y: np.ndarray, n_bins: int = 15) -> tuple[float, list]:
    """Expected calibration error: avg |accuracy - confidence| over confidence bins."""
    conf, pred = p.max(1), p.argmax(1)
    correct = pred == y
    edges = np.linspace(0, 1, n_bins + 1)
    total, bins = 0.0, []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            acc, cf = correct[m].mean(), conf[m].mean()
            total += m.mean() * abs(acc - cf)
            bins.append({"lo": lo, "hi": hi, "n": int(m.sum()), "acc": float(acc),
                         "conf": float(cf)})
    return float(total), bins


class Mahalanobis:
    """Class-conditional Gaussians with one shared covariance, fit on TRAIN embeddings."""

    def fit(self, emb: np.ndarray, y: np.ndarray, n_classes: int, shrinkage: float = 1e-3):
        """Classes with no rows (e.g. the held-out attack in leave-one-attack-out)
        simply get no centre."""
        emb = emb.astype("float64")
        present = [c for c in range(n_classes) if (y == c).any()]
        self.means = np.stack([emb[y == c].mean(0) for c in present])
        pos = np.full(n_classes, -1)
        pos[present] = np.arange(len(present))
        centered = emb - self.means[pos[y]]
        cov = centered.T @ centered / len(emb)
        cov += shrinkage * np.trace(cov) / cov.shape[0] * np.eye(cov.shape[0])
        self.precision = np.linalg.inv(cov)
        return self

    def score(self, emb: np.ndarray, batch: int = 8192) -> np.ndarray:
        """Min squared distance to any class centre (higher = more unusual)."""
        out = np.empty(len(emb))
        for i in range(0, len(emb), batch):
            d = emb[i:i + batch, None, :].astype("float64") - self.means[None]
            out[i:i + batch] = np.einsum("nkd,de,nke->nk", d, self.precision, d).min(1)
        return out

    def to_dict(self):
        return {"means": self.means, "precision": self.precision}

    @classmethod
    def from_arrays(cls, means, precision):
        m = cls()
        m.means, m.precision = means, precision
        return m


def fit_uncertainty(emb_train: np.ndarray, y_train: np.ndarray, logits_cal: np.ndarray,
                    emb_cal: np.ndarray, y_cal: np.ndarray, n_classes: int, cfg: dict):
    """Everything Stage 5 fits, in one place (used by calibrate.py and retraining).

    emb_train/y_train -> Mahalanobis centres; *_cal (validation "cal" half) ->
    temperature and routing thresholds. Returns (T, ood, thresholds).
    """
    ood = Mahalanobis().fit(emb_train, y_train, n_classes)
    T = fit_temperature(logits_cal, y_cal)
    ent = normalized_entropy(softmax(logits_cal, T))
    thresholds = {
        "entropy": float(np.quantile(ent, 1 - cfg["entropy_referral_rate"])),
        "distance": float(np.quantile(ood.score(emb_cal), cfg["distance_quantile"])),
        "entropy_referral_rate": cfg["entropy_referral_rate"],
        "distance_quantile": cfg["distance_quantile"],
    }
    return T, ood, thresholds


def second_opinion(rf_probs: np.ndarray, rf_classes: np.ndarray, cnn_pred: np.ndarray,
                   tau_rf: float) -> dict:
    """RF view of each flow: its class, its uncertainty, and the review mask."""
    rf_pred = rf_classes[rf_probs.argmax(1)]
    unc = 1 - rf_probs.max(1)
    unsure, disagree = unc > tau_rf, rf_pred != cnn_pred
    return {"rf_pred": rf_pred, "rf_uncertainty": unc, "rf_unsure": unsure,
            "disagree": disagree, "mask": unsure | disagree}


def mahalanobis_sample(y: np.ndarray, n_rows: int, seed: int, rare_below: int = 5000):
    """Random subset of train indices for fitting class centres, plus ALL rows of
    rare classes so every class (even Heartbleed) gets a centre."""
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(y), min(n_rows, len(y)), replace=False)
    rare = np.nonzero(np.bincount(y) < rare_below)[0]
    return np.union1d(idx, np.nonzero(np.isin(y, rare))[0])


def route(pred: np.ndarray, entropy: np.ndarray, distance: np.ndarray,
          tau_entropy: float, tau_distance: float, benign: int = 0,
          extra_unsure: np.ndarray | None = None) -> np.ndarray:
    """extra_unsure: any additional "send to review" mask (the RF second opinion)."""
    unsure = (entropy > tau_entropy) | (distance > tau_distance)
    if extra_unsure is not None:
        unsure = unsure | extra_unsure
    out = np.where(pred == benign, AUTO_BENIGN, AUTO_ALERT).astype(object)
    out[unsure] = REVIEW
    return out


def coverage_risk(uncertainty: np.ndarray, correct: np.ndarray, n_points: int = 200):
    """Sort by uncertainty; for each referral rate r, error rate on the rest.

    Returns arrays (referral_rate, risk_on_auto_handled).
    """
    order = np.argsort(-uncertainty)           # most uncertain first -> referred first
    err = ~correct[order]
    n = len(err)
    cum_err_remaining = err[::-1].cumsum()[::-1]  # errors among items i..n-1
    ks = np.unique(np.linspace(0, n - 1, n_points).astype(int))
    referral = ks / n
    risk = cum_err_remaining[ks] / (n - ks)
    return referral, risk
