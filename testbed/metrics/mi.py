"""Discrete (conditional) mutual information: plug-in, Miller-Madow, permutation nulls.

All quantities are in bits. Conditional MI is computed from four joint
entropies, I(X;Y|Z) = H(X,Z) + H(Y,Z) - H(X,Y,Z) - H(Z), each with the
Miller-Madow correction (m - 1) / (2 n ln 2), m = number of occupied cells.
Corrected estimates can be slightly negative; they are not clipped.

The permutation null shuffles X within strata (for example within runs) and
recomputes the statistic, vectorised over permutations: ``x`` may be a 2-D
array [n_perm, n] of permuted copies.
"""
from __future__ import annotations

import numpy as np

LN2 = np.log(2.0)


def compress(*cols: np.ndarray) -> tuple[np.ndarray, int]:
    """Map the joint value of several integer columns to codes 0..L-1."""
    if not cols:
        raise ValueError("need at least one column")
    if len(cols) == 1:
        _, inv = np.unique(np.asarray(cols[0]).ravel(), return_inverse=True)
        return inv.astype(np.int64), int(inv.max()) + 1 if inv.size else 0
    stack = np.stack([np.asarray(c).ravel() for c in cols], axis=1)
    _, inv = np.unique(stack, axis=0, return_inverse=True)
    inv = inv.ravel()
    return inv.astype(np.int64), int(inv.max()) + 1 if inv.size else 0


def _entropy(codes: np.ndarray, n_cells: int, mm: bool) -> np.ndarray:
    """Entropy (bits) of each row of a 2-D code array."""
    codes = np.atleast_2d(codes)
    P, n = codes.shape
    flat = (codes + np.arange(P)[:, None] * n_cells).ravel()
    counts = np.bincount(flat, minlength=P * n_cells).reshape(P, n_cells).astype(float)
    nz = counts > 0
    plogp = np.where(nz, counts * np.log2(np.where(nz, counts, 1.0)), 0.0).sum(axis=1)
    h = np.log2(n) - plogp / n
    if mm:
        h = h + (nz.sum(axis=1) - 1) / (2.0 * n * LN2)
    return h


def cmi(x: np.ndarray, y: np.ndarray, z: np.ndarray | None = None, mm: bool = True) -> np.ndarray | float:
    """I(X;Y|Z) in bits. ``x`` may be [n] or [P, n] (P permuted copies)."""
    x = np.asarray(x)
    single = x.ndim == 1
    x2 = np.atleast_2d(x)
    n = x2.shape[1]
    if n == 0:
        return np.nan if single else np.full(x2.shape[0], np.nan)
    xs, nx = compress(x2.ravel())
    xs = xs.reshape(x2.shape)
    ys, ny = compress(y)
    if z is None:
        zs, nz_ = np.zeros(n, dtype=np.int64), 1
    else:
        zs, nz_ = compress(z)
    h_z = _entropy(zs[None, :], nz_, mm)
    h_yz = _entropy((ys * nz_ + zs)[None, :], ny * nz_, mm)
    h_xz = _entropy(xs * nz_ + zs[None, :], nx * nz_, mm)
    h_xyz = _entropy((xs * ny + ys[None, :]) * nz_ + zs[None, :], nx * ny * nz_, mm)
    out = h_xz + h_yz - h_xyz - h_z
    return float(out[0]) if single else out


def stratified_permutations(strata: np.ndarray, n_perm: int, rng: np.random.Generator) -> np.ndarray:
    """[n_perm, n] index arrays; each permutes positions only within a stratum."""
    strata = np.asarray(strata)
    n = strata.size
    if n_perm <= 0:
        return np.zeros((0, n), dtype=np.int64)
    s_codes, _ = compress(strata)
    base = np.argsort(s_codes, kind="stable")              # positions grouped by stratum
    keys = s_codes[base][None, :] + rng.random((n_perm, n))  # shuffle inside each group
    order = np.argsort(keys, axis=1)
    perm = np.empty((n_perm, n), dtype=np.int64)
    perm[np.arange(n_perm)[:, None], base[None, :]] = base[order]
    return perm


def p_value(obs: float, null: np.ndarray) -> float:
    """One-sided permutation p-value, (1 + #{null >= obs}) / (1 + n_perm)."""
    null = np.asarray(null)
    if null.size == 0 or np.isnan(obs):
        return float("nan")
    return float((1 + np.sum(null >= obs - 1e-12)) / (1 + null.size))
