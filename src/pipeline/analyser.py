from collections import Counter

from src.pipeline.llm import get_claude_response, parse_json_response

SONNET_MODEL = "claude-sonnet-4-6"
HAIKU_MODEL = "claude-haiku-4-5-20251001"


def analyse_review_notes(reviews: list[dict], prompts: dict) -> dict:
    """
    Stage 2a: Identify recurring patterns across all batch games.

    Returns dict with recurring_mistakes, recurring_strengths, overall_impression.
    """
    combined_notes = "\n\n---\n\n".join(
        r["review_notes"] for r in reviews if r.get("review_notes")
    )
    system = prompts["go_review_notes_analyser"]
    user_content = f"Here are the combined raw review notes from all games:\n\n{combined_notes}"

    text = get_claude_response(SONNET_MODEL, system, user_content, max_tokens=2048)
    return parse_json_response(text)


def analyse_playing_style(reviews: list[dict], prompts: dict) -> dict:
    """
    Stage 2b: Qualitative assessment across 7 skill dimensions.
    Excludes games with handicap > 1.
    """
    eligible = [
        r for r in reviews
        if _to_int(r.get("handicap", "0")) <= 1
    ]
    if not eligible:
        return {}

    combined_notes = "\n\n---\n\n".join(
        r["review_notes"] for r in eligible if r.get("review_notes")
    )
    total = len(eligible)
    wins = sum(1 for r in eligible if r.get("is_won_game"))
    win_rate_summary = (
        f"Win/loss record (non-handicap games): {wins} wins, {total - wins} losses "
        f"out of {total} games ({wins / total:.0%} win rate)."
    )

    system = prompts["go_playing_style_analyser"]
    user_content = (
        f"{win_rate_summary}\n\n"
        f"Combined raw review notes from non-handicap games:\n\n{combined_notes}"
    )

    text = get_claude_response(SONNET_MODEL, system, user_content, max_tokens=2048)
    return parse_json_response(text)


def analyse_tags(reviews: list[dict]) -> dict:
    """
    Stage 2c: Count game tags across all batch reviews (in-memory).

    Returns dict mapping tag → count.
    """
    counts: Counter = Counter()
    for r in reviews:
        tags_str = r.get("game_tags") or ""
        for tag in tags_str.split(";"):
            tag = tag.strip()
            if tag:
                counts[tag] += 1
    return dict(counts)


def _to_int(value: str | int | None) -> int:
    try:
        return int(value or 0)
    except (ValueError, TypeError):
        return 0
