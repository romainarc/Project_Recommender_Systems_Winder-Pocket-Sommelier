"""Week-2 check Q3: feed the evaluation harness with mock predictions and get NDCG back.

Sanity checks on the harness itself:
- an oracle that knows the test answers must reach NDCG@10 = 1,
- random must be low,
- most-popular is the floor every real model has to beat (week 3).

    python scripts/evaluate_mock.py --data data/processed/test
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from sommelier.data.loaders import load_processed  # noqa: E402
from sommelier.evaluation.harness import evaluate  # noqa: E402
from sommelier.models.baselines import most_popular_scorer, random_scorer  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/processed/test")
    p.add_argument("--split", choices=["valid", "test"], default="test")
    a = p.parse_args()

    ds = load_processed(ROOT / a.data)
    n = ds.ckg.n_wines
    truth = ds.test_truth if a.split == "test" else ds.valid_truth
    liked = ds.train_liked[1].numpy()

    def oracle(users):
        s = np.zeros((len(users), n))
        for i, u in enumerate(users):
            s[i, list(truth[int(u)])] = 1.0
        return s

    scorers = {"Oracle (mock, must be 1.0)": oracle,
               "Random (mock)": random_scorer(n),
               "Most-popular": most_popular_scorer(liked, n)}
    results = {name: evaluate(fn, truth, ds.train_seen, n) for name, fn in scorers.items()}

    print(f"{'Scorer':30s} {'NDCG@10':>8s} {'Recall@20':>10s} {'users':>6s}")
    for name, r in results.items():
        print(f"{name:30s} {r['NDCG@10']:8.4f} {r['Recall@20']:10.4f} {r['users']:6d}")
    assert abs(results["Oracle (mock, must be 1.0)"]["NDCG@10"] - 1.0) < 1e-9
    out = ROOT / "artifacts" / "mock_eval.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
