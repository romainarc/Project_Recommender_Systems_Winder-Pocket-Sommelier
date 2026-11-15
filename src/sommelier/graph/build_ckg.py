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

KG_RELATIONS = ["has_grape", "from_region", "in_country", "made_by",
                "of_type", "has_body", "has_acidity", "pairs_with"]
BEHAVIORS = ["rated", "liked"]          # HGIB cascade, last one is the target


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

    def wine_gid(self, local):
        return local + self.n_users

    def entity_gid(self, name):
        return self.entity_index[name]


def build_ckg(train: pd.DataFrame, wines: pd.DataFrame) -> CKG:
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

    behavior_edges = {}
    for b in BEHAVIORS:
        sub = train[train[b]] if b in train else train
        u = sub["UserID"].map(user_index).to_numpy()
        w = sub["WineID"].map(wine_index).to_numpy() + n_users
        behavior_edges[b] = torch.tensor(np.stack([u, w]), dtype=torch.long)

    n_nodes = n_users + n_wines + len(entity_index)
    # KG relations + one interaction relation per behavior (+ inverse handled by the encoder)
    relation_names = KG_RELATIONS + [f"user_{b}" for b in BEHAVIORS]
    return CKG(n_users, n_wines, n_nodes, len(relation_names), user_index, wine_index,
               entity_index, relation_names, torch.tensor(triples, dtype=torch.long),
               behavior_edges, dish_wines)


def edges_for_level(ckg: CKG, behavior: str):
    """Directed edge list for one HGIB level: KG triples + behavior edges, both directions.

    Returns head, relation, tail tensors. Inverse relations get ids shifted by n_relations.
    """
    kg = ckg.kg_triples
    b = ckg.behavior_edges[behavior]
    r_b = ckg.relation_names.index(f"user_{behavior}")
    heads = [kg[:, 0], b[0]]
    rels = [kg[:, 1], torch.full((b.shape[1],), r_b)]
    tails = [kg[:, 2], b[1]]
    h, r, t = torch.cat(heads), torch.cat(rels), torch.cat(tails)
    # inverse edges so information flows wine -> user and entity -> wine
    return (torch.cat([h, t]), torch.cat([r, r + ckg.n_relations]), torch.cat([t, h]))
