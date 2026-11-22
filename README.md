# Pocket Sommelier

**Team Winder (Group 16)** · RecSys Startup Sprint 2026–2027

Pocket Sommelier recommends wines from a short **taste questionnaire** (colour, body, acidity,
grapes, countries, discovery vs. safe choices) and learns from the user's **feedback** (like,
dislike, rating, cellar): the more feedback, the better the list. The dish is a context filter.

Model: **HGIB** (Zhang et al., *Hierarchical Graph Information Bottleneck for Multi-Behavior
Recommendation*, RecSys 2025) on a **KGAT** backbone (Wang et al., KDD 2019). Questionnaire answers
are edges from the user to the same taste nodes as the wines (type, body, acidity, grape, country),
so a new user gets recommendations without retraining.
Dataset: [X-Wines](https://github.com/rogerioxavier/X-Wines) (CC0-1.0).

| Member | Role |
|---|---|
| Romain | Project Lead (PL) |
| Antoine | Data Engineer (DE) |
| Alexandre | Lead ML Engineer (MLE-Core) |
| Quentin | ML Engineer (MLE-Ops) |
| Alexis | Systems Engineer (SE) |

## Quick start (under 10 minutes, no download)

Uses the small X-Wines Test version committed in `data/sample/`. Python 3.11 or 3.12.

```bash
git clone <REPO_URL> pocket-sommelier && cd pocket-sommelier
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1. data: clean, temporal split, simulated questionnaires
python scripts/prepare_data.py --preset test

# 2. a small model (about 1 minute)
python scripts/train.py --data data/processed/test --out artifacts/test --batch-size 128 --epochs 10

# 3. API (terminal 1)  ->  http://localhost:8000/docs
MODEL_DIR=artifacts/test DATA_DIR=data/processed/test uvicorn api.main:app
#   Windows PowerShell: $env:MODEL_DIR="artifacts/test"; $env:DATA_DIR="data/processed/test"; uvicorn api.main:app

# 4. app (terminal 2)  ->  http://localhost:8501
streamlit run app/streamlit_app.py
```

Checks: `python -m pytest -q`

## Full pipeline (results of the report)

1. Download from the [X-Wines Google Drive](https://drive.google.com/drive/folders/1LqguJNV-aKh1PuWMVx5ELA61LPfGfuu_?usp=sharing)
   into `data/raw/`: `XWines_Slim_1K_wines.csv`, `XWines_Slim_150K_ratings.csv`,
   `XWines_Full_100K_wines.csv`, `XWines_Full_21M_ratings.csv` (unzip it).
2. Prepare the data:
   ```bash
   python scripts/prepare_data.py --preset slim
   python scripts/prepare_data.py --preset full --min-year 2021 --kcore 20     # V1
   ```
3. Train (Slim: ~10 min on a laptop; Full: use `--dim 32` on 8 GB of RAM, or Google Colab):
   ```bash
   python scripts/train.py --data data/processed/slim --out artifacts/slim --batch-size 4096
   python scripts/train.py --data data/processed/full --out artifacts/full --batch-size 8192 --lr 0.01 --patience 5
   ```
   Ablations: add `--no-questionnaire`, `--no-hgib` or `--no-gre` (and another `--out`).
4. Evaluate on the test split (table + feedback curve), then the qualitative check:
   ```bash
   python scripts/evaluate.py --data data/processed/slim --models artifacts/slim artifacts/slim_no_questionnaire artifacts/slim_no_hgib --out artifacts/results_slim
   python scripts/sample_users.py --model artifacts/slim --data data/processed/slim
   ```
5. Serve a trained model: set `MODEL_DIR` and `DATA_DIR` (default `artifacts/slim`,
   `data/processed/slim`) and start the API and the app as in the quick start.

## Data and evaluation protocol

- Deduplicated (user, wine) pairs (latest rating wins); two behaviors for HGIB: **rated** (any
  rating) and **liked** (rating ≥ 4, the target).
- Global **temporal split** on `Date`: 80 % train, 10 % validation, 10 % test (liked ratings of
  warm users and wines only). Graphs, popularity, embeddings and questionnaires use **train only**.
- **Simulated questionnaires**: built from each user's liked train wines, with 20 % of answers
  removed and 10 % replaced at random (real answers are imperfect).
- Full ranking over every wine; train wines masked. Baselines: Random, Most-popular,
  "dish → wines" query, "dish + questionnaire → popularity" rule.
- **Feedback curve**: test users become new users (train history removed), keep their
  questionnaire and give back their n most recent liked wines (n = 0, 1, 3, 5, 10).

## API

| Endpoint | What it does |
|---|---|
| `GET /health`, `GET /options`, `GET /dishes` | Status, questionnaire choices, dishes |
| `POST /onboard` | Saves the questionnaire (`questionnaire_answers`) and builds the profile |
| `POST /recommend` | Top-k wines from the trained model, dish first; logged in `impressions` |
| `POST /log_interaction` | like / dislike / rating / add_to_cellar → `interactions`, profile updated |

## Repository layout

```
pocket-sommelier/
├── api/main.py                  FastAPI (trained model)
├── app/streamlit_app.py         questionnaire + recommendations + feedback
├── configs/hgib_kgat.yaml
├── data/sample/                 X-Wines Test (committed)
├── data/raw/, data/processed/   git-ignored
├── scripts/                     prepare_data, train, evaluate, sample_users, smoke_forward
├── src/sommelier/
│   ├── data/                    preprocess.py, questionnaire.py, loaders.py
│   ├── graph/build_ckg.py       knowledge graph + questionnaire edges
│   ├── models/                  kgat.py, hgib.py, baselines.py
│   ├── training/train.py        training loop, early stopping, curves
│   ├── evaluation/              metrics.py, harness.py
│   ├── serving/predict.py       Recommender (new users without retraining)
│   └── db/schema.py             interactions, impressions, questionnaire_answers
└── tests/                       pytest
```
