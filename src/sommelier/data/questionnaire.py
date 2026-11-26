"""Simulated taste questionnaires.

X-Wines has no real questionnaire answers, so we build one for each user from the
wines they liked in the TRAIN split only (so there is no leakage).

Answers:
    color      the most frequent wine type among the liked wines (Red, White, ...)
    body       the most frequent body (Light-bodied ... Very full-bodied)
    acidity    the most frequent acidity (Low, Medium, High)
    grapes     the 3 most frequent grapes
    countries  the 2 most frequent countries
    discovery  "explorer" if the liked wines are less popular than the median wine, else "safe"

Noise: real people answer imperfectly. Each answer is removed with probability DROP,
or replaced by a random valid value with probability SWAP.
"""
from collections import Counter

import numpy as np
import pandas as pd

DROP = 0.2   # probability of removing an answer
SWAP = 0.1   # probability of replacing an answer by a random one


def most_common(values, k):
    """Return the k most frequent values of a list."""
    counter = Counter(values)
    result = []
    for value, count in counter.most_common(k):
        result.append(value)
    return result


def add_noise_to_answer(answer, possible_values, rng):
    """Keep, remove (None) or replace one answer."""
    r = rng.random()
    if r < DROP:
        return None
    if r < DROP + SWAP:
        return str(rng.choice(possible_values))
    return answer


def add_noise_to_list(answers, possible_values, rng):
    """Apply the same noise to each element of a list answer."""
    kept = []
    for answer in answers:
        r = rng.random()
        if r < DROP:
            continue
        if r < DROP + SWAP:
            kept.append(str(rng.choice(possible_values)))
        else:
            kept.append(answer)
    return kept


def simulate(train, wines, seed=42):
    """Build one questionnaire per train user. Returns a DataFrame (one row per user)."""
    rng = np.random.default_rng(seed)
    wine_info = wines.set_index("WineID")

    # popularity of each wine = number of ratings in the train split
    popularity = train.groupby("WineID").size()
    median_popularity = popularity.median()

    # the wines each user liked (rating >= 4)
    liked = train[train["Rating"] >= 4.0]
    # users who liked nothing: we use all the wines they rated instead
    users_without_like = ~train["UserID"].isin(liked["UserID"])
    source = pd.concat([liked, train[users_without_like]])

    # all the possible values, used to create random (noisy) answers
    all_grapes = set()
    for grapes in wines["Grapes"]:
        for grape in grapes:
            all_grapes.add(grape)
    possible = {
        "color": sorted(wines["Type"].dropna().unique()),
        "body": sorted(wines["Body"].dropna().unique()),
        "acidity": sorted(wines["Acidity"].dropna().unique()),
        "discovery": ["explorer", "safe"],
        "grapes": sorted(all_grapes),
        "countries": sorted(wines["Country"].dropna().unique()),
    }

    rows = []
    for user_id, user_ratings in source.groupby("UserID"):
        user_wines = wine_info.loc[user_ratings["WineID"]]

        user_grapes = []
        for grapes in user_wines["Grapes"]:
            for grape in grapes:
                user_grapes.append(grape)

        mean_popularity = popularity.loc[user_ratings["WineID"]].mean()
        if mean_popularity < median_popularity:
            discovery = "explorer"
        else:
            discovery = "safe"

        answers = {
            "UserID": int(user_id),
            "color": most_common(user_wines["Type"], 1)[0],
            "body": most_common(user_wines["Body"], 1)[0],
            "acidity": most_common(user_wines["Acidity"], 1)[0],
            "grapes": most_common(user_grapes, 3),
            "countries": most_common(user_wines["Country"], 2),
            "discovery": discovery,
        }

        # noise, always in the same order so the result is reproducible
        for key in ["color", "body", "acidity", "discovery"]:
            answers[key] = add_noise_to_answer(answers[key], possible[key], rng)
        for key in ["grapes", "countries"]:
            answers[key] = add_noise_to_list(answers[key], possible[key], rng)

        rows.append(answers)

    return pd.DataFrame(rows)


def is_answer(value):
    """True for a real answer. A removed answer is None, or NaN after saving to a file."""
    return isinstance(value, str) and value != ""


def as_list(value):
    """A list answer as a normal Python list (a file gives back an array, or NaN if empty)."""
    if isinstance(value, (list, tuple, np.ndarray)):
        result = []
        for item in value:
            if is_answer(item):
                result.append(item)
        return result
    return []


def answer_entities(row):
    """Turn one questionnaire into (relation, graph node) pairs for the knowledge graph."""
    links = []
    if is_answer(row.get("color")):
        links.append(("likes_type", "type:" + row["color"]))
    if is_answer(row.get("body")):
        links.append(("likes_body", "body:" + row["body"]))
    if is_answer(row.get("acidity")):
        links.append(("likes_acidity", "acidity:" + row["acidity"]))
    for grape in as_list(row.get("grapes")):
        links.append(("likes_grape", "grape:" + grape))
    for country in as_list(row.get("countries")):
        links.append(("likes_country", "country:" + country))
    if is_answer(row.get("discovery")):
        links.append(("discovery", "discovery:" + row["discovery"]))
    return links
