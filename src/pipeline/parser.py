def _parse_metadata(header: str) -> dict:
    metadata = {}
    for line in header.strip().split("\n"):
        if "`" not in line:
            continue
        parts = line.split("`")
        if len(parts) < 2:
            continue
        # "Opponent's Name: " → strip → lower → replace spaces → remove apostrophes → drop trailing ":"
        raw_key = parts[0].strip().lower().replace(" ", "_").replace("'", "")
        key = raw_key.rstrip(":")
        metadata[key] = parts[1]
    return metadata


def _is_won_game(result: str, played_as: str) -> int:
    result = result.strip().upper()
    played_as = played_as.strip().upper()
    if played_as == "BLACK" and result.startswith("B+"):
        return 1
    if played_as == "WHITE" and result.startswith("W+"):
        return 1
    return 0


def parse_game_reviews(files: list[tuple[str, bytes]]) -> list[dict]:
    """
    Parse markdown game review files into a list of game dicts.

    Args:
        files: List of (filename, raw_bytes) tuples.

    Returns:
        List of dicts with metadata fields and 'review_notes'.
    """
    reviews = []
    for filename, content in files:
        text = content.decode("utf-8")
        parts = text.split("\n___")
        if len(parts) < 2:
            continue

        header, notes = parts[0], "\n___".join(parts[1:])
        metadata = _parse_metadata(header)

        result = metadata.get("result", "")
        played_as = metadata.get("played_as", "")

        reviews.append(
            {
                "date": metadata.get("date"),
                "opponents_name": metadata.get("opponents_name"),
                "server": metadata.get("server"),
                "game_link": metadata.get("game_link"),
                "result": result,
                "played_as": played_as,
                "is_won_game": _is_won_game(result, played_as),
                "handicap": metadata.get("handicap", "0"),
                "time_setting": metadata.get("time_setting"),
                "review_notes": notes.strip(),
            }
        )

    return reviews
