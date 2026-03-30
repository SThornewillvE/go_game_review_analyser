import os
import sqlite3
import json

import pandas as pd
from openai import OpenAI
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from helpers import (
    initialise_db,
    parse_game_reviews,
    summarise_game_reviews,
    analyse_tags,
    analyse_game_review_summary,
)

PROMPTS_PATH = os.path.join(os.path.dirname(__file__), "prompt_configs.json")

app = FastAPI(title="Go Game Review Analyser")

def _load_prompts() -> dict:
    with open(PROMPTS_PATH) as f:
        return json.load(f)


def _get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY environment variable not set")
    return OpenAI(api_key=api_key)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class SummariseRequest(BaseModel):
    game_notes_path: str
    db_path: str = "game_reviews.db"


class SummariseResponse(BaseModel):
    new_games_processed: int
    message: str


class AnalyseResponse(BaseModel):
    did_well: str
    needs_work: str
    top_tags: list[dict]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/games/summarise", response_model=SummariseResponse)
def summarise_games(request: SummariseRequest):
    """
    Parse game review markdown files, summarise any new games with GPT,
    and persist the results to the database.
    """
    if not os.path.isdir(request.game_notes_path):
        raise HTTPException(
            status_code=400,
            detail=f"game_notes_path '{request.game_notes_path}' is not a valid directory",
        )

    client = _get_client()
    prompts = _load_prompts()

    initialise_db(request.db_path)

    game_path_glob = os.path.join(request.game_notes_path, "*")
    review_data, review_df = parse_game_reviews(game_path_glob)

    game_summaries = summarise_game_reviews(review_data, client, prompts, request.db_path)

    if not game_summaries:
        return SummariseResponse(new_games_processed=0, message="No new games to process.")

    # Merge GPT summaries back into the DataFrame rows for new games only
    new_rows = []
    for game_id, summary in game_summaries.items():
        row = review_data[game_id]["metadata"].copy()
        row["review_notes"] = review_data[game_id]["review_notes"]
        row.update(summary)
        new_rows.append(row)

    new_df = pd.DataFrame(new_rows)

    with sqlite3.connect(request.db_path) as conn:
        new_df.to_sql("reviews", conn, if_exists="append", index=False)

    return SummariseResponse(
        new_games_processed=len(game_summaries),
        message=f"Processed and stored {len(game_summaries)} new game(s).",
    )


@app.get("/games/analyse", response_model=AnalyseResponse)
def analyse_games(db_path: str = "game_reviews.db"):
    """
    Read all stored game summaries from the database, generate an overall
    analysis with GPT, and return tag frequency data.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            review_df = pd.read_sql("SELECT * FROM reviews", conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read database: {e}")

    if review_df.empty:
        raise HTTPException(status_code=404, detail="No games found in the database.")

    client = _get_client()
    prompts = _load_prompts()

    overall_summary = analyse_game_review_summary(review_df, client, prompts)

    tag_df = analyse_tags(review_df, db_path)

    return AnalyseResponse(
        did_well=overall_summary.get("did_well", ""),
        needs_work=overall_summary.get("needs_work", ""),
        top_tags=tag_df.head(10).to_dict(orient="records"),
    )
