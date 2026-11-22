"""KGAT encoder (owner: MLE-Core).

Wang et al., "KGAT: Knowledge Graph Attention Network for Recommendation", KDD 2019.
Pure-PyTorch implementation (scatter via index_add_), no PyTorch Geometric dependency.

    pi(h, r, t) = (W_r e_t)^T tanh(W_r e_h + e_r)        relation-aware attention
    alpha       = softmax over the neighbours of h
    e_N(h)      = sum_t alpha(h, r, t) e_t
    e_h'        = LeakyReLU(W1 (e_h + e_N)) + LeakyReLU(W2 (e_h * e_N))   bi-interaction
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


def segment_softmax(scores: torch.Tensor, index: torch.Tensor, n: int) -> torch.Tensor:
    """Softmax of ``scores`` grouped by ``index`` (numerically stable)."""
    max_per = torch.full((n,), float("-inf"), device=scores.device)
    max_per = max_per.scatter_reduce(0, index, scores, reduce="amax", include_self=True)
    ex = torch.exp(scores - max_per[index])
    denom = torch.zeros(n, device=scores.device).index_add_(0, index, ex)
    return ex / (denom[index] + 1e-16)


class KGATLayer(nn.Module):
    def __init__(self, dim_in: int, dim_out: int, dropout: float = 0.1):
        super().__init__()
        self.w1 = nn.Linear(dim_in, dim_out)
        self.w2 = nn.Linear(dim_in, dim_out)
        self.drop = nn.Dropout(dropout)

    def forward(self, x, head, tail, att):
        """att: one weight per edge (head <- tail). e_N(h) = sum of att * e_t over neighbours."""
        msg = x[tail] * att.unsqueeze(-1)
        e_n = torch.zeros_like(x).index_add_(0, head, msg)
        out = F.leaky_relu(self.w1(x + e_n)) + F.leaky_relu(self.w2(x * e_n))
        return self.drop(out)


class KGATEncoder(nn.Module):
    """L KGAT layers. Input: node embeddings. Output: concatenation of all layers.

    As in the original KGAT implementation, the attention weights are computed WITHOUT
    gradient: W_r and the relation embeddings learn through the TransR loss, and the
    attention is recomputed from them at every forward. Without this, autograd would keep
    several [edges x 64] tensors per relation and run out of memory on the Full graph.
    """

    def __init__(self, n_relations_total: int, dim: int = 64, rel_dim: int = 64,
                 layer_dims=(64, 32, 16), dropout: float = 0.1):
        super().__init__()
        self.rel_emb = nn.Embedding(n_relations_total, rel_dim)
        self.W_r = nn.Parameter(torch.empty(n_relations_total, dim, rel_dim))
        nn.init.xavier_uniform_(self.rel_emb.weight)
        nn.init.xavier_uniform_(self.W_r)
        dims = [dim, *layer_dims]
        self.layers = nn.ModuleList(KGATLayer(dims[i], dims[i + 1], dropout)
                                    for i in range(len(layer_dims)))
        self.out_dim = sum(dims)

    @torch.no_grad()
    def attention(self, x, head, rel, tail):
        """pi(h, r, t) = (W_r e_t)^T tanh(W_r e_h + e_r), softmax over the neighbours of h."""
        score = torch.empty(head.shape[0], device=x.device)
        for r in rel.unique():                     # one relation at a time: low memory
            m = rel == r
            Wr = self.W_r[r]
            r_h = x[head[m]] @ Wr
            r_t = x[tail[m]] @ Wr
            score[m] = (r_t * torch.tanh(r_h + self.rel_emb.weight[r])).sum(-1)
        return segment_softmax(score, head, x.shape[0])

    def forward(self, x, head, rel, tail, edge_weight=None):
        att = self.attention(x, head, rel, tail)
        if edge_weight is not None:                # HGIB graph refinement (keeps its gradient)
            att = att * edge_weight
        outs = [x]
        h = x
        for layer in self.layers:
            h = layer(h, head, tail, att)
            outs.append(F.normalize(h, dim=-1))
        return torch.cat(outs, dim=-1)

    def transr_loss(self, x, h, r, t_pos, t_neg):
        """KG embedding loss (TransR, pairwise): ||W_r e_h + e_r - W_r e_t||^2."""
        Wr = self.W_r[r]
        proj = lambda idx: torch.bmm(x[idx].unsqueeze(1), Wr).squeeze(1)
        e_r = self.rel_emb(r)
        pos = ((proj(h) + e_r - proj(t_pos)) ** 2).sum(-1)
        neg = ((proj(h) + e_r - proj(t_neg)) ** 2).sum(-1)
        return F.softplus(pos - neg).mean()
