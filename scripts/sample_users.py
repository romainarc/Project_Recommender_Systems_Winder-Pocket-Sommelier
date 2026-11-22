"""Qualitative sanity check for the report (week 3): 3 sample users + the "same dish,
two questionnaires" demo.

For each sample test user: their questionnaire, their top-10 wines, which ones they really
liked in the test period, how popular the recommended wines are (rank 1 = most popular)
and how varied the list is. Then two NEW users answer opposite questionnaires and ask for
the same dish: their lists must differ.

    python scripts/sample_users.py --model artifacts/slim --data data/processed/slim
Output: printed + saved as <model>/sample_users.md
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sommelier.serving.predict import Recommender  # noqa: E402

ALICE = {"color": "Red", "body": "Very full-bodied", "acidity": "Medium",
         "grapes": ["Cabernet Sauvignon", "Malbec"], "countries": ["Argentina", "France"],
         "discovery": "safe"}
BOB = {"color": "White", "body": "Light-bodied", "acidity": "High",
       "grapes": ["Riesling", "Sauvignon Blanc"], "countries": ["Germany", "New Zealand"],
       "discovery": "explorer"}


def answers_text(a):
    parts = []
    for key in ["color", "body", "acidity", "discovery"]:
        if isinstance(a.get(key), str):
            parts.append(f"{key}: {a[key]}")
    for key in ["grapes", "countries"]:
        values = list(a.get(key)) if a.get(key) is not None else []
        if values:
            parts.append(f"{key}: {', '.join(values)}")
    return "; ".join(parts) if parts else "(no answer)"


def wine_table(recs, liked_ids=None):
    lines = ["| # | Wine | Type | Body | Grapes | Country | Popularity rank | Why |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for i, r in enumerate(recs, 1):
        hit = " ✓" if liked_ids and r["wine_id"] in liked_ids else ""
        lines.append(f"| {i} | {r['name']}{hit} | {r['type']} | {r['body']} | "
                     f"{', '.join(r['grapes'][:3])} | {r['country']} | {r['popularity_rank']} | "
                     f"{r['explanation']} |")
    return lines


def summary(recs, n_wines, answers=None):
    types = len({r["type"] for r in recs})
    countries = len({r["country"] for r in recs})
    mean_rank = sum(r["popularity_rank"] for r in recs) / len(recs)
    text = (f"{types} wine types, {countries} countries; mean popularity rank {mean_rank:.0f} "
            f"of {n_wines} wines")
    answers = answers or {}
    for key, field in (("color", "type"), ("body", "body")):
        if isinstance(answers.get(key), str):      # does the list respect the answer?
            n = sum(r[field] == answers[key] for r in recs)
            text += f"; {key} asked ({answers[key]}) in {n}/{len(recs)}"
    return text


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="artifacts/slim")
    p.add_argument("--data", default="data/processed/slim")
    p.add_argument("--weight", type=float, default=None,
                   help="questionnaire bonus weight (default: the served one; 0 = pure model)")
    p.add_argument("--dish", default="Poultry", help="dish for the two-new-users demo (one that suits reds and whites)")
    a = p.parse_args()

    rec = Recommender(ROOT / a.model, ROOT / a.data, questionnaire_weight=a.weight)
    ds = rec.ds
    n_wines = ds.ckg.n_wines
    lines = [f"# Qualitative sanity check ({Path(a.model).name}, questionnaire weight "
             f"{rec.questionnaire_weight})", ""]

    # 3 test users with different favourite colours and at least 3 liked test wines
    chosen, colours = [], set()
    for row in ds.questionnaires.to_dict("records"):
        u = ds.ckg.user_index.get(int(row["UserID"]))
        colour = row.get("color")
        if u is None or not isinstance(colour, str) or colour in colours:
            continue
        if len(ds.test_truth.get(u, ())) >= 3:
            chosen.append(row)
            colours.add(colour)
        if len(chosen) == 3:
            break

    local_to_id = rec.local_to_wine_id
    for row in chosen:
        user_id = str(int(row["UserID"]))
        u = ds.ckg.user_index[int(row["UserID"])]
        liked_ids = {local_to_id[w] for w in ds.test_truth[u]}
        recs = rec.recommend(user_id, None, 10)
        hits = sum(r["wine_id"] in liked_ids for r in recs)
        lines += [f"## User {user_id}", "",
                  f"Questionnaire: {answers_text(row)}  ",
                  f"Train history: {len(ds.train_seen.get(u, ()))} rated wines. "
                  f"Liked in the test period: {len(liked_ids)} wines, {hits} of them in the top 10 (✓).  ",
                  f"List: {summary(recs, n_wines, row)}.", ""]
        lines += wine_table(recs, liked_ids) + [""]

    # same dish, two opposite questionnaires
    rec.onboard("demo-alice", ALICE)
    rec.onboard("demo-bob", BOB)
    ra = rec.recommend("demo-alice", a.dish, 10)
    rb = rec.recommend("demo-bob", a.dish, 10)
    common = len({r["wine_id"] for r in ra} & {r["wine_id"] for r in rb})
    lines += [f"## Same dish ({a.dish}), two new users with opposite questionnaires", "",
              f"Wines in common in the two top-10 lists: {common} of 10.", "",
              f"### New user A: {answers_text(ALICE)}", f"List: {summary(ra, n_wines, ALICE)}.", ""]
    lines += wine_table(ra) + ["", f"### New user B: {answers_text(BOB)}",
                               f"List: {summary(rb, n_wines, BOB)}.", ""]
    lines += wine_table(rb) + [""]

    text = "\n".join(lines)
    print(text)
    out = ROOT / a.model / (f"sample_users_w{a.weight:g}.md" if a.weight is not None else "sample_users.md")
    out.write_text(text, encoding="utf-8")
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
