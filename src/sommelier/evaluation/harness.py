"""Evaluation harness (owner: PL).

One harness for every model and baseline, so numbers are comparable:
- full ranking over all wines (no sampled negatives),
- wines already seen by the user in train are masked,
- metrics averaged over test users that have at least one warm positive.

A model is any callable ``score_fn(user_ids: np.ndarray) -> np.ndarray [B, n_wines]``.
"""
from __future__ import annotations

from typing import Callable

import numpy as np

from sommelier.evaluation.metrics import ndcg_at_k, recall_at_k

ScoreFn = Callable[[np.ndarray], np.ndarray]


def evaluate(score_fn: ScoreFn, truth: dict, seen: dict, n_wines: int,
             ks=(10, 20), batch_size: int = 1024) -> dict:
    users = np.array(sorted(truth))
    res = {f"NDCG@{k}": [] for k in ks} | {f"Recall@{k}": [] for k in ks}
    for start in range(0, len(users), batch_size):
        batch = users[start:start + batch_size]
        scores = np.asarray(score_fn(batch), dtype=np.float64).copy()
        assert scores.shape == (len(batch), n_wines), f"bad score shape {scores.shape}"
        for row, u in enumerate(batch):
            for w in seen.get(int(u), ()):
                scores[row, w] = -np.inf
        top = np.argsort(-scores, axis=1)[:, :max(ks)]
        for row, u in enumerate(batch):
            t = truth[int(u)]
            for k in ks:
                res[f"NDCG@{k}"].append(ndcg_at_k(top[row], t, k))
                res[f"Recall@{k}"].append(recall_at_k(top[row], t, k))
    out = {m: float(np.mean(v)) if v else 0.0 for m, v in res.items()}
    out["users"] = int(len(users))
    return out
