"""Run the data pipeline (V1 and V2 presets)

Examples
Test version (committed in data/sample, used by CI):
    python scripts/prepare_data.py --preset test

Full versions (download first from the X-Wines Google Drive into data/raw/):
    python scripts/prepare_data.py --preset full_k10   # V2, final model: 2021, 10-core (1.7M ratings)
    python scripts/prepare_data.py --preset full       # V1 (Week 3 report): 2021, 20-core (443K ratings)
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sommelier.data.preprocess import PrepConfig, run  # noqa: E402

PRESETS = {
    "test": dict(wines="data/sample/XWines_Test_100_wines.csv",
                 ratings="data/sample/XWines_Test_1K_ratings.csv",
                 out="data/processed/test", min_year=None, kcore=1),
    "slim": dict(wines="data/raw/XWines_Slim_1K_wines.csv",
                 ratings="data/raw/XWines_Slim_150K_ratings.csv",
                 out="data/processed/slim", min_year=None, kcore=5),
    "full": dict(wines="data/raw/XWines_Full_100K_wines.csv",
                 ratings="data/raw/XWines_Full_21M_ratings.csv",
                 out="data/processed/full", min_year=2021, kcore=20),
    "full_k10": dict(wines="data/raw/XWines_Full_100K_wines.csv",
                     ratings="data/raw/XWines_Full_21M_ratings.csv",
                     out="data/processed/full_k10", min_year=2021, kcore=10),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--preset", choices=PRESETS, default="test")
    p.add_argument("--wines"); p.add_argument("--ratings"); p.add_argument("--out")
    p.add_argument("--min-year", type=int); p.add_argument("--kcore", type=int)
    a = p.parse_args()

    cfg = dict(PRESETS[a.preset])
    for key in ("wines", "ratings", "out", "min_year", "kcore"):
        if getattr(a, key) is not None:
            cfg[key] = getattr(a, key)

    start = time.time()
    stats = run(ROOT / cfg["wines"], ROOT / cfg["ratings"], ROOT / cfg["out"],
                PrepConfig(min_year=cfg["min_year"], kcore=cfg["kcore"]))
    stats["seconds"] = round(time.time() - start, 1)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
