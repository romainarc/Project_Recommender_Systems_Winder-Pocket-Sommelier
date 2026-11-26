"""Load the processed split and build the graph + id-mapped evaluation sets."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from sommelier.graph.build_ckg import CKG, build_ckg


@dataclass
class Dataset:
    ckg: CKG
    train: pd.DataFrame
    valid: pd.DataFrame
    test: pd.DataFrame
    wines: pd.DataFrame
    train_liked: torch.Tensor          # [2, E] local (user, wine) ids, target behavior
    train_seen: dict                   # user local id -> set of wine local ids (masked at eval)
    valid_truth: dict                  # user local id -> set of wine local ids
    test_truth: dict
    questionnaires: pd.DataFrame = None


def _truth(df: pd.DataFrame, ckg: CKG) -> dict:
    out: dict = {}
    for u, w in zip(df["UserID"].map(ckg.user_index), df["WineID"].map(ckg.wine_index)):
        if pd.notna(u) and pd.notna(w):
            out.setdefault(int(u), set()).add(int(w))
    return out


def load_processed(path: str | Path) -> Dataset:
    p = Path(path)
    train = pd.read_parquet(p / "train.parquet")
    valid = pd.read_parquet(p / "valid.parquet")
    test = pd.read_parquet(p / "test.parquet")
    wines = pd.read_parquet(p / "wines.parquet")
    wines["Grapes"] = wines["Grapes"].map(list)
    wines["Harmonize"] = wines["Harmonize"].map(list)

    # simulated questionnaires (built from train only); older processed folders have none
    questionnaires = None
    if (p / "questionnaires.parquet").exists():
        questionnaires = pd.read_parquet(p / "questionnaires.parquet")

    ckg = build_ckg(train, wines, questionnaires)
    liked = train[train["liked"]]
    tl = torch.tensor(np.stack([liked["UserID"].map(ckg.user_index).to_numpy(),
                                liked["WineID"].map(ckg.wine_index).to_numpy()]), dtype=torch.long)
    return Dataset(ckg, train, valid, test, wines, tl, _truth(train, ckg),
                   _truth(valid, ckg), _truth(test, ckg), questionnaires)
