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
git clone https://github.com/romainarc/Project_Recommender_Systems_Winder-Pocket-Sommelier.git pocket-sommelier
cd pocket-sommelier
python3 -m venv .venv                  # Windows: python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1. data: clean, temporal split, simulated questionnaires
python scripts/prepare_data.py --preset test

# 2. a small model (about 1 minute)
python scripts/train.py --data data/processed/test --out artifacts/test --batch-size 128 --epochs 10

# 3. API (terminal 1)  ->  http://localhost:8000/docs
MODEL_DIR=artifacts/test DATA_DIR=data/processed/test uvicorn api.main:app
#   Windows PowerShell: $env:MODEL_DIR="artifacts/test"; $env:DATA_DIR="data/processed/test"; uvicorn api.main:app

# 4. app (terminal 2, same folder, activate .venv again)  ->  http://localhost:8501
streamlit run app/streamlit_app.py
#   port already in use? add: --server.port 8502
```

In the app: fill the questionnaire, click **Save my taste**, pick a dish, then like a wine and
watch the list change. Everything is logged in `artifacts/sommelier.db`.

Checks: `python -m pytest -q`

## Final app (V2): one command

The final model (`artifacts/full_k10/`, HGIB-KGAT trained on X-Wines Full) and its data split
(`data/processed/full_k10/`, ~23 MB) are committed, and so is the built web app (`web/dist/`).
No download, no training and no Node.js are needed:

```bash
uvicorn api.main:app        # then open http://localhost:8000
```

The app is in French by default (English with the FR / EN button). A visitor answers six questions,
one per screen, picks a dish among 11 families, and gets ten wines with the reason for each one;
"J'aime", "Pas pour moi" and "En cave" update the list at once. "Nouveau visiteur" starts over
(useful at the showcase). The old Streamlit app still works: `streamlit run app/streamlit_app.py`.
To change the web app: `cd web && npm install && npm run dev` (http://localhost:5173, it calls the
API on port 8000), then `npm run build` to update `web/dist/`.

| | V1 (Week 3 report) | **V2 (final model)** |
|---|---|---|
| Input | X-Wines Full (21M ratings, 100K wines) | X-Wines Full (21M ratings, 100K wines) |
| Filter | year 2021, 20-core | year 2021, **10-core** |
| Ratings used | 443,073 | **1,688,859** |
| Users / wines | 12,406 / 8,968 | **79,652 / 37,112** |
| Target interactions (liked, train) | 246,578 | **928,763** |
| Model | dim 32 / 64 | dim 16 (12 GB RAM of Colab), 14 epochs, best epoch 12 |
| Folders | `artifacts/full*`, `data/processed/full` | `artifacts/full_k10`, `data/processed/full_k10` |

V2 test results (`artifacts/results_full_k10/results.md`, 45,394 test users, full ranking):

| Method | NDCG@10 | Recall@20 | Body match |
|---|---|---|---|
| Most-popular | 0.0088 | 0.0224 | 0.30 |
| Dish → wines (query) | 0.0146 | 0.0381 | 0.32 |
| HGIB-KGAT | 0.0161 | 0.0439 | 0.39 |
| HGIB-KGAT + dish filter | **0.0254** | **0.0669** | 0.40 |
| HGIB-KGAT + questionnaire bonus + dish filter (served) | 0.0225 | 0.0598 | **0.77** |

Training curves: `artifacts/full_k10/curves.png`; feedback curve:
`artifacts/results_full_k10/feedback_curve.png`; qualitative check:
`artifacts/full_k10/sample_users.md`; Colab logs: `reports/v2_logs/`.

## Full pipeline (how the models were produced)

1. Download from the [X-Wines Google Drive](https://drive.google.com/drive/folders/1LqguJNV-aKh1PuWMVx5ELA61LPfGfuu_?usp=sharing)
   into `data/raw/`: `XWines_Full_100K_wines.csv` and `XWines_Full_21M_ratings.csv`
   (and `XWines_Slim_1K_wines.csv`, `XWines_Slim_150K_ratings.csv` for the Slim version).
2. Prepare the data (reads the 21M ratings in chunks, ~3 min):
   ```bash
   python scripts/prepare_data.py --preset full_k10    # V2, final: 2021, 10-core
   python scripts/prepare_data.py --preset full        # V1: 2021, 20-core
   python scripts/prepare_data.py --preset slim
   ```
3. Train. V2 was trained on Google Colab (CPU, 12 GB RAM, ~10 min per epoch); it does not fit
   in 8 GB of RAM:
   ```bash
   # V2 (final)
   python scripts/train.py --data data/processed/full_k10 --out artifacts/full_k10 --dim 16 --batch-size 32768 --lr 0.02 --patience 3 --epochs 14 --max-eval-users 2000
   # V1
   python scripts/train.py --data data/processed/full --out artifacts/full --dim 32 --batch-size 8192 --lr 0.01 --patience 5
   ```
   Ablations: add `--no-questionnaire`, `--no-hgib` or `--no-gre` (and another `--out`).
4. Questionnaire bonus weight, chosen on the **validation** split (served score = standardised
   model score + weight × number of answers the wine matches):
   ```bash
   python scripts/tune_bonus.py --model artifacts/full --data data/processed/full
   ```
   The chosen weight (0.5, tuned on V1 and reused for V2) is `DEFAULT_QUESTIONNAIRE_WEIGHT` in
   `src/sommelier/serving/predict.py` (override with `QUESTIONNAIRE_WEIGHT=...`).
5. Evaluate on the **test** split (table + feedback curve), then the qualitative check:
   ```bash
   python scripts/evaluate.py --data data/processed/full_k10 --models artifacts/full_k10 --out artifacts/results_full_k10 --max-curve-users 500
   python scripts/sample_users.py --model artifacts/full_k10 --data data/processed/full_k10
   ```

## Where each step lives in the code

| Step | Script | Code |
|---|---|---|
| Data pipeline (dedup, 2021 filter, k-core, temporal split) | `scripts/prepare_data.py` | `src/sommelier/data/preprocess.py` |
| Simulated questionnaires (train only) | (called by the pipeline) | `src/sommelier/data/questionnaire.py` |
| Knowledge graph (wines, attributes, questionnaire edges) | (called by training) | `src/sommelier/graph/build_ckg.py` |
| Model: HGIB cascade rated → liked, HSIC, GRE | | `src/sommelier/models/hgib.py` |
| Model: KGAT encoder, TransR | | `src/sommelier/models/kgat.py` |
| Training, early stopping, curves | `scripts/train.py` | `src/sommelier/training/train.py` |
| Baselines, questionnaire bonus | | `src/sommelier/models/baselines.py` |
| Test evaluation, feedback curve | `scripts/evaluate.py` | `src/sommelier/evaluation/` |
| Serving (new users, feedback, explanations) | `api/main.py` | `src/sommelier/serving/predict.py` |
| App | `app/streamlit_app.py` | theme in `.streamlit/config.toml` |

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
