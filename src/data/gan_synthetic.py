# src/data/gan_synthetic.py
from __future__ import annotations
"""
Tiny GAN wrapper for synthetic return generation with graceful fallbacks.

- If PyTorch is missing, data is too short, or training errors:
    train_gan(...) -> {"gan_enabled": False, "reason": "..."}
    generate_synthetic_prices(...) falls back to AR(1)+bootstrap returns

- If PyTorch is present and data is sufficient:
    Trains a simple windowed MLP GAN on normalized returns and uses it
    to generate synthetic return windows that are stitched into a path.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
import numpy as np
import math
import warnings

# ---------------- Optional torch import ----------------
try:
    import torch
    from torch import nn
    TORCH_AVAILABLE = True
except Exception:
    torch, nn = None, None  # type: ignore
    TORCH_AVAILABLE = False


# ---------------- Utilities ----------------
def _to_returns(x: np.ndarray) -> np.ndarray:
    """Accept prices or returns; convert to simple returns if needed."""
    x = np.asarray(x, dtype=np.float32).flatten()
    if len(x) < 3:
        return x
    # Heuristic: treat as prices if positive and median > 1
    if np.all(x > 0) and float(np.nanmedian(x)) > 1.0:
        px = x
        r = np.diff(px) / px[:-1]
        return r.astype(np.float32)
    return x  # already returns

def _make_windows(r: np.ndarray, win: int) -> np.ndarray:
    """Sliding windows of returns, shape (n_windows, win)."""
    r = np.asarray(r, dtype=np.float32)
    if len(r) < win:
        return np.empty((0, win), dtype=np.float32)
    n = len(r) - win + 1
    X = np.stack([r[i:i+win] for i in range(n)], axis=0).astype(np.float32)
    return X

def _ar1_bootstrap(r: np.ndarray, n_steps: int, start_price: float = 100.0, seed: Optional[int] = None) -> np.ndarray:
    """Fallback generator: AR(1) mixed with bootstrapped shocks to keep fat tails."""
    rng = np.random.default_rng(seed)
    r = np.asarray(r, dtype=np.float32)
    if len(r) < 3:
        r = rng.normal(0.0, 0.01, size=512).astype(np.float32)

    mu = float(np.mean(r))
    var = float(np.var(r) + 1e-8)
    r0, r1 = r[:-1], r[1:]
    denom = float(np.dot(r0 - mu, r0 - mu) + 1e-8)
    phi = float(np.dot(r0 - mu, r1 - mu) / denom)
    eps_std = math.sqrt(max(1e-8, var * (1 - phi**2)))

    px = [float(start_price)]
    rt = mu
    for _ in range(n_steps):
        eps = rng.normal(0.0, eps_std)
        boot = float(rng.choice(r))
        rt = mu + phi * (rt - mu) + 0.5 * eps + 0.5 * (boot - mu)
        px.append(px[-1] * (1.0 + rt))
    return np.array(px, dtype=np.float32)


# ---------------- Public API ----------------
@dataclass
class GANHandle:
    gan_enabled: bool = False
    reason: str = "disabled"
    win: int = 0
    mu: float = 0.0
    sigma: float = 1.0
    G: Any = None          # torch.nn.Module
    device: str = "cpu"
    latent_dim: int = 32


def train_gan(
    real_prices_or_returns: np.ndarray,
    *,
    window: int = 64,
    latent_dim: int = 32,
    n_epochs: int = 50,
    batch_size: int = 64,
    lr: float = 2e-4,
    seed: Optional[int] = 42,
) -> Dict[str, Any]:
    """
    Train a tiny MLP GAN on sliding windows of returns.
    Returns a dict usable by generate_synthetic_prices. Auto-disables on issues.
    """
    r = _to_returns(np.asarray(real_prices_or_returns, dtype=np.float32))
    X = _make_windows(r, window)

    if not TORCH_AVAILABLE:
        return {"gan_enabled": False, "reason": "torch_not_available"}
    if X.shape[0] < max(256, batch_size):
        return {"gan_enabled": False, "reason": f"not_enough_windows_{X.shape[0]}<256"}

    # Normalize windows
    mu = float(np.mean(X))
    sigma = float(np.std(X) + 1e-8)
    Xn = (X - mu) / sigma

    # Torch setup
    torch.manual_seed(seed or 42)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    ds = torch.utils.data.TensorDataset(torch.tensor(Xn, dtype=torch.float32))
    dl = torch.utils.data.DataLoader(ds, batch_size=batch_size, shuffle=True, drop_last=True)

    # Models sized to 'window' (fixes your matmul shape error)
    class Generator(nn.Module):  # type: ignore[misc]
        def __init__(self, zdim: int, out_dim: int):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(zdim, 128), nn.LeakyReLU(0.2),
                nn.Linear(128, 128), nn.LeakyReLU(0.2),
                nn.Linear(128, out_dim),
            )
        def forward(self, z):
            return self.net(z)

    class Discriminator(nn.Module):  # type: ignore[misc]
        def __init__(self, in_dim: int):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(in_dim, 128), nn.LeakyReLU(0.2),
                nn.Linear(128, 64), nn.LeakyReLU(0.2),
                nn.Linear(64, 1), nn.Sigmoid(),
            )
        def forward(self, x):
            return self.net(x)

    G, D = Generator(latent_dim, window).to(device), Discriminator(window).to(device)
    optG = torch.optim.Adam(G.parameters(), lr=lr, betas=(0.5, 0.999))
    optD = torch.optim.Adam(D.parameters(), lr=lr, betas=(0.5, 0.999))
    bce = nn.BCELoss()

    try:
        for _ in range(max(1, n_epochs)):
            for (xb,) in dl:
                xb = xb.to(device)
                bs = xb.size(0)

                # ----- Train D -----
                z = torch.randn(bs, latent_dim, device=device)
                fake = G(z).detach()
                D_real = D(xb)
                D_fake = D(fake)
                lossD = bce(D_real, torch.ones_like(D_real)) + bce(D_fake, torch.zeros_like(D_fake))
                optD.zero_grad(); lossD.backward(); optD.step()

                # ----- Train G -----
                z = torch.randn(bs, latent_dim, device=device)
                fake = G(z)
                D_fake = D(fake)
                lossG = bce(D_fake, torch.ones_like(D_fake))
                optG.zero_grad(); lossG.backward(); optG.step()

    except Exception as e:
        warnings.warn(f"GAN training failed: {e}")
        return {"gan_enabled": False, "reason": f"train_error:{e}"}

    return {
        "gan_enabled": True,
        "reason": "ok",
        "win": int(window),
        "mu": float(mu),
        "sigma": float(sigma),
        "G": G.eval(),
        "device": device,
        "latent_dim": int(latent_dim),
    }


def generate_synthetic_prices(
    n_steps: int,
    *,
    start_price: float = 100.0,
    gan: Optional[Dict[str, Any]] = None,
    seed: Optional[int] = 123,
    real_prices_or_returns: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Generate a synthetic price path of length n_steps+1 (including start).
    If a trained GAN handle is provided and enabled, use it; otherwise fallback.
    """
    # Fallback path (no GAN or disabled)
    if not gan or not gan.get("gan_enabled"):
        r = real_prices_or_returns if real_prices_or_returns is not None else np.array([0.0], dtype=np.float32)
        return _ar1_bootstrap(_to_returns(r), n_steps=n_steps, start_price=start_price, seed=seed)

    # GAN path
    if not TORCH_AVAILABLE:
        r = real_prices_or_returns if real_prices_or_returns is not None else np.array([0.0], dtype=np.float32)
        return _ar1_bootstrap(_to_returns(r), n_steps=n_steps, start_price=start_price, seed=seed)

    G = gan["G"]
    device = gan.get("device", "cpu")
    latent_dim = int(gan.get("latent_dim", 32))
    win = int(gan.get("win", 64))
    mu = float(gan.get("mu", 0.0))
    sigma = float(gan.get("sigma", 1.0))

    # How many windows do we need to cover n_steps returns?
    # We'll overlap by (win-1) so concatenate windows smoothly.
    if n_steps <= 0:
        return np.array([start_price], dtype=np.float32)

    n_windows = max(1, math.ceil(n_steps / win))
    returns: list[float] = []

    with torch.no_grad():
        for _ in range(n_windows):
            z = torch.randn(1, latent_dim, device=device)
            win_norm = G(z).cpu().numpy().reshape(-1)          # normalized returns
            win_real = win_norm * sigma + mu                    # de-normalize
            returns.extend(win_real.tolist())

    # Trim to exactly n_steps
    returns = np.array(returns[:n_steps], dtype=np.float32)

    # Build price path from returns
    prices = [float(start_price)]
    for r in returns:
        prices.append(prices[-1] * (1.0 + float(r)))

    return np.array(prices, dtype=np.float32)
