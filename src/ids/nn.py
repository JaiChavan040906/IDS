"""CNN-LSTM classifier (paper, Table 5) + training loop + inference helpers.

Architecture (input = our 64 selected features, the paper used 46):
    x (B, F) -> (B, 1, F)
    Conv1D(64, k=5, ReLU) -> MaxPool(2) -> Conv1D(128, k=3, ReLU)
    -> LSTM(128) over the pooled feature axis -> last hidden state
    -> Dropout(0.3) -> Dense(n_classes)       (softmax is applied outside)

The 128-d vector before the final Dense layer is the "embedding"; Stage 5 uses
it for out-of-distribution scoring (Mahalanobis distance).
"""

import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class CNNLSTM(nn.Module):
    def __init__(self, n_features: int, n_classes: int, use_lstm: bool = True,
                 dropout: float = 0.3):
        super().__init__()
        self.config = {"n_features": n_features, "n_classes": n_classes,
                       "use_lstm": use_lstm, "dropout": dropout}
        self.conv = nn.Sequential(
            nn.Conv1d(1, 64, kernel_size=5, padding=2), nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(64, 128, kernel_size=3, padding=1), nn.ReLU(),
        )
        self.use_lstm = use_lstm
        if use_lstm:
            self.lstm = nn.LSTM(128, 128, batch_first=True)
        self.dropout = nn.Dropout(dropout)
        self.head = nn.Linear(128, n_classes)

    def embed(self, x: torch.Tensor) -> torch.Tensor:
        h = self.conv(x.unsqueeze(1))            # (B, 128, F/2)
        if self.use_lstm:
            _, (hn, _) = self.lstm(h.transpose(1, 2))
            return hn[-1]                        # (B, 128)
        return h.mean(dim=2)                     # ablation: no LSTM -> global average

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.dropout(self.embed(x)))


def set_seed(seed: int):
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


@torch.no_grad()
def predict(model: CNNLSTM, X: np.ndarray, batch: int = 2048,
            with_embeddings: bool = False):
    """Returns logits (N, K) and optionally embeddings (N, 128) as numpy."""
    model.eval()
    logits, embs = [], []
    for i in range(0, len(X), batch):
        xb = torch.from_numpy(X[i:i + batch]).to(DEVICE)
        e = model.embed(xb)
        logits.append(model.head(e).float().cpu())
        if with_embeddings:
            embs.append(e.float().cpu())
    out = torch.cat(logits).numpy()
    return (out, torch.cat(embs).numpy()) if with_embeddings else out


def train(X: np.ndarray, y: np.ndarray, Xv: np.ndarray, yv: np.ndarray, n_classes: int,
          cfg: dict, seed: int, use_lstm: bool = True, log=print):
    """Plain cross-entropy (no class weights, so probabilities stay calibratable).

    Classes with fewer than cfg["min_class_rows"] training rows are randomly
    oversampled (rows repeated) up to that count - TRAIN only. Without this the
    network ignores Heartbleed (8 rows) / Infiltration (46 rows) entirely.

    Early stopping on validation macro-F1. Returns (best model, history).
    """
    from sklearn.metrics import f1_score

    set_seed(seed)
    min_rows = cfg.get("min_class_rows", 0)
    if min_rows:
        rng = np.random.default_rng(seed)
        extra = [rng.choice(np.nonzero(y == c)[0], min_rows - n)
                 for c, n in enumerate(np.bincount(y, minlength=n_classes)) if 0 < n < min_rows]
        if extra:
            extra = np.concatenate(extra)
            X, y = np.concatenate([X, X[extra]]), np.concatenate([y, y[extra]])
            log(f"  oversampled {len(extra):,} rows of classes with < {min_rows} rows")

    model = CNNLSTM(X.shape[1], n_classes, use_lstm, cfg["dropout"]).to(DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg["lr"], weight_decay=cfg["weight_decay"])
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=cfg["max_epochs"])
    loss_fn = nn.CrossEntropyLoss()

    # Whole training set lives on the GPU (1.2M x 64 floats = ~300 MB).
    Xt = torch.from_numpy(X).to(DEVICE)
    yt = torch.from_numpy(y).to(DEVICE)
    g = torch.Generator(device=DEVICE).manual_seed(seed)

    best, best_state, bad, history = -1.0, None, 0, []
    for epoch in range(1, cfg["max_epochs"] + 1):
        model.train()
        t0, total = time.time(), 0.0
        perm = torch.randperm(len(Xt), device=DEVICE, generator=g)
        for i in range(0, len(perm), cfg["batch_size"]):
            idx = perm[i:i + cfg["batch_size"]]
            opt.zero_grad(set_to_none=True)
            loss = loss_fn(model(Xt[idx]), yt[idx])
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            total += loss.item() * len(idx)
        sched.step()

        pv = predict(model, Xv).argmax(1)
        per = f1_score(yv, pv, average=None, labels=np.arange(n_classes), zero_division=0)
        f1 = float(per.mean())
        history.append({"epoch": epoch, "train_loss": total / len(Xt), "val_macro_f1": f1,
                        "val_f1_per_class": per.round(4).tolist(),
                        "seconds": round(time.time() - t0, 1)})
        log(f"  epoch {epoch:2d} loss {total / len(Xt):.5f} val macroF1 {f1:.4f} "
            f"(worst class {per.argmin()}: {per.min():.3f}) ({time.time() - t0:.0f}s)")
        if f1 > best:
            best, bad = f1, 0
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= cfg["patience"]:
                break
    model.load_state_dict(best_state)
    del Xt, yt
    torch.cuda.empty_cache()
    return model, history


def fine_tune(model: CNNLSTM, X: np.ndarray, y: np.ndarray, epochs: int, lr: float,
              seed: int, batch_size: int = 1024, log=print) -> CNNLSTM:
    """Continue training an existing model (retraining). No early stopping: the
    candidate is judged afterwards against fixed acceptance criteria."""
    set_seed(seed)
    model = model.to(DEVICE).train()
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss()
    Xt, yt = torch.from_numpy(X).to(DEVICE), torch.from_numpy(y).to(DEVICE)
    g = torch.Generator(device=DEVICE).manual_seed(seed)
    for epoch in range(1, epochs + 1):
        total = 0.0
        perm = torch.randperm(len(Xt), device=DEVICE, generator=g)
        for i in range(0, len(perm), batch_size):
            idx = perm[i:i + batch_size]
            opt.zero_grad(set_to_none=True)
            loss = loss_fn(model(Xt[idx]), yt[idx])
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            total += loss.item() * len(idx)
        log(f"fine-tune epoch {epoch}/{epochs}: loss {total / len(Xt):.5f}")
    del Xt, yt
    if DEVICE.type == "cuda":
        torch.cuda.empty_cache()
    return model.eval()


def save_model(model: CNNLSTM, directory: str | Path):
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), d / "model.pt")
    (d / "model_config.json").write_text(json.dumps(model.config, indent=2))


def load_model(directory: str | Path, device=DEVICE) -> CNNLSTM:
    d = Path(directory)
    model = CNNLSTM(**json.loads((d / "model_config.json").read_text()))
    model.load_state_dict(torch.load(d / "model.pt", map_location=device, weights_only=True))
    return model.to(device).eval()
