"""Choose the weight of the questionnaire bonus on the VALIDATION split (never the test).

The served score is   standardised model score + weight x (number of answers the wine matches)
(see models.baselines.questionnaire_bonus). weight = 0 is the pure model. For each weight we
report, on the validation users:
    NDCG@10 / Recall@20                 ranking quality (must not drop)
    colour match / body match           share of the top-10 with the colour / body asked for
with and without the dish filter (dish = most frequent dish of the user's validation wines,
the same protocol as evaluate.py on the test split).

The chosen weight is the smallest one whose validation body match is at least
--min-body-match (default 0.8); written to <model>/bonus.json.

Example:
    python scripts/tune_bonus.py --model artifacts/full --data data/processed/full
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate import adherence, answers_per_user, context_dish_per_user, model_scorer  # noqa: E402
from sommelier.data.loaders import load_processed  # noqa: E402
from sommelier.evaluation.harness import evaluate  # noqa: E402
from sommelier.models.baselines import wine_attributes  # noqa: E402
from sommelier.serving.predict import embeddings, load_model  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="artifacts/full")
    p.add_argument("--data", default="data/processed/full")
    p.add_argument("--weights", type=float, nargs="+", default=[0, 0.25, 0.5, 1, 2, 4])
    p.add_argument("--min-body-match", type=float, default=0.8,
                   help="the list must respect the body answer at least this often")
    a = p.parse_args()

    ds = load_processed(ROOT / a.data)
    model, _, _ = load_model(ROOT / a.model, ds)
    attrs = wine_attributes(ds.wines, ds.ckg.wine_index)
    answers = answers_per_user(ds)
    user_dish = context_dish_per_user(ds.valid, ds.ckg, attrs)
    Z = embeddings(model)
    print(f"validation: {len(ds.valid_truth)} users")
    print(f"{'weight':>6} | {'NDCG@10':>8} {'Rec@20':>7} {'colour':>6} {'body':>6} | "
          f"+dish: {'NDCG@10':>8} {'Rec@20':>7} {'colour':>6} {'body':>6}")

    rows = []
    for w in a.weights:
        r = {"weight": w}
        for tag, dish in (("", None), ("dish_", user_dish)):
            fn = model_scorer(model, Z, dish, attrs, answers, w)
            m = evaluate(fn, ds.valid_truth, ds.train_seen, ds.ckg.n_wines)
            m.update(adherence(fn, ds.valid_truth, ds.train_seen, answers, attrs))
            r.update({tag + "ndcg10": m["NDCG@10"], tag + "recall20": m["Recall@20"],
                      tag + "colour_match": m["colour_match"], tag + "body_match": m["body_match"]})
        rows.append(r)
        print(f"{w:6.2f} | {r['ndcg10']:8.4f} {r['recall20']:7.4f} {r['colour_match']:6.2f} "
              f"{r['body_match']:6.2f} | +dish: {r['dish_ndcg10']:8.4f} {r['dish_recall20']:7.4f} "
              f"{r['dish_colour_match']:6.2f} {r['dish_body_match']:6.2f}", flush=True)

    # smallest weight that makes the list respect the body answer often enough (the model alone
    # ignores it ~60 % of the time); among those, the bonus costs the least NDCG
    ok = [r for r in rows if r["body_match"] >= a.min_body_match] or rows
    best = min(ok, key=lambda r: r["weight"])
    out = ROOT / a.model / "bonus.json"
    out.write_text(json.dumps({"chosen_weight": best["weight"], "grid": rows}, indent=2))
    print(f"chosen weight {best['weight']} (smallest with body match >= {a.min_body_match}) -> {out}")


if __name__ == "__main__":
    main()
