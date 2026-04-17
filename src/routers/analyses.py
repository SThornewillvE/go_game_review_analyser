from fastapi import APIRouter, Depends, HTTPException, status

from src.pipeline import db
from src.routers.auth import get_current_user

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.get("")
def list_analyses(user: dict = Depends(get_current_user)):
    """Return all past analyses (summary fields only)."""
    analyses = db.get_all_analyses(user["id"])
    return [
        {
            "id": a["id"],
            "period_start": a["period_start"],
            "period_end": a["period_end"],
            "win_count": a["win_count"],
            "game_count": a["game_count"],
            "created_at": a["created_at"],
        }
        for a in analyses
    ]


@router.get("/latest")
def latest_analysis(user: dict = Depends(get_current_user)):
    """Return the most recent analysis with all fields, including comparison."""
    analysis = db.get_latest_analysis(user["id"])
    if analysis is None:
        raise HTTPException(status_code=404, detail="No analyses found")
    return analysis


@router.get("/tag-stats")
def tag_stats(user: dict = Depends(get_current_user)):
    """Return tag counts broken down by all games, wins, and losses."""
    return db.get_tag_stats(user["id"])


@router.get("/{analysis_id}")
def get_analysis(analysis_id: int, user: dict = Depends(get_current_user)):
    """Return a single analysis by ID."""
    analyses = db.get_all_analyses(user["id"])
    for a in analyses:
        if a["id"] == analysis_id:
            return a
    raise HTTPException(status_code=404, detail="Analysis not found")


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_analysis(analysis_id: int, user: dict = Depends(get_current_user)):
    """Delete an analysis by ID (must belong to the authenticated user)."""
    deleted = db.delete_analysis(analysis_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis not found")
