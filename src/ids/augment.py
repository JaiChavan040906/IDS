"""Conditional WGAN-GP for minority-class augmentation (paper: VAE seeds -> cWGAN-GP).

Simplification vs the paper: the generator starts from Gaussian noise instead of
VAE-encoded seeds. Everything happens in the TRANSFORMED feature space (after the
fitted Preprocessor), and only TRAIN rows are ever used.

WGAN-GP in one paragraph: a critic D scores how "real" a sample looks; the
generator G tries to raise its score. The gradient penalty keeps D smooth
(|grad D| ~ 1), which makes training far more stable than a classic GAN.
Conditioning = both networks also receive the class, so G can be asked for
"a Botnet flow".
"""

import numpy as np
import torch
from torch import nn

from ids.nn import DEVICE, set_seed


class Generator(nn.Module):
    def __init__(self, n_features, n_classes, z_dim=32, hidden=256):
        super().__init__()
        self.z_dim = z_dim
        self.emb = nn.Embedding(n_classes, 16)
        self.net = nn.Sequential(
            nn.Linear(z_dim + 16, hidden), nn.LeakyReLU(0.2),
            nn.Linear(hidden, hidden), nn.LeakyReLU(0.2),
            nn.Linear(hidden, n_features))

    def forward(self, z, c):
        return self.net(torch.cat([z, self.emb(c)], dim=1))


class Critic(nn.Module):
    def __init__(self, n_features, n_classes, hidden=256):
        super().__init__()
        self.emb = nn.Embedding(n_classes, 16)
        self.net = nn.Sequential(
            nn.Linear(n_features + 16, hidden), nn.LeakyReLU(0.2),
            nn.Linear(hidden, hidden), nn.LeakyReLU(0.2),
            nn.Linear(hidden, 1))

    def forward(self, x, c):
        return self.net(torch.cat([x, self.emb(c)], dim=1))


def gradient_penalty(D, real, fake, c):
    a = torch.rand(len(real), 1, device=real.device)
    mix = (a * real + (1 - a) * fake).requires_grad_(True)
    grad = torch.autograd.grad(D(mix, c).sum(), mix, create_graph=True)[0]
    return ((grad.norm(2, dim=1) - 1) ** 2).mean()


def train_cwgan(X: np.ndarray, y: np.ndarray, n_classes: int, cfg: dict, seed: int, log=print):
    """X, y = real minority rows (train split only). Returns generator + loss history."""
    set_seed(seed)
    G = Generator(X.shape[1], n_classes, cfg["z_dim"]).to(DEVICE)
    D = Critic(X.shape[1], n_classes).to(DEVICE)
    opt_g = torch.optim.Adam(G.parameters(), lr=cfg["lr"], betas=(0.5, 0.9))
    opt_d = torch.optim.Adam(D.parameters(), lr=cfg["lr"], betas=(0.5, 0.9))
    Xt, yt = torch.from_numpy(X).to(DEVICE), torch.from_numpy(y).to(DEVICE)

    # Sample classes uniformly so small classes get as many updates as bigger ones.
    by_class = {int(c): torch.nonzero(yt == c).squeeze(1) for c in np.unique(y)}
    classes = torch.tensor(list(by_class), device=DEVICE)

    def real_batch(n):
        cs = classes[torch.randint(len(classes), (n,), device=DEVICE)]
        idx = torch.empty(n, dtype=torch.long, device=DEVICE)
        for c, pool in by_class.items():
            m = cs == c
            idx[m] = pool[torch.randint(len(pool), (int(m.sum()),), device=DEVICE)]
        return Xt[idx], cs

    history = []
    bs = cfg["batch_size"]
    for it in range(1, cfg["iterations"] + 1):
        for _ in range(cfg["n_critic"]):
            real, c = real_batch(bs)
            fake = G(torch.randn(bs, G.z_dim, device=DEVICE), c).detach()
            loss_d = (D(fake, c).mean() - D(real, c).mean()
                      + cfg["gp_lambda"] * gradient_penalty(D, real, fake, c))
            opt_d.zero_grad(set_to_none=True)
            loss_d.backward()
            opt_d.step()
        _, c = real_batch(bs)
        loss_g = -D(G(torch.randn(bs, G.z_dim, device=DEVICE), c), c).mean()
        opt_g.zero_grad(set_to_none=True)
        loss_g.backward()
        opt_g.step()
        if it % cfg["log_every"] == 0:
            # -loss_d without the penalty ~ Wasserstein distance estimate (should shrink).
            history.append({"iter": it, "loss_d": loss_d.item(), "loss_g": loss_g.item()})
            log(f"  iter {it:5d}  critic {loss_d.item():+.4f}  gen {loss_g.item():+.4f}")
    return G.eval(), history


@torch.no_grad()
def sample(G: Generator, cls: int, n: int, batch: int = 8192) -> np.ndarray:
    out = []
    for i in range(0, n, batch):
        k = min(batch, n - i)
        c = torch.full((k,), cls, dtype=torch.long, device=DEVICE)
        out.append(G(torch.randn(k, G.z_dim, device=DEVICE), c).cpu())
    return torch.cat(out).numpy().astype("float32")
