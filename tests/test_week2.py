"""Week-2 checks: data split, harness, forward pass, API. Run: pytest -q"""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PROCESSED = ROOT / "data/processed/test"


@pytest.fixture(scope="session", autouse=True)
def prepared():
    subprocess.run([sys.executable, str(ROOT / "scripts/prepare_data.py"), "--preset", "test"],
                   check=True, capture_output=True)


def test_split_is_temporal_and_leak_free():
    import pandas as pd
    train = pd.read_parquet(PROCESSED / "train.parquet")
    test = pd.read_parquet(PROCESSED / "test.parquet")
    valid = pd.read_parquet(PROCESSED / "valid.parquet")
    assert train["Date"].max() < valid["Date"].min() <= valid["Date"].max() < test["Date"].min()
    pairs = set(zip(train.UserID, train.WineID))
    assert not pairs & set(zip(test.UserID, test.WineID))
    assert (test["Rating"] >= 4).all()


def test_metrics():
    from sommelier.evaluation.metrics import ndcg_at_k, recall_at_k
    assert ndcg_at_k(np.array([3, 1, 2]), {3}) == 1.0
    assert 0 < ndcg_at_k(np.array([1, 3, 2]), {3}) < 1
    assert recall_at_k(np.array([1, 2, 3]), {3, 9}, k=3) == 0.5


def test_harness_oracle_is_perfect():
    from sommelier.data.loaders import load_processed
    from sommelier.evaluation.harness import evaluate
    ds = load_processed(PROCESSED)
    n = ds.ckg.n_wines

    def oracle(users):
        s = np.zeros((len(users), n))
        for i, u in enumerate(users):
            s[i, list(ds.test_truth[int(u)])] = 1
        return s
    assert evaluate(oracle, ds.test_truth, ds.train_seen, n)["NDCG@10"] == pytest.approx(1.0)


def test_hgib_forward_and_backward():
    import torch
    from sommelier.data.loaders import load_processed
    from sommelier.models.hgib import HGIBKGAT
    torch.manual_seed(0)
    ds = load_processed(PROCESSED)
    model = HGIBKGAT(ds.ckg)
    Z = model.forward()[-1][0]
    s = model.score_users(Z, torch.arange(4))
    assert s.shape == (4, ds.ckg.n_wines) and torch.isfinite(s).all()
    u, w = ds.train_liked[:, :32]
    loss, _ = model.loss(u, w, torch.randint(0, ds.ckg.n_wines, (32,)))
    loss.backward()
    assert torch.isfinite(loss)


def test_api_mock_and_logging(tmp_path):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/t.db"
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    import importlib
    import api.main as main
    importlib.reload(main)
    c = TestClient(main.app)
    r = c.post("/recommend", json={"user_id": "u1", "dish": "Beef", "k": 5})
    assert r.status_code == 200 and len(r.json()["wines"]) == 5
    assert all("Beef" in main.WINES.set_index("WineID").loc[w["wine_id"], "Harmonize"]
               for w in r.json()["wines"])
    r = c.post("/log_interaction", json={"user_id": "u1", "wine_id": 100062, "event_type": "like"})
    assert r.json()["status"] == "logged"
    from sommelier.db.schema import Interaction
    with main.Session() as s:
        assert s.query(Interaction).count() == 1
