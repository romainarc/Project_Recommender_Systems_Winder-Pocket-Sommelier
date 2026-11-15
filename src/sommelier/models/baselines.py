"""Sanity-floor baselines (week-3 Q2). Fitted on train only."""
from __future__ import annotations

import numpy as np


def random_scorer(n_wines: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    return lambda users: rng.random((len(users), n_wines))


def most_popular_scorer(train_liked_wines: np.ndarray, n_wines: int):
    """Popularity = number of train positives (liked) per wine."""
    pop = np.bincount(train_liked_wines, minlength=n_wines).astype(float)
    return lambda users: np.tile(pop, (len(users), 1))


def most_popular_for_dish_scorer(train_liked_wines: np.ndarray, n_wines: int, dish_wines: list):
    """Context baseline: most popular among the wines listed for the requested dish."""
    pop = np.bincount(train_liked_wines, minlength=n_wines).astype(float)
    listed = np.zeros(n_wines, dtype=bool)
    listed[dish_wines] = True
    boosted = np.where(listed, pop + 1e6, pop)
    return lambda users: np.tile(boosted, (len(users), 1))
