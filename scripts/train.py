"""Train HGIB + KGAT and save the best model, the loss curves and the history.

Examples
--------
    python scripts/train.py --data data/processed/slim --out artifacts/slim
    python scripts/train.py --data data/processed/full --out artifacts/full
    python scripts/train.py --data data/processed/full_k10 --out artifacts/full_k10 --dim 16 --lr 0.02 --batch-size 32768.

Ablations (same data, one component switched off):
    python scripts/train.py --data data/processed/full --out artifacts/full_no_questionnaire --no-questionnaire
    python scripts/train.py --data data/processed/full --out artifacts/full_no_hgib --no-hgib
    python scripts/train.py --data data/processed/full --out artifacts/full_no_gre --no-gre
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sommelier.training.train import train  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/processed/slim")
    p.add_argument("--out", default="artifacts/slim")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch-size", type=int, default=16384)
    p.add_argument("--lr", type=float, default=5e-3)
    p.add_argument("--dim", type=int, default=64,
                   help="embedding size; 32 halves the memory (needed on 8 GB of RAM)")
    p.add_argument("--beta", type=float, default=0.1, help="weight of the HSIC bottleneck term")
    p.add_argument("--patience", type=int, default=3, help="early stopping patience (epochs)")
    p.add_argument("--max-eval-users", type=int, default=3000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--no-questionnaire", action="store_true")
    p.add_argument("--no-hgib", action="store_true")
    p.add_argument("--no-gre", action="store_true")
    a = p.parse_args()

    train(ROOT / a.data, ROOT / a.out, epochs=a.epochs, batch_size=a.batch_size, lr=a.lr,
          dim=a.dim, beta=a.beta, patience=a.patience, max_eval_users=a.max_eval_users,
          seed=a.seed, use_questionnaire=not a.no_questionnaire, use_hgib=not a.no_hgib,
          use_gre=not a.no_gre, log=lambda m: print(m, flush=True))


if __name__ == "__main__":
    main()
