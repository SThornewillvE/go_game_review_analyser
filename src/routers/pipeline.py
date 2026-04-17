import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from src.pipeline import analyser, comparator, db, parser, summariser
from src.routers.auth import get_current_user

router = APIRouter(tags=["pipeline"])

_prompts: dict | None = None


def _load_prompts() -> dict:
    global _prompts
    if _prompts is None:
        prompts_path = Path(__file__).parent.parent / "prompt_configs.json"
        with open(prompts_path) as f:
            _prompts = json.load(f)
    return _prompts


@router.post("/upload")
async def upload(
    files: list[UploadFile],
    user: dict = Depends(get_current_user),
):
    """Stage 1: Parse uploaded .md files and extract structured fields via Claude."""
    prompts = _load_prompts()

    file_data = [(f.filename, await f.read()) for f in files]
    all_reviews = parser.parse_game_reviews(file_data)

    existing = db.get_existing_game_links(user["id"])
    new_reviews = [r for r in all_reviews if r.get("game_link") not in existing]

    if not new_reviews:
        return {"message": "No new games to process", "new_games": 0}

    summaries = summariser.summarise_game_reviews(new_reviews, prompts)

    merged = []
    for review, summary in zip(new_reviews, summaries):
        merged.append({**review, **summary})

    db.save_reviews(merged, user["id"])
    return {"message": f"Processed {len(merged)} new games", "new_games": len(merged)}


@router.post("/analyse")
def analyse(user: dict = Depends(get_current_user)):
    """Stage 2 + Stage 3: Analyse the current batch, then compare with the previous one."""
    prompts = _load_prompts()

    reviews = db.get_unanalysed_reviews(user["id"])
    if len(reviews) < 20:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least 20 new games to analyse; only {len(reviews)} available.",
        )

    notes_analysis = analyser.analyse_review_notes(reviews, prompts)
    playing_style = analyser.analyse_playing_style(reviews, prompts)
    tag_counts = analyser.analyse_tags(reviews)

    win_count = sum(1 for r in reviews if r.get("is_won_game"))
    game_count = len(reviews)

    dates = [r["date"] for r in reviews if r.get("date")]
    period_start = min(dates) if dates else None
    period_end = max(dates) if dates else None

    analysis_id = db.save_analysis(
        user_id=user["id"],
        period_start=period_start,
        period_end=period_end,
        win_count=win_count,
        game_count=game_count,
        notes_analysis=notes_analysis,
        tag_counts=tag_counts,
        playing_style=playing_style,
    )

    # Stage 3
    prev = db.get_previous_analysis(user["id"], analysis_id)
    if prev:
        curr = {"notes_analysis": notes_analysis, "playing_style": playing_style}
        progress = comparator.compare_analyses(prev, curr, prompts)
        tag_trends = comparator.compute_tag_trends(
            prev.get("tag_counts") or {}, tag_counts
        )
        db.update_comparison(analysis_id, {"progress": progress, "tag_trends": tag_trends})

    return {"message": "Analysis complete", "analysis_id": analysis_id}
