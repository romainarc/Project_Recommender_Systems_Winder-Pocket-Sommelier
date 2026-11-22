"""Final offline evaluation on the TEST split (run once per final model).

1. Comparison table (NDCG@10, Recall@20, full ranking, train wines masked):
       Random, Most-popular, "dish -> wines" query, "dish + questionnaire -> popularity" rule,
       and each trained model given in --models (main model + ablations), with and without
       the dish filter.
   Context: each test user gets ONE dish, the most frequent dish among the wines they
   liked in the test period (the "I'm eating beef tonight" of the request). Every method
   receives the same dish.

2. Feedback curve: every test user with enough liked wines in train is treated as a NEW
   user: their whole train history is removed from the graph, they keep their
   questionnaire, and they give back their n most recent liked wines (before the train
   cut date) as feedback, n = 0, 1, 3, 5, 10 (--steps). We rank for them and measure
   NDCG@10 on their liked wines of the TEST period (the same truth for every n).

Example:
    python scripts/evaluate.py --data data/processed/full \
        --models artifacts/full artifacts/full_no_questionnaire --out artifacts/results_full
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from sommelier.data.loaders import load_processed  # noqa: E402
from sommelier.evaluation.harness import evaluate  # noqa: E402
from sommelier.models.baselines import (dish_scorer, dish_wines_mask, most_popular_scorer,  # noqa: E402
                                        questionnaire_adherence, questionnaire_bonus,
                                        questionnaire_scorer, random_scorer, wine_attributes)
from sommelier.serving.predict import DEFAULT_QUESTIONNAIRE_WEIGHT, embeddings, load_model  # noqa: E402

FEEDBACK_STEPS = [0, 1, 3, 5, 10]     # changed with --steps


def adherence(score_fn, truth, seen, answers, attrs, k=10, batch=1024):
    """Does the top-k respect the questionnaire? Mean share of the top-k wines whose colour
    (resp. body) is the one the user asked for, over the users who answered that question.
    Uses the same masking of train wines as the ranking metrics."""
    users = sorted(truth)
    colour, body = [], []
    for i in range(0, len(users), batch):
        chunk = users[i:i + batch]
        s = np.array(score_fn(chunk), dtype=float)
        for row, u in enumerate(chunk):
            for w in seen.get(u, ()):
                s[row, w] = -np.inf
        top = np.argsort(-s, axis=1)[:, :k]
        for row, u in enumerate(chunk):
            m = questionnaire_adherence(top[row], answers.get(u, {}), attrs)
            if "color" in m:
                colour.append(m["color"])
            if "body" in m:
                body.append(m["body"])
    return {"colour_match": float(np.mean(colour)) if colour else float("nan"),
            "body_match": float(np.mean(body)) if body else float("nan")}


def context_dish_per_user(test, ckg, attrs):
    """Most frequent dish among each user's test wines (alphabetical order breaks ties)."""
    dishes_of_user = {}
    for user_id, wine_id in zip(test["UserID"], test["WineID"]):
        u = ckg.user_index.get(int(user_id))
        w = ckg.wine_index.get(int(wine_id))
        if u is None or w is None:
            continue
        dishes_of_user.setdefault(u, []).extend(attrs["dishes"][w])
    user_dish = {}
    for u, dishes in dishes_of_user.items():
        if dishes:
            counts = Counter(dishes)
            best = max(counts.values())
            user_dish[u] = sorted(d for d, c in counts.items() if c == best)[0]
    return user_dish


def answers_per_user(ds):
    out = {}
    if ds.questionnaires is None:
        return out
    for row in ds.questionnaires.to_dict("records"):
        u = ds.ckg.user_index.get(int(row["UserID"]))
        if u is not None:
            out[u] = row
    return out


def model_scorer(model, Z, user_dish=None, attrs=None, answers=None, bonus_weight=0.0):
    """Model scores; with answers + bonus_weight, the questionnaire bonus served by the API
    (models.baselines.questionnaire_bonus); with user_dish, the dish's wines come first."""
    wines = Z[model.wine_slice()]
    masks = {}

    def score(users):
        with torch.no_grad():
            s = (Z[torch.as_tensor(users)] @ wines.T).numpy().astype(float)
        if bonus_weight and answers is not None:
            s = questionnaire_bonus(s, [answers.get(int(u), {}) for u in users], attrs, bonus_weight)
        if user_dish is not None:
            for row, u in enumerate(users):
                dish = user_dish.get(int(u))
                if dish is None:
                    continue
                if dish not in masks:
                    masks[dish] = dish_wines_mask(dish, attrs)
                s[row] += masks[dish] * 1e6
        return s
    return score


# --------------------------------------------------------------------------- feedback curve

def feedback_users(ds, max_users, rng):
    """Test users with at least max(steps) liked wines in train.

    feedback[u] = their most recent liked wines of the train period (most recent first),
    truth[u]    = their liked wines of the test period.
    """
    ckg = ds.ckg
    liked = ds.train[ds.train["liked"]].sort_values("Date", ascending=False)
    recent = {}
    for user_id, wine_id in zip(liked["UserID"], liked["WineID"]):
        u = ckg.user_index[int(user_id)]
        recent.setdefault(u, []).append(ckg.wine_index[int(wine_id)])
    need = max(FEEDBACK_STEPS)
    users = [u for u in sorted(ds.test_truth) if len(recent.get(u, [])) >= need]
    if len(users) > max_users:
        users = sorted(rng.choice(users, size=max_users, replace=False).tolist())
    feedback = {u: recent[u][:need] for u in users}
    truth = {u: ds.test_truth[u] for u in users}
    return feedback, truth


def edges_for_new_users(ckg, feedback, n):
    """Behavior edges where the selected users lost their train history and gave n likes."""
    selected = torch.tensor(sorted(feedback))
    extra_u, extra_w = [], []
    for u, wines in feedback.items():
        for w in wines[:n]:
            extra_u.append(u)
            extra_w.append(w + ckg.n_users)
    extra = torch.tensor([extra_u, extra_w], dtype=torch.long).reshape(2, -1)
    new_edges = {}
    for b, e in ckg.behavior_edges.items():
        keep = ~torch.isin(e[0], selected)
        new_edges[b] = torch.cat([e[:, keep], extra], dim=1)   # a like is also a rating
    return new_edges


def feedback_curve(models, ds, attrs, answers, max_users, rng, log, bonus_weight=0.0):
    ckg = ds.ckg
    feedback, truth = feedback_users(ds, max_users, rng)
    log(f"feedback curve: steps {FEEDBACK_STEPS}, {len(truth)} test users with "
        f">= {max(FEEDBACK_STEPS)} liked wines in train")
    if not truth:
        return {}
    liked = ds.train_liked[1].numpy()
    curve = {}
    # rules do not learn from feedback: flat lines
    for name, fn in [("Most-popular", most_popular_scorer(liked, ckg.n_wines)),
                     ("Questionnaire -> popularity (rule)",
                      questionnaire_scorer(liked, ckg.n_wines, attrs, answers))]:
        curve[name] = []
        for n in FEEDBACK_STEPS:
            seen = {u: set(feedback[u][:n]) for u in truth}
            curve[name].append(evaluate(fn, truth, seen, ckg.n_wines)["NDCG@10"])
    main = next(iter(models)) if models else None
    for name, model in models.items():
        variants = [(name, 0.0)]
        if bonus_weight and name == main:          # served version of the main model
            variants.append((name + " + questionnaire bonus", bonus_weight))
        for label, weight in variants:
            curve[label] = []
            for n in FEEDBACK_STEPS:
                edges = model.build_edges(behavior_edges=edges_for_new_users(ckg, feedback, n))
                Z = embeddings(model, edges)
                seen = {u: set(feedback[u][:n]) for u in truth}
                fn = model_scorer(model, Z, attrs=attrs, answers=answers, bonus_weight=weight)
                curve[label].append(evaluate(fn, truth, seen, ckg.n_wines)["NDCG@10"])
            log(f"  {label}: " + ", ".join(f"n={n}: {v:.4f}" for n, v in zip(FEEDBACK_STEPS, curve[label])))
    return {"steps": FEEDBACK_STEPS, "users": len(truth), "ndcg10": curve}


def plot_curve(result, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    for name, values in result["ndcg10"].items():
        style = "--" if "rule" in name or "popular" in name else "-"
        ax.plot(result["steps"], values, style, marker="o", label=name)
    ax.set_xticks(result["steps"])
    ax.set_xlabel("feedback given by a new user (liked wines)")
    ax.set_ylabel("NDCG@10 on their test-period wines")
    ax.set_title(f"Recommendations improve with feedback ({result['users']} test users)")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/processed/full")
    p.add_argument("--models", nargs="+", default=["artifacts/full"],
                   help="trained model folders (the first one is the main model)")
    p.add_argument("--out", default="artifacts/results_full")
    p.add_argument("--max-curve-users", type=int, default=2000)
    p.add_argument("--steps", type=int, nargs="+", default=FEEDBACK_STEPS,
                   help="numbers of feedback for the curve (default 0 1 3 5 10)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--bonus-weight", type=float, default=DEFAULT_QUESTIONNAIRE_WEIGHT,
                   help="questionnaire bonus of the served model (0 = off); tuned with tune_bonus.py")
    a = p.parse_args()
    FEEDBACK_STEPS[:] = sorted(a.steps)
    log = lambda m: print(m, flush=True)
    rng = np.random.default_rng(a.seed)
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)

    ds = load_processed(ROOT / a.data)
    ckg = ds.ckg
    attrs = wine_attributes(ds.wines, ckg.wine_index)
    answers = answers_per_user(ds)
    user_dish = context_dish_per_user(ds.test, ckg, attrs)
    liked = ds.train_liked[1].numpy()
    log(f"test: {len(ds.test_truth)} users, {sum(len(v) for v in ds.test_truth.values())} positives, "
        f"{len(user_dish)} users with a context dish")

    models = {}
    for folder in a.models:
        model, _, config = load_model(ROOT / folder, ds)
        name = "HGIB-KGAT"
        if not config["use_questionnaire"]:
            name += " without questionnaire"
        if not config["use_hgib"]:
            name += " without HGIB"
        if not config["use_gre"] and config["use_hgib"]:
            name += " without GRE"
        if name in models:                       # two models of the same kind: add the folder
            name += f" [{Path(folder).name}]"
        models[name] = model

    rows = {
        "Random": random_scorer(ckg.n_wines, a.seed),
        "Most-popular": most_popular_scorer(liked, ckg.n_wines),
        "Dish -> wines (query)": dish_scorer(liked, ckg.n_wines, attrs, user_dish),
        "Dish + questionnaire -> popularity (rule)":
            questionnaire_scorer(liked, ckg.n_wines, attrs, answers, user_dish),
    }
    main_model = next(iter(models)) if models else None
    for name, model in models.items():
        Z = embeddings(model)
        rows[name] = model_scorer(model, Z)
        rows[name + " + dish filter"] = model_scorer(model, Z, user_dish, attrs)
        if a.bonus_weight and name == main_model:     # what the API serves
            rows[name + " + questionnaire bonus"] = model_scorer(
                model, Z, attrs=attrs, answers=answers, bonus_weight=a.bonus_weight)
            rows[name + " + questionnaire bonus + dish filter"] = model_scorer(
                model, Z, user_dish, attrs, answers, a.bonus_weight)

    table = {}
    for name, fn in rows.items():
        table[name] = evaluate(fn, ds.test_truth, ds.train_seen, ckg.n_wines)
        table[name].update(adherence(fn, ds.test_truth, ds.train_seen, answers, attrs))
        log(f"{name:56s} NDCG@10 {table[name]['NDCG@10']:.4f}  Recall@20 {table[name]['Recall@20']:.4f}"
            f"  colour match {table[name]['colour_match']:.2f}  body match {table[name]['body_match']:.2f}")

    curve = feedback_curve(models, ds, attrs, answers, a.max_curve_users, rng, log, a.bonus_weight)
    if curve:
        plot_curve(curve, out / "feedback_curve.png")

    (out / "results.json").write_text(json.dumps({"table": table, "feedback_curve": curve}, indent=2))
    lines = ["| Method | NDCG@10 | Recall@20 | Colour match | Body match |",
             "| --- | --- | --- | --- | --- |"]
    for name, r in table.items():
        lines.append(f"| {name} | {r['NDCG@10']:.4f} | {r['Recall@20']:.4f} | "
                     f"{r['colour_match']:.2f} | {r['body_match']:.2f} |")
    (out / "results.md").write_text("\n".join(lines) + "\n")
    log(f"saved {out / 'results.md'}, {out / 'results.json'}" +
        (f", {out / 'feedback_curve.png'}" if curve else ""))


if __name__ == "__main__":
    main()
