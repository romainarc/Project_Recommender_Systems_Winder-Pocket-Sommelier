"""Load a trained model and serve recommendations (used by evaluation, the API and the report).

New app users ("guests") are served WITHOUT retraining: the graph gets empty user slots;
a guest's questionnaire answers and likes become edges of their slot, one forward pass
gives their profile, and every new like updates it.
"""
import json
import os
from pathlib import Path

import numpy as np
import torch

from sommelier.data.loaders import load_processed
from sommelier.data.questionnaire import answer_entities
from sommelier.graph.build_ckg import QUESTIONNAIRE_RELATIONS, KG_RELATIONS, CKG
from sommelier.models.baselines import dish_wines_mask, questionnaire_bonus, wine_attributes

# Weight of the questionnaire bonus at serving time (see questionnaire_bonus). Chosen on the
# VALIDATION split with scripts/tune_bonus.py; override with the QUESTIONNAIRE_WEIGHT variable.
DEFAULT_QUESTIONNAIRE_WEIGHT = 0.5

# A recommended wine is explained by a liked wine when their learned representations are
# at least this close (cosine similarity).
LIKE_SIMILARITY = 0.9          # about the top 1 % of random wine pairs (0.83)
MAX_SIMILAR_REASONS = 3

# X-Wines has 60 dish labels, many with only a few wines ("Fish": 54, "Paella": 1) next to
# big ones ("Rich Fish": 5,699). The app offers these families; a family matches a wine
# when any of its labels is in the wine's Harmonize list.
DISH_FAMILIES = {
    "Red meat": ["Beef", "Lamb", "Veal", "Game Meat", "Meat", "Barbecue", "Grilled"],
    "Poultry": ["Poultry", "Chicken", "Duck", "Curry Chicken", "Light Stews"],
    "Pork & charcuterie": ["Pork", "Cured Meat"],
    "Fish": ["Fish", "Lean Fish", "Rich Fish", "Codfish", "Sushi", "Sashimi"],
    "Seafood": ["Shellfish", "Seafood", "Paella"],
    "Pasta & pizza": ["Pasta", "Pizza", "Lasagna", "Tagliatelle", "Risotto", "Tomato Dishes",
                      "Eggplant Parmigiana", "Yakissoba"],
    "Vegetarian": ["Vegetarian", "Mushrooms", "Salad", "Baked Potato"],
    "Cheese": ["Soft Cheese", "Maturated Cheese", "Hard Cheese", "Goat Cheese", "Blue Cheese",
               "Mild Cheese", "Cheese", "Medium-cured Cheese"],
    "Spicy food": ["Spicy Food"],
    "Aperitif & snacks": ["Appetizer", "Snack", "Aperitif", "French Fries", "Soufflé"],
    "Dessert": ["Sweet Dessert", "Fruit Dessert", "Dessert", "Fruit", "Cake", "Chocolate",
                "Cookies", "Citric Dessert", "Dried Fruits", "Chestnut", "Cream"],
}
from sommelier.models.hgib import HGIBKGAT


def load_model(model_dir, ds=None, ckg=None):
    """Rebuild the model saved by train.py. Returns (model, dataset, config)."""
    model_dir = Path(model_dir)
    config = json.loads((model_dir / "config.json").read_text())
    if ds is None:
        data_dir = Path(config["data_dir"])
        if not data_dir.is_absolute():                 # saved relative to the repository
            data_dir = Path(__file__).resolve().parents[3] / data_dir
        ds = load_processed(data_dir)
    dim = config["dim"]
    model = HGIBKGAT(ckg if ckg is not None else ds.ckg, dim=dim,
                     layer_dims=(dim, dim // 2, dim // 4), beta=config["beta"],
                     use_gre=config["use_gre"], use_questionnaire=config["use_questionnaire"],
                     use_hgib=config["use_hgib"])
    model.load_state_dict(torch.load(model_dir / "model.pt", map_location="cpu"))
    model.eval()
    return model, ds, config


def embeddings(model, edges=None):
    """Final node representations (one forward on the whole graph, no gradient)."""
    model.eval()
    with torch.no_grad():
        return model.forward(edges)[-1][0]


def with_guest_slots(ckg, n_guests):
    """Copy of the graph with n_guests empty user slots placed after the real users.

    Users must come first in the node numbering, so every wine / taste node id moves up by
    n_guests. The model weights do not depend on the number of users (users share one
    starting vector), so the trained model loads on this bigger graph unchanged.
    """
    k = n_guests
    kg = ckg.kg_triples.clone()
    kg[:, 0] += k
    kg[:, 2] += k
    answers = ckg.answer_triples.clone()
    answers[:, 2] += k
    behavior = {}
    for b, e in ckg.behavior_edges.items():
        e = e.clone()
        e[1] += k
        behavior[b] = e
    entity_index = {name: gid + k for name, gid in ckg.entity_index.items()}
    return CKG(ckg.n_users + k, ckg.n_wines, ckg.n_nodes + k, ckg.n_relations, ckg.user_index,
               ckg.wine_index, entity_index, ckg.relation_names, kg, behavior,
               ckg.dish_wines, answers)


class Recommender:
    """Recommendations for X-Wines users and for new app users (guests)."""

    def __init__(self, model_dir, data_dir, n_guests=1000, questionnaire_weight=None):
        if questionnaire_weight is None:
            questionnaire_weight = float(os.environ.get("QUESTIONNAIRE_WEIGHT",
                                                        DEFAULT_QUESTIONNAIRE_WEIGHT))
        self.questionnaire_weight = questionnaire_weight
        self.ds = load_processed(data_dir)
        base = self.ds.ckg
        self.n_real = base.n_users
        self.ckg = with_guest_slots(base, n_guests)
        self.model, _, self.config = load_model(model_dir, self.ds, self.ckg)
        self.model_version = Path(model_dir).name
        self.attrs = wine_attributes(self.ds.wines, base.wine_index)
        self.wines = self.ds.wines.set_index("WineID")
        self.local_to_wine_id = {i: wid for wid, i in base.wine_index.items()}
        liked = self.ds.train_liked[1].numpy()
        self.popularity = np.bincount(liked, minlength=base.n_wines)
        self.guests = {}            # app user id -> {"slot", "answers", "liked", "rated", "disliked"}
        self.dish_masks = {}
        self.Z = embeddings(self.model)

    # ------------------------------------------------------------------ guests
    def _slot(self, user_id):
        if user_id not in self.guests:
            slot = self.n_real + len(self.guests)
            if slot >= self.ckg.n_users:
                raise RuntimeError("no free guest slot: restart the API or raise n_guests")
            self.guests[user_id] = {"slot": slot, "answers": {}, "liked": [], "rated": [],
                                    "disliked": []}
        return self.guests[user_id]

    def _refresh(self):
        """Rebuild the edges with every guest's answers and feedback, then one forward."""
        ckg = self.ckg
        answer_rows, liked_rows, rated_rows = [], [], []
        first_q = len(KG_RELATIONS)
        for g in self.guests.values():
            for relation, key in answer_entities(g["answers"]):
                gid = ckg.entity_index.get(key)
                if gid is not None:          # an answer unknown to the graph is ignored
                    answer_rows.append((g["slot"], first_q + QUESTIONNAIRE_RELATIONS.index(relation), gid))
            for w in g["liked"]:
                liked_rows.append((g["slot"], w + ckg.n_users))
            for w in g["rated"]:
                rated_rows.append((g["slot"], w + ckg.n_users))
        answers = ckg.answer_triples
        if answer_rows:
            answers = torch.cat([answers, torch.tensor(answer_rows, dtype=torch.long)])
        behavior = {}
        extra = {"liked": liked_rows, "rated": rated_rows + liked_rows}
        for b, e in ckg.behavior_edges.items():
            rows = extra.get(b, [])
            if rows:
                e = torch.cat([e, torch.tensor(rows, dtype=torch.long).T], dim=1)
            behavior[b] = e
        self.Z = embeddings(self.model, self.model.build_edges(behavior, answers))

    def onboard(self, user_id, answers):
        """answers: dict with color, body, acidity, grapes, countries, discovery."""
        g = self._slot(user_id)
        g["answers"] = dict(answers)
        self._refresh()

    def feedback(self, user_id, wine_id, event_type, value=None):
        """like / rating >= 4 / add_to_cellar -> positive; dislike / rating < 4 -> negative."""
        g = self._slot(user_id)
        w = self.ds.ckg.wine_index.get(int(wine_id))
        if w is None:
            return
        positive = event_type in ("like", "add_to_cellar") or (event_type == "rating" and (value or 0) >= 4)
        negative = event_type == "dislike" or (event_type == "rating" and (value or 0) < 4)
        if positive and w not in g["liked"]:
            g["liked"].append(w)
        elif negative:
            if event_type == "rating" and w not in g["rated"]:
                g["rated"].append(w)
            if w not in g["disliked"]:
                g["disliked"].append(w)
        else:
            return                            # a "view" does not change the profile
        self._refresh()

    # ------------------------------------------------------------------ recommend
    def _user_node(self, user_id):
        if user_id in self.guests:
            return self.guests[user_id]["slot"], set(self.guests[user_id]["liked"] + self.guests[user_id]["disliked"])
        try:
            u = self.ds.ckg.user_index.get(int(user_id))
        except ValueError:
            u = None
        if u is None:
            return None, set()
        return u, set(self.ds.train_seen.get(u, set()))

    def _dish_mask(self, dish):
        """Wines that pair with a dish family (e.g. "Fish" = Fish, Lean Fish, Rich Fish...)
        or with one raw X-Wines dish label."""
        if dish not in self.dish_masks:
            labels = DISH_FAMILIES.get(dish, [dish])
            mask = np.zeros(self.ckg.n_wines, dtype=bool)
            for label in labels:
                mask |= dish_wines_mask(label, self.attrs)
            self.dish_masks[dish] = mask
        return self.dish_masks[dish]

    def recommend(self, user_id, dish=None, k=10):
        """Top-k wines: model score, wines listed for the dish first, seen wines removed."""
        node, seen = self._user_node(user_id)
        wines = self.Z[self.ckg.n_users:self.ckg.n_users + self.ckg.n_wines]
        guest = self.guests.get(user_id, {})
        answers = guest.get("answers") or self._answers_of(node)
        has_profile = node is not None and (node < self.n_real or bool(guest.get("answers"))
                                            or bool(guest.get("liked")))
        if not has_profile:                   # no questionnaire, no like yet: popularity
            scores = self.popularity.astype(float)
        else:
            with torch.no_grad():
                scores = (self.Z[node] @ wines.T).numpy().astype(float)
            # make the explicit answers count: a "red, full-bodied" user gets reds first
            scores = questionnaire_bonus(scores, answers, self.attrs, self.questionnaire_weight)
        if dish:
            scores = scores + self._dish_mask(dish) * 1e6
        for w in seen:
            scores[w] = -np.inf
        top = np.argsort(-scores)[:k]
        liked = guest.get("liked", [])
        # "close to the wine you liked" on the few closest wines only, so the taste reasons
        # stay visible on the others
        closest = [(self._closest_liked(int(w), liked), int(w)) for w in top]
        ranked = sorted((c for c in closest if c[0][0] is not None), key=lambda c: -c[0][1])
        keep = {w for _, w in ranked[:MAX_SIMILAR_REASONS]}
        return [self.describe(w, dish, answers, close=c[0] if w in keep else None,
                              personal=has_profile) for c, w in closest]

    def _closest_liked(self, w, liked):
        """(liked wine closest to wine w, cosine) when close enough, else (None, 0)."""
        if not liked:
            return None, 0.0
        n_u = self.ckg.n_users
        z = self.Z[n_u + w]
        L = self.Z[[n_u + x for x in liked]]
        sims = torch.nn.functional.cosine_similarity(L, z.unsqueeze(0)).numpy()
        best = int(np.argmax(sims))
        return (liked[best], float(sims[best])) if sims[best] >= LIKE_SIMILARITY else (None, 0.0)

    def _answers_of(self, node):
        if self.ds.questionnaires is None or node is None or node >= self.n_real:
            return {}
        if not hasattr(self, "_answers_by_node"):
            self._answers_by_node = {}
            for row in self.ds.questionnaires.to_dict("records"):
                u = self.ds.ckg.user_index.get(int(row["UserID"]))
                if u is not None:
                    self._answers_by_node[u] = row
        return self._answers_by_node.get(node, {})

    def describe(self, w, dish=None, answers=None, close=None, personal=True):
        """Wine card + a short reason built from what it shares with the user's answers,
        the wines they liked, and the dish. The reason only says what is true."""
        wine_id = self.local_to_wine_id[w]
        row = self.wines.loc[wine_id]
        grapes = list(row["Grapes"])
        reasons = []
        answers = answers or {}
        if isinstance(answers.get("color"), str) and row["Type"] == answers["color"]:
            reasons.append(row["Type"].lower())
        if isinstance(answers.get("body"), str) and row["Body"] == answers["body"]:
            reasons.append(row["Body"].lower())
        if isinstance(answers.get("acidity"), str) and row["Acidity"] == answers["acidity"]:
            reasons.append(f"{row['Acidity'].lower()} acidity")
        liked_grapes = set(answers.get("grapes") if answers.get("grapes") is not None else [])
        common = [g for g in grapes if g in liked_grapes]
        if common:
            reasons.append(", ".join(common))
        liked_countries = set(answers.get("countries") if answers.get("countries") is not None else [])
        if row["Country"] in liked_countries:
            reasons.append(f"from {row['Country']}")
        if close is not None:
            why = f"Similar to {self.wines.loc[self.local_to_wine_id[close], 'WineName']}, which you liked"
        elif reasons:
            why = "Matches your taste: " + ", ".join(reasons)
        elif personal:
            why = "Chosen for you from what people with a similar taste enjoy"
        else:
            why = "Popular with wine lovers"
        pairs = None
        if dish:
            labels = DISH_FAMILIES.get(dish, [dish])
            pairs = next((d for d in row["Harmonize"] if d in labels), None)
            if pairs:
                why += f". Pairs with {pairs.lower()}"
        rank = int((self.popularity > self.popularity[w]).sum()) + 1
        abv = row.get("ABV")
        # the same reasons as data, so the app can write them in any language
        matched = {}
        if isinstance(answers.get("color"), str) and row["Type"] == answers["color"]:
            matched["color"] = row["Type"]
        if isinstance(answers.get("body"), str) and row["Body"] == answers["body"]:
            matched["body"] = row["Body"]
        if isinstance(answers.get("acidity"), str) and row["Acidity"] == answers["acidity"]:
            matched["acidity"] = row["Acidity"]
        if common:
            matched["grapes"] = common
        if row["Country"] in liked_countries:
            matched["country"] = row["Country"]
        basis = ("similar" if close is not None else "taste" if reasons
                 else "personal" if personal else "popular")
        return {"wine_id": int(wine_id), "name": row["WineName"], "type": row["Type"],
                "body": row["Body"], "acidity": row.get("Acidity"), "grapes": grapes,
                "country": row["Country"], "region": row.get("RegionName"),
                "winery": row.get("WineryName"),
                "abv": float(abv) if abv is not None and abv == abv else None,
                "country_code": row.get("Code"),
                "popularity_rank": rank, "explanation": why,
                "similar_to_liked": close is not None,
                "basis": basis, "matched": matched, "pairs_with": pairs,
                "similar_to": (self.wines.loc[self.local_to_wine_id[close], "WineName"]
                               if close is not None else None)}

    def options(self):
        """Possible answers for the questionnaire page."""
        top_grapes = {}
        for gs in self.ds.wines["Grapes"]:
            for g in gs:
                top_grapes[g] = top_grapes.get(g, 0) + 1
        grapes = [g for g, _ in sorted(top_grapes.items(), key=lambda x: -x[1])[:40]]
        return {"color": sorted(self.ds.wines["Type"].dropna().unique()),
                "body": sorted(self.ds.wines["Body"].dropna().unique()),
                "acidity": sorted(self.ds.wines["Acidity"].dropna().unique()),
                "grapes": sorted(grapes),
                "countries": sorted(self.ds.wines["Country"].dropna().unique()),
                "discovery": ["explorer", "safe"],
                "dishes": sorted(self.ds.ckg.dish_wines),
                # what the app shows: a dozen families instead of 60 raw labels (many of
                # them have a handful of wines), with the number of wines in each
                "dish_families": [{"name": f, "wines": int(self._dish_mask(f).sum())}
                                  for f in DISH_FAMILIES if self._dish_mask(f).any()]}


def default_recommender():
    """Recommender built from the MODEL_DIR and DATA_DIR environment variables
    (default: the final V2 model, artifacts/full_k10, committed in the repository)."""
    root = Path(__file__).resolve().parents[3]
    model_dir = os.environ.get("MODEL_DIR", str(root / "artifacts" / "full_k10"))
    data_dir = os.environ.get("DATA_DIR", str(root / "data" / "processed" / "full_k10"))
    return Recommender(model_dir, data_dir)
