"""Week-2 check Q2: one forward pass (and one backward step) of HGIB + KGAT without crashing.

    python scripts/smoke_forward.py --data data/processed/test
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import torch  # noqa: E402

from sommelier.data.loaders import load_processed  # noqa: E402
from sommelier.models.hgib import HGIBKGAT  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/processed/test")
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    torch.manual_seed(a.seed)

    ds = load_processed(ROOT / a.data)
    ckg = ds.ckg
    print(f"CKG: {ckg.n_users} users, {ckg.n_wines} wines, "
          f"{ckg.n_nodes - ckg.n_users - ckg.n_wines} entities, {len(ckg.kg_triples)} KG triples, "
          + ", ".join(f"{b}={e.shape[1]} edges" for b, e in ckg.behavior_edges.items()))

    model = HGIBKGAT(ckg)
    print(f"Model: HGIB-KGAT, {sum(p.numel() for p in model.parameters()):,} parameters, "
          f"{len(model.behaviors)} behavior levels {model.behaviors}")

    t0 = time.time()
    levels = model.forward()
    Z = levels[-1][0]
    users = torch.arange(min(8, ckg.n_users))
    scores = model.score_users(Z, users)
    dish = next(iter(ckg.dish_wines))
    dish_scores = model.score_users(Z, users, ckg.entity_gid(f"dish:{dish}"), lam=0.5)
    print(f"Forward pass OK in {time.time() - t0:.2f}s: Z {tuple(Z.shape)}, "
          f"scores {tuple(scores.shape)}, dish-conditioned ({dish}) {tuple(dish_scores.shape)}")
    assert torch.isfinite(scores).all() and torch.isfinite(dish_scores).all()

    # one optimisation step on the target behavior
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    idx = torch.randint(0, ds.train_liked.shape[1], (64,))
    u, pw = ds.train_liked[0, idx], ds.train_liked[1, idx]
    nw = torch.randint(0, ckg.n_wines, (64,))
    kg = ckg.kg_triples[torch.randint(0, len(ckg.kg_triples), (64,))]
    t_neg = torch.randint(ckg.n_users + ckg.n_wines, ckg.n_nodes, (64,))
    loss, parts = model.loss(u, pw, nw, (kg[:, 0], kg[:, 1], kg[:, 2], t_neg))
    opt.zero_grad(); loss.backward(); opt.step()
    assert torch.isfinite(loss)
    print(f"Backward step OK: loss={loss.item():.4f} (bpr={parts['bpr']:.4f}, "
          f"hsic={parts['ib_hsic']:.4f})")


if __name__ == "__main__":
    main()
