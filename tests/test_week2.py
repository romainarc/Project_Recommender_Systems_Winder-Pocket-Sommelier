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


@pytest.fixture(scope="session")
def tiny_model(tmp_path_factory):
    """A model trained for 2 epochs on the Test data (enough to check the plumbing)."""
    out = tmp_path_factory.mktemp("model")
    from sommelier.training.train import train
    train(PROCESSED, out, epochs=2, batch_size=128, dim=16, log=lambda m: None)
    return out


def test_questionnaires_come_from_train_only():
    import pandas as pd
    train = pd.read_parquet(PROCESSED / "train.parquet")
    q = pd.read_parquet(PROCESSED / "questionnaires.parquet")
    assert set(q["UserID"]) <= set(train["UserID"])


def test_guest_slots_do_not_change_real_users(tiny_model):
    import torch
    from sommelier.serving.predict import Recommender, embeddings, load_model
    rec = Recommender(tiny_model, PROCESSED, n_guests=3)
    model, ds, _ = load_model(tiny_model, None)
    Z = embeddings(model)
    n, nw = ds.ckg.n_users, ds.ckg.n_wines
    before = Z[:5] @ Z[n:n + nw].T
    after = rec.Z[:5] @ rec.Z[rec.ckg.n_users:rec.ckg.n_users + nw].T
    assert torch.allclose(before, after, atol=1e-5)


def test_api_real_model_and_logging(tmp_path, tiny_model):
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/t.db"
    os.environ["MODEL_DIR"] = str(tiny_model)
    os.environ["DATA_DIR"] = str(PROCESSED)
    sys.path.insert(0, str(ROOT))
    import importlib
    from fastapi.testclient import TestClient
    import api.main as main
    importlib.reload(main)
    c = TestClient(main.app)
    r = c.post("/onboard", json={"user_id": "u1", "color": "Red", "grapes": ["Malbec"]})
    assert r.status_code == 200
    r = c.post("/recommend", json={"user_id": "u1", "dish": "Beef", "k": 5})
    body = r.json()
    assert r.status_code == 200 and len(body["wines"]) == 5
    assert body["model_version"] == Path(tiny_model).name           # trained model, not a mock
    assert body["latency_ms"] < 2000
    first = body["wines"][0]["wine_id"]
    r = c.post("/log_interaction", json={"user_id": "u1", "wine_id": first, "event_type": "like"})
    assert r.json()["status"] == "logged"
    again = c.post("/recommend", json={"user_id": "u1", "dish": "Beef", "k": 5}).json()
    assert first not in [w["wine_id"] for w in again["wines"]]       # liked wine not shown again
    from sommelier.db.schema import Interaction, QuestionnaireAnswer
    with main.Session() as s:
        assert s.query(Interaction).count() == 1
        assert s.query(QuestionnaireAnswer).count() == 1


def test_questionnaire_bonus_ranks_matching_wines_first():
    from sommelier.models.baselines import questionnaire_adherence, questionnaire_bonus
    attrs = {"type": np.array(["Red", "White", "Red", "White"], dtype=object),
             "body": np.array(["Full-bodied", "Light-bodied", "Light-bodied", "Full-bodied"], dtype=object),
             "acidity": np.array([None] * 4, dtype=object), "grapes": [[]] * 4,
             "country": np.array(["France"] * 4, dtype=object)}
    model_scores = np.array([0.1, 0.9, 0.2, 0.8])            # the model prefers the whites
    answers = {"color": "Red", "body": float("nan"), "grapes": np.array([])}   # parquet-like row
    assert np.array_equal(questionnaire_bonus(model_scores, answers, attrs, 0), model_scores)
    top = np.argsort(-questionnaire_bonus(model_scores, answers, attrs, 3.0))[:2]
    assert set(top) == {0, 2}                                 # the two reds come first
    assert questionnaire_adherence(top, answers, attrs) == {"color": 1.0}   # body not answered


def test_served_list_respects_the_colour(tiny_model):
    from sommelier.serving.predict import Recommender
    rec = Recommender(tiny_model, PROCESSED, n_guests=2, questionnaire_weight=5.0)
    rec.onboard("g", {"color": "Red"})
    wines = rec.recommend("g", k=5)
    assert all(w["type"] == "Red" for w in wines)
