"""X-Wines V1 data pipeline (owner: DE, split: PL).

Steps
-----
1. Load wines and ratings (ratings are read in chunks so the 21M-row Full file fits in memory).
2. Optional date filter (2021 only for the Full versions V1 and V2).
3. Deduplicate (user, wine) pairs coming from several vintages: keep the latest rating.
4. Optional k-core filtering on users and wines.
5. Two behaviors for HGIB: ``rated`` (every rating, auxiliary) and ``liked`` (rating >= 4, target).
6. Global temporal split on Date: train < T1 <= valid < T2 <= test.
   Interaction-derived objects (graphs, popularity, embeddings) are built on train only.
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd
from sommelier.data.questionnaire import simulate as simulate_questionnaires 

RATING_COLS = ["UserID", "WineID", "Rating", "Date"]
LIKE_THRESHOLD = 4.0


@dataclass
class PrepConfig:
    min_year: int | None = None      # 2021 for the Full dataset
    kcore: int = 1                   # 1 = no filtering (Test), 10 for Full
    train_frac: float = 0.8
    valid_frac: float = 0.1
    chunksize: int = 2_000_000


def parse_list(value) -> list:
    """X-Wines stores lists as strings: "['Beef', 'Lamb']"."""
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        out = ast.literal_eval(value)
        return list(out) if isinstance(out, (list, tuple)) else [out]
    except (ValueError, SyntaxError):
        return [v.strip(" '\"") for v in value.strip("[]").split(",") if v.strip()]


def load_wines(path: str | Path) -> pd.DataFrame:
    wines = pd.read_csv(path)
    wines["Grapes"] = wines["Grapes"].map(parse_list)
    wines["Harmonize"] = wines["Harmonize"].map(parse_list)
    return wines


def load_ratings(path: str | Path, cfg: PrepConfig) -> pd.DataFrame:
    """Read ratings in chunks; apply the date filter per chunk to keep memory low."""
    parts = []
    for chunk in pd.read_csv(path, usecols=RATING_COLS, chunksize=cfg.chunksize,
                             dtype={"UserID": "int64", "WineID": "int64", "Rating": "float32"}):
        chunk["Date"] = pd.to_datetime(chunk["Date"])
        if cfg.min_year is not None:
            chunk = chunk[chunk["Date"].dt.year >= cfg.min_year]
        parts.append(chunk)
    return pd.concat(parts, ignore_index=True)


def deduplicate(ratings: pd.DataFrame) -> pd.DataFrame:
    """One row per (user, wine): the latest rating wins."""
    ratings = ratings.sort_values("Date")
    return ratings.drop_duplicates(["UserID", "WineID"], keep="last").reset_index(drop=True)


def kcore_filter(ratings: pd.DataFrame, k: int) -> pd.DataFrame:
    if k <= 1:
        return ratings
    while True:
        n = len(ratings)
        u = ratings["UserID"].map(ratings["UserID"].value_counts())
        w = ratings["WineID"].map(ratings["WineID"].value_counts())
        ratings = ratings[(u >= k) & (w >= k)]
        if len(ratings) == n:
            return ratings.reset_index(drop=True)


def temporal_split(ratings: pd.DataFrame, cfg: PrepConfig):
    """Global temporal split. Returns (train_all_behaviors, valid_liked, test_liked, cut dates).

    Cut dates are quantiles of the rating dates. Train keeps both behaviors; valid and test
    keep only target-behavior positives (liked) of warm users and wines (seen in train).
    """
    t1 = ratings["Date"].quantile(cfg.train_frac)
    t2 = ratings["Date"].quantile(cfg.train_frac + cfg.valid_frac)
    train = ratings[ratings["Date"] < t1].copy()
    valid = ratings[(ratings["Date"] >= t1) & (ratings["Date"] < t2)]
    test = ratings[ratings["Date"] >= t2]

    seen_u, seen_w = set(train["UserID"]), set(train["WineID"])

    def warm_liked(df):
        df = df[df["Rating"] >= LIKE_THRESHOLD]
        warm = df["UserID"].isin(seen_u) & df["WineID"].isin(seen_w)
        return df[warm].copy(), int((~warm).sum())

    valid, dropped_v = warm_liked(valid)
    test, dropped_t = warm_liked(test)
    info = {"T1": str(t1), "T2": str(t2), "valid_cold_dropped": dropped_v, "test_cold_dropped": dropped_t}
    return train, valid, test, info


def add_behaviors(train: pd.DataFrame) -> pd.DataFrame:
    train = train.copy()
    train["rated"] = True
    train["liked"] = train["Rating"] >= LIKE_THRESHOLD
    return train


def run(wines_path, ratings_path, out_dir, cfg: PrepConfig) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    wines = load_wines(wines_path)
    raw = load_ratings(ratings_path, cfg)
    n_raw = len(raw)
    ratings = deduplicate(raw)
    n_dedup = len(ratings)
    ratings = ratings[ratings["WineID"].isin(wines["WineID"])]
    ratings = kcore_filter(ratings, cfg.kcore)

    train, valid, test, split_info = temporal_split(ratings, cfg)
    train = add_behaviors(train)
    wines = wines[wines["WineID"].isin(ratings["WineID"])].reset_index(drop=True)

    train.to_parquet(out / "train.parquet", index=False)
    valid.to_parquet(out / "valid.parquet", index=False)
    test.to_parquet(out / "test.parquet", index=False)
    wines.to_parquet(out / "wines.parquet", index=False)

    # simulated questionnaires, from TRAIN only (no leakage)                    
    questionnaires = simulate_questionnaires(train, wines)                      
    questionnaires.to_parquet(out / "questionnaires.parquet", index=False)      

    stats = {
        "config": asdict(cfg),
        "ratings_read": n_raw,
        "after_dedup": n_dedup,
        "after_kcore": len(ratings),
        "users": int(ratings["UserID"].nunique()),
        "wines": int(ratings["WineID"].nunique()),
        "train_rated": len(train),
        "train_liked": int(train["liked"].sum()),
        "valid_liked_warm": len(valid),
        "test_liked_warm": len(test),
        "dishes": int(wines["Harmonize"].explode().nunique()),
        "questionnaires": len(questionnaires),
        **split_info,
    }
    (out / "stats.json").write_text(json.dumps(stats, indent=2))
    return stats
