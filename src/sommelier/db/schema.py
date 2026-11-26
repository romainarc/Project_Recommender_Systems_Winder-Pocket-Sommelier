"""SQLite schema through SQLAlchemy (owner: DE). Switch to PostgreSQL by changing DATABASE_URL."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///artifacts/sommelier.db")

Base = declarative_base()


def _now():
    return datetime.now(timezone.utc)


class Interaction(Base):
    __tablename__ = "interactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False)
    wine_id = Column(Integer, index=True, nullable=False)
    event_type = Column(String, nullable=False)     # view | like | dislike | rating | add_to_cellar
    value = Column(Float, nullable=True)            # rating value (1-5) when event_type == rating
    dish = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    ts = Column(DateTime(timezone=True), default=_now)


class QuestionnaireAnswer(Base):
    __tablename__ = "questionnaire_answers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False)
    answers = Column(JSON, nullable=False)          # color, body, acidity, grapes, countries, discovery
    ts = Column(DateTime(timezone=True), default=_now)


class Impression(Base):
    __tablename__ = "impressions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False)
    dish = Column(String, nullable=True)
    wine_ids = Column(JSON, nullable=False)
    model_version = Column(String, nullable=False)
    ts = Column(DateTime(timezone=True), default=_now)


def make_session_factory(url: str = DATABASE_URL):
    if url.startswith("sqlite:///"):
        os.makedirs(os.path.dirname(url.removeprefix("sqlite:///")) or ".", exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
