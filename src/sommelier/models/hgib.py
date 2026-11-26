"""HGIB on a KGAT backbone (owner: MLE-Core). Core RecSys paper of the project.

Zhang et al., "Hierarchical Graph Information Bottleneck for Multi-Behavior Recommendation",
RecSys 2025.

One graph per behavior, ordered as a cascade (rated -> liked). Level l encodes the output of
level l-1 on its own behavior graph (KG triples + behavior edges):

    Z_l = KGAT_l(H_{l-1}, G_l)          H_l = Proj_l(Z_l)

Information-bottleneck objective, per level:
    max  I(Z_l ; Y)  -  beta * I(H_l ; H_{l-1})
      I(Z_l ; Y)          ~ BPR loss on the target behavior (liked)
      I(H_l ; H_{l-1})    ~ HSIC (Hilbert-Schmidt independence criterion)

Graph Refinement Encoder (GRE): a learnable, relaxed-Bernoulli edge mask on behavior edges
that down-weights noisy interactions during training.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from sommelier.graph.build_ckg import BEHAVIORS, CKG, edges_for_level
from sommelier.models.kgat import KGATEncoder


def hsic(x: torch.Tensor, y: torch.Tensor, sigma: float | None = None) -> torch.Tensor:
    """Biased HSIC estimator with Gaussian kernels (median heuristic for sigma)."""
    n = x.shape[0]

    def kernel(z):
        d = torch.cdist(z, z) ** 2
        s = sigma if sigma is not None else d.detach().median().clamp_min(1e-6)
        return torch.exp(-d / (2 * s))

    K, L = kernel(x), kernel(y)
    H = torch.eye(n, device=x.device) - 1.0 / n
    return torch.trace(K @ H @ L @ H) / (n - 1) ** 2


class GraphRefinement(nn.Module):
    """Learnable edge keep-probability for user-wine edges (KG edges keep weight 1).

    The score of an edge is a weighted dot product of its two ends (one linear layer):
    light enough for the hundreds of thousands of edges of the Full graph.
    """

    def __init__(self, dim: int, temperature: float = 0.5):
        super().__init__()
        self.mlp = nn.Linear(dim, 1)
        self.temperature = temperature

    def forward(self, x, head, tail, is_behavior):
        w = torch.ones(head.shape[0], device=x.device)
        logits = self.mlp(x[head[is_behavior]] * x[tail[is_behavior]]).squeeze(-1)
        if self.training:   # relaxed Bernoulli (Gumbel-sigmoid) sample
            u = torch.rand_like(logits).clamp(1e-6, 1 - 1e-6)
            logits = logits + torch.log(u) - torch.log(1 - u)
        w[is_behavior] = torch.sigmoid(logits / self.temperature)
        return w


class HGIBKGAT(nn.Module):
    """HGIB + KGAT with inductive users.

    Users have NO personal embedding: they all start from the same learned vector, so a user
    is described only by its neighbours in the graph (questionnaire answers + wines rated or
    liked). A new user, or a user who just gave a new feedback, gets a profile without
    retraining: add the edges and run forward again.

    Ablation switches:
        use_questionnaire=False  -> the questionnaire edges are removed from the graph
        use_hgib=False           -> plain KGAT on the target behavior only (no rated level,
                                    no information bottleneck)
    """

    def __init__(self, ckg: CKG, dim: int = 64, layer_dims=(64, 32, 16),
                 beta: float = 0.1, use_gre: bool = True, behaviors=BEHAVIORS, dropout=0.1,
                 use_questionnaire: bool = True, use_hgib: bool = True):
        super().__init__()
        self.ckg = ckg
        self.use_questionnaire = use_questionnaire
        self.use_hgib = use_hgib
        if use_hgib:
            self.behaviors = list(behaviors)
            self.beta = beta
        else:
            self.behaviors = [behaviors[-1]]   # target behavior only
            self.beta = 0.0
        self.use_gre = use_gre and use_hgib

        # one shared starting vector for every user + one vector per wine / taste node
        self.user_token = nn.Parameter(torch.empty(1, dim))
        nn.init.xavier_uniform_(self.user_token)
        self.node_emb = nn.Embedding(ckg.n_nodes - ckg.n_users, dim)
        nn.init.xavier_uniform_(self.node_emb.weight)

        n_rel = 2 * ckg.n_relations                      # + inverse relations
        self.encoders = nn.ModuleList(KGATEncoder(n_rel, dim, dim, layer_dims, dropout)
                                      for _ in self.behaviors)
        out_dim = self.encoders[0].out_dim
        self.proj = nn.ModuleList(nn.Linear(out_dim, dim) for _ in self.behaviors)
        self.gre = nn.ModuleList(GraphRefinement(dim) for _ in self.behaviors)
        self.out_dim = out_dim
        self._edges = self.build_edges()

    def build_edges(self, behavior_edges=None, answer_triples=None):
        """Edge lists of every level. Pass other behavior edges / answers to simulate users
        with a different history (feedback curve, new app user)."""
        ckg = self.ckg
        beh_rel = []
        for b in self.behaviors:
            beh_rel.append(ckg.relation_names.index(f"user_{b}"))
        beh_rel = torch.tensor(beh_rel)

        edges = []
        for b in self.behaviors:
            h, r, t = edges_for_level(ckg, b, self.use_questionnaire, behavior_edges, answer_triples)
            is_beh = torch.isin(r % ckg.n_relations, beh_rel)
            edges.append((h, r, t, is_beh))
        return edges

    def initial_embeddings(self):
        users = self.user_token.expand(self.ckg.n_users, -1)
        return torch.cat([users, self.node_emb.weight])

    def forward(self, edges=None):
        """Returns per-level outputs: list of (Z_l [n_nodes, out_dim], H_l, H_prev)."""
        if edges is None:
            edges = self._edges
        H = self.initial_embeddings()
        levels = []
        for enc, proj, gre, (h, r, t, is_beh) in zip(self.encoders, self.proj, self.gre, edges):
            w = gre(H, h, t, is_beh) if self.use_gre else None
            Z = enc(H, h, r, t, edge_weight=w)
            H_next = proj(Z)
            levels.append((Z, H_next, H))
            H = H_next
        return levels

    # ---------- scoring ----------
    def wine_slice(self):
        return slice(self.ckg.n_users, self.ckg.n_users + self.ckg.n_wines)

    def score_users(self, Z, user_idx, dish_gid=None, lam: float = 0.0):
        """Scores of every wine for a batch of users: [B, n_wines]. Optional dish context."""
        wines = Z[self.wine_slice()]
        s = Z[user_idx] @ wines.T
        if dish_gid is not None and lam:
            s = s + lam * (Z[dish_gid] @ wines.T)
        return s

    # ---------- training objective ----------
    def loss(self, users, pos_wines, neg_wines, kg_batch=None, lambda_kg: float = 0.1,
             hsic_nodes: int = 256):
        """users: local ids; pos/neg_wines: local wine ids (target behavior)."""
        levels = self.forward()
        n_u = self.ckg.n_users
        bpr_total, ib_total = 0.0, 0.0
        for Z, H_l, H_prev in levels:
            u, p, n = Z[users], Z[pos_wines + n_u], Z[neg_wines + n_u]
            bpr_total = bpr_total + F.softplus(-((u * p).sum(-1) - (u * n).sum(-1))).mean()
            idx = torch.cat([users, pos_wines + n_u]).unique()[:hsic_nodes]
            ib_total = ib_total + hsic(H_l[idx], H_prev[idx])
        loss = bpr_total + self.beta * ib_total
        if kg_batch is not None:
            h, r, t, t_neg = kg_batch
            loss = loss + lambda_kg * self.encoders[0].transr_loss(self.initial_embeddings(), h, r, t, t_neg)
        return loss, {"bpr": float(bpr_total.detach()), "ib_hsic": float(ib_total.detach())}
