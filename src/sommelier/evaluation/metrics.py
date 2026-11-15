"""Ranking metrics on full ranking (owner: PL). Binary relevance."""
from __future__ import annotations

import numpy as np


def ndcg_at_k(ranked: np.ndarray, truth: set, k: int = 10) -> float:
    """ranked: item ids sorted by score (best first)."""
    if not truth:
        return 0.0
    gains = np.array([1.0 if i in truth else 0.0 for i in ranked[:k]])
    dcg = (gains / np.log2(np.arange(2, len(gains) + 2))).sum()
    ideal = (1.0 / np.log2(np.arange(2, min(len(truth), k) + 2))).sum()
    return float(dcg / ideal)


def recall_at_k(ranked: np.ndarray, truth: set, k: int = 20) -> float:
    if not truth:
        return 0.0
    return len(set(ranked[:k].tolist()) & truth) / len(truth)
