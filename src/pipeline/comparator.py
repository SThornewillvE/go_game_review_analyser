import json

from src.pipeline.llm import get_claude_response, parse_json_response

HAIKU_MODEL = "claude-haiku-4-5-20251001"


def compute_tag_trends(prev_tags: dict, curr_tags: dict) -> dict:
    """
    Compute tag trends between two analyses.

    Surfaces tags that appeared, disappeared, or changed by 2+ games.
    """
    all_tags = set(prev_tags) | set(curr_tags)
    appeared = []
    disappeared = []
    changed = []

    for tag in all_tags:
        prev = prev_tags.get(tag, 0)
        curr = curr_tags.get(tag, 0)
        diff = curr - prev

        if prev == 0 and curr > 0:
            appeared.append({"tag": tag, "count": curr})
        elif prev > 0 and curr == 0:
            disappeared.append({"tag": tag, "count": prev})
        elif abs(diff) >= 2:
            changed.append({"tag": tag, "prev": prev, "curr": curr, "diff": diff})

    changed.sort(key=lambda x: abs(x["diff"]), reverse=True)
    return {"appeared": appeared, "disappeared": disappeared, "changed": changed}


def compare_analyses(prev: dict, curr: dict, prompts: dict) -> dict:
    """
    Stage 3: Compare previous and current analyses to surface progress.

    Args:
        prev: Previous analysis dict (with notes_analysis, playing_style).
        curr: Current analysis dict (same structure).
        prompts: Prompt config dict; must contain 'go_review_progress_analyser'.

    Returns:
        Dict with improved, same, regressed lists.
    """
    system = prompts["go_review_progress_analyser"]

    user_content = (
        "Previous batch analysis:\n"
        f"{json.dumps({'notes_analysis': prev.get('notes_analysis'), 'playing_style': prev.get('playing_style')}, indent=2)}"
        "\n\nCurrent batch analysis:\n"
        f"{json.dumps({'notes_analysis': curr.get('notes_analysis'), 'playing_style': curr.get('playing_style')}, indent=2)}"
    )

    text = get_claude_response(HAIKU_MODEL, system, user_content, max_tokens=1024)
    return parse_json_response(text)
