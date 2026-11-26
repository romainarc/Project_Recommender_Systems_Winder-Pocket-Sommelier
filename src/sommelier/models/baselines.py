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


# ---------------------------------------------------------------------------
# Baselines for the new framing: what a simple query or rule can already do.
# ---------------------------------------------------------------------------

def wine_attributes(wines, wine_index):
    """Wine attributes as lists ordered by local wine id (to match a questionnaire fast)."""
    n = len(wine_index)
    types, bodies, acidities = [None] * n, [None] * n, [None] * n
    grapes, countries, dishes = [[]] * n, [None] * n, [[]] * n
    for row in wines.itertuples(index=False):
        i = wine_index[int(row.WineID)]
        types[i] = row.Type
        bodies[i] = row.Body
        acidities[i] = row.Acidity
        grapes[i] = list(row.Grapes)
        countries[i] = row.Country
        dishes[i] = list(row.Harmonize)
    return {"type": np.array(types, dtype=object), "body": np.array(bodies, dtype=object),
            "acidity": np.array(acidities, dtype=object), "grapes": grapes,
            "country": np.array(countries, dtype=object), "dishes": dishes}


def questionnaire_match(answers, attrs):
    """Number of questionnaire answers each wine matches (0 to 5), as a numpy array."""
    n = len(attrs["type"])
    match = np.zeros(n)
    if isinstance(answers.get("color"), str):
        match += attrs["type"] == answers["color"]
    if isinstance(answers.get("body"), str):
        match += attrs["body"] == answers["body"]
    if isinstance(answers.get("acidity"), str):
        match += attrs["acidity"] == answers["acidity"]
    liked_grapes = set(answers.get("grapes") if answers.get("grapes") is not None else [])
    if liked_grapes:
        match += np.array([len(liked_grapes.intersection(g)) > 0 for g in attrs["grapes"]])
    liked_countries = set(answers.get("countries") if answers.get("countries") is not None else [])
    if liked_countries:
        match += np.array([c in liked_countries for c in attrs["country"]])
    return match


def clean_answers(answers):
    """Questionnaire answers with removed / empty values dropped (a parquet row gives NaN
    for a removed answer and numpy arrays for lists)."""
    from sommelier.data.questionnaire import as_list, is_answer
    answers = answers or {}
    out = {k: answers.get(k) for k in ("color", "body", "acidity") if is_answer(answers.get(k))}
    out["grapes"] = as_list(answers.get("grapes"))
    out["countries"] = as_list(answers.get("countries"))
    return out


def questionnaire_bonus(scores, answers, attrs, weight):
    """Model scores + weight x (number of questionnaire answers the wine matches).

    The model scores of each user are standardised first (mean 0, std 1) so that `weight`
    means the same thing for every user and every model: weight = 1 lets one matching
    answer move a wine up by one standard deviation of the model scores. weight = 0 gives
    back the pure model ranking. Works on one user (1-D) or a batch (2-D, one answers dict
    per row).
    """
    if weight == 0:
        return scores
    s = np.atleast_2d(np.asarray(scores, dtype=float))
    answers_list = answers if isinstance(answers, list) else [answers]
    out = np.empty_like(s)
    for row in range(s.shape[0]):
        std = s[row].std() or 1.0
        z = (s[row] - s[row].mean()) / std
        out[row] = z + weight * questionnaire_match(clean_answers(answers_list[row]), attrs)
    return out if np.ndim(scores) == 2 else out[0]


def questionnaire_adherence(top, answers, attrs, keys=("color", "body")):
    """Share of the recommended wines that match each given answer (None if not answered)."""
    a = clean_answers(answers)
    field = {"color": "type", "body": "body", "acidity": "acidity"}
    result = {}
    for key in keys:
        if key in a:
            result[key] = float(np.mean([attrs[field[key]][w] == a[key] for w in top]))
    return result


def dish_wines_mask(dish, attrs):
    """True for the wines whose Harmonize list contains the dish."""
    return np.array([dish in d for d in attrs["dishes"]])


def dish_scorer(train_liked_wines, n_wines, attrs, user_dish):
    """"Dish -> wines" query: wines listed for the user's dish, most popular first."""
    pop = np.bincount(train_liked_wines, minlength=n_wines).astype(float)
    masks = {}

    def score(users):
        out = np.tile(pop, (len(users), 1))
        for row, u in enumerate(users):
            dish = user_dish.get(int(u))
            if dish is None:
                continue
            if dish not in masks:
                masks[dish] = dish_wines_mask(dish, attrs)
            out[row] += masks[dish] * 1e6
        return out
    return score


def questionnaire_scorer(train_liked_wines, n_wines, attrs, user_answers, user_dish=None):
    """Rule-based "dish + questionnaire -> filter -> popularity".

    Wines listed for the dish first, then the wines matching the most answers, then by
    popularity. Without user_dish it is "questionnaire -> popularity".
    """
    pop = np.bincount(train_liked_wines, minlength=n_wines).astype(float)
    pop = pop / (pop.max() + 1)          # between 0 and 1: only breaks ties
    masks = {}

    def score(users):
        out = np.tile(pop, (len(users), 1))
        for row, u in enumerate(users):
            answers = user_answers.get(int(u))
            if answers is not None:
                out[row] += questionnaire_match(answers, attrs)
            if user_dish is not None:
                dish = user_dish.get(int(u))
                if dish is not None:
                    if dish not in masks:
                        masks[dish] = dish_wines_mask(dish, attrs)
                    out[row] += masks[dish] * 100
        return out
    return score
