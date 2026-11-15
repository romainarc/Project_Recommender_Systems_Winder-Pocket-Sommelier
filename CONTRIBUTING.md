# Contributing

## Workflow

1. Pick or open an issue and assign yourself.
2. Create a branch from an up-to-date `main`:
   ```bash
   git checkout main && git pull
   git checkout -b feat/<short-name>      # or fix/, docs/, data/
   ```
3. Commit small, clear steps. Message format: `<area>: <what changed>`
   (e.g. `train: add early stopping on val NDCG@20`).
4. Run `pytest -q` before pushing.
5. Push the branch and open a pull request to `main`. Write `Closes #<issue>` in the description.
6. One review is required, and CI must pass, before merging. Do not push directly to `main`.

## Branch names

| Prefix | Use |
|---|---|
| `feat/` | new feature (model, endpoint, page) |
| `fix/` | bug fix |
| `data/` | data pipeline, preprocessing |
| `docs/` | README, reports |

## Data

Never commit files from `data/raw/`, `data/processed/` or `artifacts/` (they are git-ignored).
Only the X-Wines Test sample in `data/sample/` is versioned.
