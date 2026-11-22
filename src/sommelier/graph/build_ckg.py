"""Collaborative knowledge graph (owner: PL).

Node index layout (one shared embedding table):
    [0, n_users)                                   users
    [n_users, n_users + n_wines)                   wines
    [n_users + n_wines, n_nodes)                   KG entities (grape, region, country, winery,
                                                   type, body, acidity, dish)

Only train interactions are used for the user-wine edges (no leakage). The knowledge part
comes from static wine metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import torch

from sommelier.data.questionnaire import answer_entities

KG_RELATIONS = ["has_grape", "from_region", "in_country", "made_by",
                "of_type", "has_body", "has_acidity", "pairs_with"]
BEHAVIORS = ["rated", "liked"]          # HGIB cascade, last one is the target
# questionnaire answers: user -> taste node (type, body, acidity, grape, country, discovery)
QUESTIONNAIRE_RELATIONS = ["likes_type", "likes_body", "likes_acidity",
                           "likes_grape", "likes_country", "discovery"]


@dataclass
class CKG:
    n_users: int
    n_wines: int
    n_nodes: int
    n_relations: int
    user_index: dict
    wine_index: dict
    entity_index: dict
    relation_names: list
    kg_triples: torch.Tensor                     # [T, 3] (head, relation, tail), global ids
    behavior_edges: dict = field(default_factory=dict)  # name -> [2, E] (user_gid, wine_gid)
    dish_wines: dict = field(default_factory=dict)      # dish name -> list of wine local ids
    answer_triples: torch.Tensor = None                 # [A, 3] (user, relation, taste node)

    def wine_gid(self, local):
        return local + self.n_users

    def entity_gid(self, name):
        return self.entity_index[name]


def build_ckg(train: pd.DataFrame, wines: pd.DataFrame, questionnaires=None) -> CKG:
    users = np.sort(train["UserID"].unique())
    wine_ids = np.sort(wines["WineID"].unique())
    user_index = {int(u): i for i, u in enumerate(users)}
    n_users = len(users)
    wine_index = {int(w): i for i, w in enumerate(wine_ids)}
    n_wines = len(wine_ids)

    entity_index: dict = {}
    triples = []

    def ent(kind, value):
        key = f"{kind}:{value}"
        if key not in entity_index:
            entity_index[key] = n_users + n_wines + len(entity_index)
        return entity_index[key]

    rel = {r: i for i, r in enumerate(KG_RELATIONS)}
    dish_wines: dict = {}
    for row in wines.itertuples(index=False):
        w = n_users + wine_index[int(row.WineID)]
        for g in row.Grapes:
            triples.append((w, rel["has_grape"], ent("grape", g)))
        region = ent("region", row.RegionName)
        triples.append((w, rel["from_region"], region))
        triples.append((region, rel["in_country"], ent("country", row.Country)))
        triples.append((w, rel["made_by"], ent("winery", row.WineryName)))
        triples.append((w, rel["of_type"], ent("type", row.Type)))
        triples.append((w, rel["has_body"], ent("body", row.Body)))
        triples.append((w, rel["has_acidity"], ent("acidity", row.Acidity)))
        for d in row.Harmonize:
            triples.append((w, rel["pairs_with"], ent("dish", d)))
            dish_wines.setdefault(d, []).append(wine_index[int(row.WineID)])

    # questionnaire answers: one edge from the user to each taste node they chose
    answer_triples = []
    if questionnaires is not None:
        first_q_rel = len(KG_RELATIONS)
        for answers in questionnaires.to_dict("records"):
            user_id = int(answers["UserID"])
            if user_id not in user_index:
                continue
            user = user_index[user_id]
            for relation, key in answer_entities(answers):
                kind, value = key.split(":", 1)
                rel_id = first_q_rel + QUESTIONNAIRE_RELATIONS.index(relation)
                answer_triples.append((user, rel_id, ent(kind, value)))
    if answer_triples:
        answer_triples = torch.tensor(answer_triples, dtype=torch.long)
    else:
        answer_triples = torch.zeros((0, 3), dtype=torch.long)

    behavior_edges = {}
    for b in BEHAVIORS:
        sub = train[train[b]] if b in train else train
        u = sub["UserID"].map(user_index).to_numpy()
        w = sub["WineID"].map(wine_index).to_numpy() + n_users
        behavior_edges[b] = torch.tensor(np.stack([u, w]), dtype=torch.long)

    n_nodes = n_users + n_wines + len(entity_index)
    # KG relations + questionnaire relations + one interaction relation per behavior
    # (inverse relations are added in edges_for_level)
    relation_names = KG_RELATIONS + QUESTIONNAIRE_RELATIONS + [f"user_{b}" for b in BEHAVIORS]
    return CKG(n_users, n_wines, n_nodes, len(relation_names), user_index, wine_index,
               entity_index, relation_names, torch.tensor(triples, dtype=torch.long),
               behavior_edges, dish_wines, answer_triples)


def edges_for_level(ckg: CKG, behavior: str, use_questionnaire: bool = True,
                    behavior_edges=None, answer_triples=None):
    """Directed edge list for one HGIB level: KG triples + questionnaire answers + behavior
    edges, both directions.

    behavior_edges / answer_triples replace the ones stored in the graph when given
    (used to simulate a user who gives 0, 1, 3... feedbacks).
    Returns head, relation, tail tensors. Inverse relations get ids shifted by n_relations.
    """
    kg = ckg.kg_triples
    if use_questionnaire:
        answers = ckg.answer_triples if answer_triples is None else answer_triples
        kg = torch.cat([kg, answers])
    if behavior_edges is None:
        b = ckg.behavior_edges[behavior]
    else:
        b = behavior_edges[behavior]
    r_b = ckg.relation_names.index(f"user_{behavior}")
    heads = [kg[:, 0], b[0]]
    rels = [kg[:, 1], torch.full((b.shape[1],), r_b)]
    tails = [kg[:, 2], b[1]]
    h, r, t = torch.cat(heads), torch.cat(rels), torch.cat(tails)
    # inverse edges so information flows wine -> user and entity -> wine
    return (torch.cat([h, t]), torch.cat([r, r + ckg.n_relations]), torch.cat([t, h]))
