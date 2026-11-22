"""Training loop for HGIB + KGAT (owner: MLE-Ops).

One epoch = one pass over the train positives (liked), in big batches: each step runs the
model on the whole graph, so big batches mean fewer (expensive) steps.

After every epoch, on the SAME fixed samples:
    train_loss  BPR loss on a sample of train positives
    valid_loss  BPR loss on the validation positives        -> loss curves (week-3 Q1)
    valid NDCG@10 / Recall@20 with the evaluation harness   -> early stopping

The best epoch (highest validation NDCG@10) is saved. The test split is never used here.
"""
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from sommelier.data.loaders import load_processed
from sommelier.evaluation.harness import evaluate
from sommelier.models.hgib import HGIBKGAT


REPO_ROOT = Path(__file__).resolve().parents[3]


def portable_path(path):
    """Path relative to the repository when it is inside it, so a saved model (config.json)
    works on any machine that clones the repository."""
    p = Path(path).resolve()
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def make_score_fn(model):
    """Run the graph once, then score users with a dot product (used by the harness)."""
    model.eval()
    with torch.no_grad():
        Z = model.forward()[-1][0]
    wines = Z[model.wine_slice()]

    def score(users):
        with torch.no_grad():
            return (Z[torch.as_tensor(users)] @ wines.T).numpy()
    return score


def bpr_on_pairs(model, users, pos, neg):
    """BPR loss of the final level on fixed (user, positive, negative) triples, no gradient."""
    model.eval()
    with torch.no_grad():
        Z = model.forward()[-1][0]
        n_u = model.ckg.n_users
        u, p, n = Z[users], Z[pos + n_u], Z[neg + n_u]
        return float(F.softplus(-((u * p).sum(-1) - (u * n).sum(-1))).mean())


def sample_eval_users(truth, max_users, rng):
    users = sorted(truth)
    if len(users) > max_users:
        users = sorted(rng.choice(users, size=max_users, replace=False).tolist())
    return {u: truth[u] for u in users}


def pairs_from_truth(truth, n_wines, rng):
    users, pos = [], []
    for u, wines in truth.items():
        for w in wines:
            users.append(u)
            pos.append(w)
    users = torch.tensor(users)
    pos = torch.tensor(pos)
    neg = torch.as_tensor(rng.integers(0, n_wines, len(users)))
    return users, pos, neg


def train(data_dir, out_dir, epochs=30, batch_size=16384, lr=5e-3, dim=64, beta=0.1,
          lambda_kg=0.1, patience=3, max_eval_users=3000, seed=42,
          use_questionnaire=True, use_hgib=True, use_gre=True, log=print):
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    ds = load_processed(data_dir)
    ckg = ds.ckg
    config = dict(data_dir=portable_path(data_dir), epochs=epochs, batch_size=batch_size, lr=lr, dim=dim,
                  beta=beta, lambda_kg=lambda_kg, patience=patience, seed=seed,
                  use_questionnaire=use_questionnaire, use_hgib=use_hgib, use_gre=use_gre)
    (out / "config.json").write_text(json.dumps(config, indent=2))

    # layer sizes follow dim: 64 -> (64, 32, 16), 32 -> (32, 16, 8). Use --dim 32 on 8 GB of RAM.
    model = HGIBKGAT(ckg, dim=dim, layer_dims=(dim, dim // 2, dim // 4), beta=beta,
                     use_gre=use_gre, use_questionnaire=use_questionnaire, use_hgib=use_hgib)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    log(f"graph: {ckg.n_users} users, {ckg.n_wines} wines, "
        f"{ckg.n_nodes - ckg.n_users - ckg.n_wines} taste/KG nodes | "
        f"model: {sum(p.numel() for p in model.parameters()):,} parameters | config: {config}")

    # fixed samples, so every epoch is measured on exactly the same pairs and users
    valid_eval = sample_eval_users(ds.valid_truth, max_eval_users, rng)
    v_users, v_pos, v_neg = pairs_from_truth(valid_eval, ckg.n_wines, rng)
    pick = rng.choice(ds.train_liked.shape[1], size=min(len(v_users), ds.train_liked.shape[1]),
                      replace=False)
    t_users, t_pos = ds.train_liked[0, pick], ds.train_liked[1, pick]
    t_neg = torch.as_tensor(rng.integers(0, ckg.n_wines, len(t_users)))

    history = []
    best_ndcg, best_epoch, bad_epochs = -1.0, 0, 0
    n_pos = ds.train_liked.shape[1]
    for epoch in range(1, epochs + 1):
        start = time.time()
        model.train()
        order = torch.randperm(n_pos)
        step_losses = []
        for i in range(0, n_pos, batch_size):
            idx = order[i:i + batch_size]
            users, pos = ds.train_liked[0, idx], ds.train_liked[1, idx]
            neg = torch.randint(0, ckg.n_wines, (len(idx),))
            kg = ckg.kg_triples[torch.randint(0, len(ckg.kg_triples), (len(idx),))]
            kg_neg = torch.randint(ckg.n_users + ckg.n_wines, ckg.n_nodes, (len(idx),))
            loss, parts = model.loss(users, pos, neg, (kg[:, 0], kg[:, 1], kg[:, 2], kg_neg),
                                     lambda_kg=lambda_kg)
            if not torch.isfinite(loss):
                raise RuntimeError(f"loss is {loss.item()} at epoch {epoch}: training diverged")
            opt.zero_grad()
            loss.backward()
            opt.step()
            step_losses.append(loss.item())

        train_loss = bpr_on_pairs(model, t_users, t_pos, t_neg)
        valid_loss = bpr_on_pairs(model, v_users, v_pos, v_neg)
        metrics = evaluate(make_score_fn(model), valid_eval, ds.train_seen, ckg.n_wines)
        row = dict(epoch=epoch, objective=float(np.mean(step_losses)), train_loss=train_loss,
                   valid_loss=valid_loss, valid_ndcg10=metrics["NDCG@10"],
                   valid_recall20=metrics["Recall@20"], seconds=round(time.time() - start, 1))
        history.append(row)
        log(f"epoch {epoch:2d} | objective {row['objective']:.4f} | train loss {train_loss:.4f} "
            f"| valid loss {valid_loss:.4f} | valid NDCG@10 {row['valid_ndcg10']:.4f} "
            f"| Recall@20 {row['valid_recall20']:.4f} | {row['seconds']}s")

        if row["valid_ndcg10"] > best_ndcg:
            best_ndcg, best_epoch, bad_epochs = row["valid_ndcg10"], epoch, 0
            torch.save(model.state_dict(), out / "model.pt")
        else:
            bad_epochs += 1
            if bad_epochs >= patience:
                log(f"early stopping: no improvement for {patience} epochs")
                break

    (out / "history.json").write_text(json.dumps(history, indent=2))
    summary = dict(best_epoch=best_epoch, best_valid_ndcg10=best_ndcg, epochs_run=len(history))
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    plot_history(history, best_epoch, out / "curves.png")
    log(f"best epoch {best_epoch} (valid NDCG@10 {best_ndcg:.4f}) -> {out / 'model.pt'}")
    return model, history, summary


def plot_history(history, best_epoch, path):
    """Two panels: train vs valid loss, and validation NDCG@10 / Recall@20."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ep = [h["epoch"] for h in history]
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.6))
    a.plot(ep, [h["train_loss"] for h in history], marker="o", label="train")
    a.plot(ep, [h["valid_loss"] for h in history], marker="o", label="validation")
    a.set_title("BPR loss")
    a.set_xlabel("epoch")
    a.legend()
    b.plot(ep, [h["valid_ndcg10"] for h in history], marker="o", label="NDCG@10")
    b.plot(ep, [h["valid_recall20"] for h in history], marker="o", label="Recall@20")
    b.set_title("Validation ranking metrics")
    b.set_xlabel("epoch")
    b.legend()
    for ax in (a, b):
        ax.axvline(best_epoch, color="grey", linestyle="--", linewidth=1)
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
