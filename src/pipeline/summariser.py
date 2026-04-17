from src.pipeline.llm import get_claude_response, parse_json_response

HAIKU_MODEL = "claude-haiku-4-5-20251001"


def summarise_game_reviews(
    games: list[dict],
    prompts: dict,
) -> list[dict]:
    """
    Call Claude to extract structured fields from each game's review notes.

    Args:
        games: List of game dicts (from parser), each with 'review_notes' and metadata.
        prompts: Prompt config dict; must contain 'go_review_system_prompt'.

    Returns:
        List of dicts with key_mistake, key_mistake_cause, positive_point, game_tags.
        Same order as input; failed extractions yield an empty dict.
    """
    system = prompts["go_review_system_prompt"]
    summaries = []

    for game in games:
        user_content = (
            f"Analyse these game notes as outlined in the system message:\n\n"
            f"Game Notes:\n{game.get('review_notes', '')}"
        )
        try:
            text = get_claude_response(HAIKU_MODEL, system, user_content, max_tokens=512)
            summary = parse_json_response(text)
            summaries.append(summary if isinstance(summary, dict) else {})
        except Exception:
            summaries.append({})

    return summaries
