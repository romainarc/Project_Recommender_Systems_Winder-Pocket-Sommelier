"""Pocket Sommelier API (owner: SE). Serves the TRAINED model (no mocks).

Which model: environment variables MODEL_DIR and DATA_DIR
(default: artifacts/slim and data/processed/slim).

Run:  uvicorn api.main:app --reload      Docs: http://localhost:8000/docs

Flow for a new user:
    POST /onboard          questionnaire answers -> profile built from the answers
    POST /recommend        top-k wines (+ dish), written to `impressions`
    POST /log_interaction  like / dislike / rating / add_to_cellar -> database + profile update
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import List, Literal, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from sommelier.db.schema import Impression, Interaction, QuestionnaireAnswer, make_session_factory  # noqa: E402
from sommelier.serving.predict import default_recommender  # noqa: E402

app = FastAPI(title="Pocket Sommelier API", version="0.3.0")
Session = make_session_factory()
REC = default_recommender()          # loads the trained model once, at start-up
OPTIONS = REC.options()


class Questionnaire(BaseModel):
    user_id: str
    color: Optional[str] = None
    body: Optional[str] = None
    acidity: Optional[str] = None
    grapes: List[str] = []
    countries: List[str] = []
    discovery: Optional[Literal["explorer", "safe"]] = None


class RecommendRequest(BaseModel):
    user_id: str
    dish: Optional[str] = None
    k: int = Field(10, ge=1, le=50)


class WineOut(BaseModel):
    wine_id: int
    name: str
    type: str
    body: Optional[str] = None
    acidity: Optional[str] = None
    grapes: List[str]
    country: str
    region: Optional[str] = None
    winery: Optional[str] = None
    abv: Optional[float] = None
    country_code: Optional[str] = None
    popularity_rank: int
    explanation: str
    similar_to_liked: bool = False
    basis: str = "popular"                   # popular / personal / taste / similar
    matched: dict = {}                       # questionnaire answers the wine matches
    pairs_with: Optional[str] = None         # X-Wines dish label behind the dish family
    similar_to: Optional[str] = None         # liked wine it is close to


class RecommendResponse(BaseModel):
    user_id: str
    dish: Optional[str]
    model_version: str
    latency_ms: float
    wines: List[WineOut]


class InteractionIn(BaseModel):
    user_id: str
    wine_id: int
    event_type: Literal["view", "like", "dislike", "rating", "add_to_cellar"]
    value: Optional[float] = Field(None, ge=1, le=5)
    dish: Optional[str] = None
    session_id: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok", "model_version": REC.model_version,
            "users": REC.n_real, "wines": REC.ds.ckg.n_wines, "guests": len(REC.guests)}


@app.get("/options")
def options():
    """Possible questionnaire answers and dishes, for the frontend."""
    return OPTIONS


@app.get("/dishes")
def dishes():
    return {"dishes": OPTIONS["dishes"]}


@app.post("/onboard")
def onboard(q: Questionnaire):
    answers = q.model_dump(exclude={"user_id"})
    start = time.time()
    REC.onboard(q.user_id, answers)
    with Session() as s:
        s.add(QuestionnaireAnswer(user_id=q.user_id, answers=answers))
        s.commit()
    return {"status": "profile created", "user_id": q.user_id,
            "latency_ms": round(1000 * (time.time() - start), 1)}


@app.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest):
    known = set(OPTIONS["dishes"]) | {f["name"] for f in OPTIONS["dish_families"]}
    if req.dish and req.dish not in known:
        raise HTTPException(404, f"unknown dish '{req.dish}', see /options")
    start = time.time()
    wines = REC.recommend(req.user_id, req.dish, req.k)
    latency = round(1000 * (time.time() - start), 1)
    with Session() as s:
        s.add(Impression(user_id=req.user_id, dish=req.dish,
                         wine_ids=[w["wine_id"] for w in wines], model_version=REC.model_version))
        s.commit()
    return RecommendResponse(user_id=req.user_id, dish=req.dish, model_version=REC.model_version,
                             latency_ms=latency, wines=[WineOut(**w) for w in wines])


@app.post("/log_interaction")
def log_interaction(evt: InteractionIn):
    if evt.event_type == "rating" and evt.value is None:
        raise HTTPException(422, "a rating event needs a value between 1 and 5")
    with Session() as s:
        row = Interaction(**evt.model_dump())
        s.add(row)
        s.commit()
        row_id = row.id
    REC.feedback(evt.user_id, evt.wine_id, evt.event_type, evt.value)   # profile update
    return {"status": "logged", "id": row_id}


# ------------------------------------------------------------------ web app
# The consumer app (web/, React) is built into web/dist and served here, so one command
# (uvicorn api.main:app) starts everything: open http://localhost:8000
WEB_DIST = ROOT / "web" / "dist"
if WEB_DIST.exists():
    from fastapi.staticfiles import StaticFiles  # noqa: E402
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
