import json
import glob
import sqlite3
import pandas as pd

from openai import OpenAI
from tqdm import tqdm, trange

def initialise_db(db_path: str = "game_reviews.db") -> None:
    """
    Create the database and required tables if they don't already exist.

    Args:
        db_path: Path to the SQLite database file.
    """
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                date TEXT,
                opponents_name TEXT,
                server TEXT,
                game_link TEXT,
                result TEXT,
                played_as TEXT,
                is_won_game INTEGER,
                handicap TEXT,
                time_setting TEXT,
                review_notes TEXT,
                key_mistake TEXT,
                key_mistake_cause TEXT,
                positive_point TEXT,
                game_tags TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tag_counts (
                tag TEXT,
                count INTEGER
            )
        """)


def get_existing_game_links(db_path: str = "game_reviews.db") -> set[str]:
    """
    Return the set of game_link values already stored in the reviews table.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A set of game_link strings, or an empty set if the table doesn't exist.
    """
    try:
        conn = sqlite3.connect(db_path)
        existing = pd.read_sql("SELECT game_link FROM reviews", conn)["game_link"].tolist()
        conn.close()
        return set(existing)
    except Exception:
        return set()


def get_gpt_response(client: OpenAI, messages: list[dict]) -> dict:
    """
    Send messages to the GPT API and parse the JSON response.

    Args:
        client: An initialised OpenAI client.
        messages: A list of message dicts with 'role' and 'content' keys.

    Returns:
        Parsed JSON response from the model as a dict.
    """
    response = client.responses.create(
        model="gpt-5-nano",
        input=messages
    )

    output = json.loads(response.output_text.replace("\n", ""))

    return output


def parse_game_reviews(game_path: str = "./game_review_notes/*") -> tuple[dict, pd.DataFrame]:
    """
    Parse game review markdown files into a dict and a DataFrame.

    Args:
        game_path: Glob pattern pointing to the review markdown files.

    Returns:
        A tuple of:
        - review_data: dict mapping integer game IDs to dicts containing
          'metadata' (dict) and 'review_notes' (str).
        - review_df: DataFrame with one row per game, metadata columns, and a
          'review_notes' column.
    """

    # Get game reviews
    review_data = dict()
    game_id = 0
    review_files = glob.glob(game_path)

    for file_path in tqdm([f for f in review_files if not f.endswith("game_review_template.md")]):

        # Load review
        with open(file_path, "r") as f:
            review_text = f.read()

        # Break apart review
        text_metadata = review_text.split("\n___")[0]
        review_notes = review_text.split("\n___")[1]

        # Parse metadata
        keys = [i.split("`")[0].strip().lower().replace(" ", "_").replace("'", "")[:-1] for i in text_metadata.split("\n")]
        values = [i.split("`")[1:2][0] for i in text_metadata.split("\n")]
        metadata = {i: j for i, j in zip(keys, values)}

        # Package everything together
        review_data[game_id] = {
            'metadata': metadata,
            'review_notes': review_notes
        }

        game_id+=1

    # Create dataframe for return
    review_df = pd.DataFrame([review_data[i]["metadata"] for i in review_data])\
        .assign(review_notes=[review_data[i]["review_notes"] for i in review_data])

    return review_data, review_df


def summarise_game_reviews(game_review_data: dict, client: OpenAI, prompts: dict, db_path: str = "game_reviews.db") -> dict:
    """
    Generate GPT summaries for each game review.

    Args:
        game_review_data: Dict mapping integer game IDs to review data, as
            returned by parse_game_reviews.
        client: An initialised OpenAI client.
        prompts: Dict of prompt strings; must contain the key
            'go_review_system_prompt'.
        db_path: Path to the SQLite database file, used to skip games already
            stored in the reviews table.

    Returns:
        Dict mapping integer game IDs to the parsed JSON summary returned by
        the model. Only contains entries for games not already in the database.
    """
    existing_game_links = get_existing_game_links(db_path)

    game_summaries = dict()

    for i in trange(len(game_review_data)):
        if game_review_data[i].get('metadata', {}).get('game_link') in existing_game_links:
            continue

        messages = [
            {
                "role": "system",
                "content": prompts["go_review_system_prompt"]
            },
            {
                "role": "user",
                "content": f"""Analyse these game notes as outlined in the system message:\n
                \
                Game Notes: {game_review_data[i]}
                """
            }
        ]

        game_summary = get_gpt_response(client, messages)  # TODO: Verify output
        game_summaries[i] = game_summary

    return game_summaries

def analyse_tags(game_review_df: pd.DataFrame, db_path: str = "game_reviews.db") -> pd.DataFrame:
    """
    Count game tags across all reviews and persist them to the database.

    Args:
        game_review_df: DataFrame with a 'game_tags' column containing
            semicolon-separated tag strings.
        db_path: Path to the SQLite database file.

    Returns:
        DataFrame with columns ['tag', 'count'] sorted by frequency descending.
    """
    tag_counts = (
        game_review_df["game_tags"]
        .str.split(";")
        .explode()
        .str.strip()
        .value_counts()
        .to_dict()
    )

    df_tag_counts = pd.DataFrame(list(tag_counts.items()), columns=["tag", "count"])

    with sqlite3.connect(db_path) as conn:
        df_tag_counts.to_sql("tag_counts", conn, if_exists="replace", index=False)

    return df_tag_counts


def analyse_review_notes(game_review_df: pd.DataFrame, client: OpenAI, prompts: dict) -> dict:
    combined_notes = "\n\n---\n\n".join(game_review_df["review_notes"].dropna().tolist())

    messages = [
        {"role": "system",
         "content": prompts["go_review_notes_analyser"]},
        {"role": "user",
         "content": f"Here are the combined raw review notes from all games:\n\n{combined_notes}"}
    ]

    return get_gpt_response(client, messages)


def analyse_playing_style(
    game_review_df: pd.DataFrame,
    client: OpenAI,
    prompts: dict,
    n_runs: int = 4,
    context: dict | None = None,
) -> dict:
    eligible_df = game_review_df[pd.to_numeric(game_review_df["handicap"], errors="coerce").fillna(0) <= 1]
    combined_notes = "\n\n---\n\n".join(eligible_df["review_notes"].dropna().tolist())

    total = len(eligible_df)
    wins = int(eligible_df["is_won_game"].sum())
    win_rate_summary = f"Win/loss record: {wins} wins, {total - wins} losses out of {total} games ({wins / total:.0%} win rate)."

    context_section = ""
    if context:
        if "summary" in context:
            context_section += f"\n\nGame review summary:\n{json.dumps(context['summary'], indent=2)}"
        if "notes_analysis" in context:
            context_section += f"\n\nRecurring pattern analysis:\n{json.dumps(context['notes_analysis'], indent=2)}"

    user_content = (
        f"{win_rate_summary}"
        f"{context_section}"
        f"\n\nCombined raw review notes from all games:\n\n{combined_notes}"
    )

    messages = [
        {"role": "system", "content": prompts["go_playing_style_analyser"]},
        {"role": "user", "content": user_content},
    ]

    all_runs = [
        get_gpt_response(client, messages)
        for _ in trange(n_runs, desc="Analysing playing style")
    ]

    scores_by_dimension: dict[str, list[int]] = {}
    reasoning_by_dimension: dict[str, list[str]] = {}
    for run in all_runs:
        for dim, value in run.items():
            scores_by_dimension.setdefault(dim, []).append(value["score"])
            reasoning_by_dimension.setdefault(dim, []).append(value["reasoning"])

    scores_df = pd.DataFrame([
        {"dimension": dim, "score": round(sum(scores) / len(scores), 1)}
        for dim, scores in scores_by_dimension.items()
    ])

    # Use the reasoning from the median-score run to surface the most representative justification
    dimensions_detail = {}
    for dim, scores in scores_by_dimension.items():
        avg = sum(scores) / len(scores)
        closest_idx = min(range(len(scores)), key=lambda i: abs(scores[i] - avg))
        dimensions_detail[dim] = {
            "score": round(avg, 1),
            "reasoning": reasoning_by_dimension[dim][closest_idx],
        }

    return {"scores": scores_df, "dimensions": dimensions_detail}


def save_analysis(
    game_review_df: pd.DataFrame,
    summary: dict,
    notes_analysis: dict,
    db_path: str = "game_reviews.db",
) -> None:
    """
    Persist a period's analysis results to the game_analyses table.

    Args:
        game_review_df: DataFrame with a 'date' column used to derive the
            period start and end dates.
        summary: Output of analyse_game_review_summary.
        notes_analysis: Output of analyse_review_notes.
        db_path: Path to the SQLite database file.
    """
    period_start = pd.to_datetime(game_review_df["date"]).min().date().isoformat()
    period_end = pd.to_datetime(game_review_df["date"]).max().date().isoformat()

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS game_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_start TEXT,
                period_end TEXT,
                summary TEXT,
                notes_analysis TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "INSERT INTO game_analyses (period_start, period_end, summary, notes_analysis) VALUES (?, ?, ?, ?)",
            (period_start, period_end, json.dumps(summary), json.dumps(notes_analysis)),
        )

    print(f"Saved analysis for period {period_start} → {period_end}")


def analyse_game_review_summary(game_review_data: dict, client: OpenAI, prompts: dict) -> dict:
        
    messages = [
        {"role": "system", 
        "content": prompts["go_review_summary_analyser"]},
        {"role": "user", 
        "content": f"""Here is the JSON of game review summaries: \n
            {game_review_data.drop(columns=["review_notes", "game_link"]).to_json(orient="records", indent=2)}"""
        }
    ]

    analysis = get_gpt_response(client, messages)

    return analysis
