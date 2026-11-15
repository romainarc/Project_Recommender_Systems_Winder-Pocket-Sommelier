"""Pocket Sommelier API (owner: SE).

Week 2: /recommend returns MOCK recommendations (popular wines listed for the dish, taken from
the sample catalogue). Week 3 replaces ``mock_recommend`` with ``serving.predict`` (trained model).

Run:  uvicorn api.main:app --reload      Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from sommelier.data.preprocess import parse_list  # noqa: E402
from sommelier.db.schema import Impression, Interaction, make_session_factory  # noqa: E402

MODEL_VERSION = "mock-v0"
WINES = pd.read_csv(ROOT / "data/sample/XWines_Test_100_wines.csv")
WINES["Harmonize"] = WINES["Harmonize"].map(parse_list)
WINES["Grapes"] = WINES["Grapes"].map(parse_list)
_ratings = pd.read_csv(ROOT / "data/sample/XWines_Test_1K_ratings.csv")
POPULARITY = _ratings[_ratings["Rating"] >= 4].groupby("WineID").size()
DISHES = sorted(WINES["Harmonize"].explode().dropna().unique())

app = FastAPI(title="Pocket Sommelier API", version="0.2.0")
Session = make_session_factory()


class RecommendRequest(BaseModel):
    user_id: str
    dish: Optional[str] = None
    k: int = Field(10, ge=1, le=50)


class WineOut(BaseModel):
    wine_id: int
    name: str
    type: str
    grapes: list[str]
    country: str
    score: float
    explanation: str


class RecommendResponse(BaseModel):
    user_id: str
    dish: Optional[str]
    model_version: str
    wines: list[WineOut]


class InteractionIn(BaseModel):
    user_id: str
    wine_id: int
    event_type: Literal["view", "like", "dislike", "rating", "add_to_cellar"]
    value: Optional[float] = Field(None, ge=1, le=5)
    dish: Optional[str] = None
    session_id: Optional[str] = None


def mock_recommend(dish: Optional[str], k: int) -> list[WineOut]:
    cand = WINES
    if dish:
        cand = WINES[WINES["Harmonize"].map(lambda h: dish in h)]
    cand = cand.assign(pop=cand["WineID"].map(POPULARITY).fillna(0)).sort_values("pop", ascending=False)
    out = []
    for row in cand.head(k).itertuples():
        why = f"pairs with {dish}" if dish else "popular with other users"
        out.append(WineOut(wine_id=int(row.WineID), name=row.WineName, type=row.Type,
                           grapes=row.Grapes, country=row.Country, score=float(row.pop),
                           explanation=f"[mock] {why}"))
    return out


@app.get("/health")
def health():
    return {"status": "ok", "model_version": MODEL_VERSION, "wines": len(WINES)}


@app.get("/dishes")
def dishes():
    return {"dishes": DISHES}


@app.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    if req.dish and req.dish not in DISHES:
        raise HTTPException(404, f"unknown dish '{req.dish}', see /dishes")
    wines = mock_recommend(req.dish, req.k)
    with Session() as s:
        s.add(Impression(user_id=req.user_id, dish=req.dish,
                         wine_ids=[w.wine_id for w in wines], model_version=MODEL_VERSION))
        s.commit()
    return RecommendResponse(user_id=req.user_id, dish=req.dish, model_version=MODEL_VERSION, wines=wines)


@app.post("/log_interaction")
def log_interaction(evt: InteractionIn):
    if evt.event_type == "rating" and evt.value is None:
        raise HTTPException(422, "a rating event needs a value between 1 and 5")
    with Session() as s:
        row = Interaction(**evt.model_dump())
        s.add(row)
        s.commit()
        return {"status": "logged", "id": row.id}
