# Pocket Sommelier

**Team Winder (Group 16)** · RecSys Startup Sprint 2026–2027

Pocket Sommelier recommends the right wine for a given person *and* the dish on their plate, and
explains why. Core RecSys paper: **HGIB** (Zhang et al., *Hierarchical Graph Information Bottleneck
for Multi-Behavior Recommendation*, RecSys 2025) on a **KGAT** graph backbone (Wang et al., KDD 2019).
Dataset: [X-Wines](https://github.com/rogerioxavier/X-Wines) (CC0-1.0).

| Member | Role |
|---|---|
| Romain | Project Lead (PL) |
| Antoine | Data Engineer (DE) |
| Alexandre | Lead ML Engineer (MLE-Core) |
| Quentin | ML Engineer (MLE-Ops) |
| Alexis | Systems Engineer (SE) |

## Run locally (under 10 minutes)

Requires Python 3.11 or 3.12.

```bash
# 1. clone
git clone https://github.com/romainarc/Project_Recommender_Systems_Winder-Pocket-Sommelier.git
cd Project_Recommender_Systems_Winder-Pocket-Sommelier

# 2. virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. dependencies (CPU only)
pip install -r requirements.txt

# 4. prepare the data (X-Wines Test, already in data/sample)
python scripts/prepare_data.py --preset test

# 5. start the API  ->  http://localhost:8000/docs
uvicorn api.main:app --reload

# 6. in a second terminal, start the frontend  ->  http://localhost:8501
streamlit run app/streamlit_app.py
```

Run the checks: `pytest -q`

## Week-2 checks

| Check | Command |
|---|---|
| Q1 data pipeline | `python scripts/prepare_data.py --preset full` (see below) |
| Q2 model forward pass | `python scripts/smoke_forward.py --data data/processed/test` |
| Q3 evaluation harness | `python scripts/evaluate_mock.py --data data/processed/test` |
| Q4 API with mock recommendations | `uvicorn api.main:app`, then `POST /recommend` |

## Full and Slim datasets

The Slim (150K ratings) and Full (21M ratings) versions are only on the
[X-Wines Google Drive](https://drive.google.com/drive/folders/1LqguJNV-aKh1PuWMVx5ELA61LPfGfuu_?usp=sharing).
Download the CSV files into `data/raw/` (they are git-ignored), then:

```bash
python scripts/prepare_data.py --preset slim
python scripts/prepare_data.py --preset full     # keeps 2019-2021, 10-core
```

If the file names differ, pass them explicitly:
`python scripts/prepare_data.py --preset full --wines data/raw/<wines>.csv --ratings data/raw/<ratings>.csv`.
Each run writes `data/processed/<preset>/stats.json` with the counts and the split dates.

## Data protocol

- Deduplicate (user, wine) pairs: the latest rating wins.
- Two behaviors for HGIB: **rated** (any rating, auxiliary) and **liked** (rating ≥ 4, target).
- Global temporal split on `Date`: 80 % train, 10 % validation, 10 % test.
  Validation and test keep liked ratings of warm users and wines only.
- Graphs, popularity and embeddings use train only. Evaluation ranks all wines and masks the wines
  a user already rated in train.

## Retraining

Training (`scripts/train.py`) and `scripts/retrain.py`, which merges the interactions logged by the
app, arrive in week 3.

## Repository layout

```
pocket-sommelier/
├── api/main.py                     FastAPI: /recommend (mock in week 2), /log_interaction, /dishes
├── app/streamlit_app.py            Streamlit frontend
├── configs/hgib_kgat.yaml          hyperparameters
├── data/sample/                    X-Wines Test (committed, used by CI)
├── data/raw/, data/processed/      git-ignored
├── scripts/                        prepare_data, smoke_forward, evaluate_mock
├── src/sommelier/
│   ├── data/                       preprocess.py, loaders.py
│   ├── graph/build_ckg.py          collaborative knowledge graph
│   ├── models/                     kgat.py, hgib.py, baselines.py
│   ├── evaluation/                 metrics.py, harness.py
│   └── db/schema.py                interactions, impressions (SQLAlchemy)
└── tests/                          pytest
```

## License

Code: [MIT](LICENSE). Data: X-Wines, CC0-1.0.
