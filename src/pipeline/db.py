import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path("game_reviews.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialise_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT,
                opponents_name TEXT,
                server TEXT,
                game_link TEXT NOT NULL,
                result TEXT,
                played_as TEXT,
                is_won_game INTEGER,
                handicap TEXT,
                time_setting TEXT,
                review_notes TEXT,
                key_mistake TEXT,
                key_mistake_cause TEXT,
                positive_point TEXT,
                game_tags TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS game_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                period_start TEXT,
                period_end TEXT,
                win_count INTEGER,
                game_count INTEGER,
                notes_analysis TEXT,
                tag_counts TEXT,
                playing_style TEXT,
                comparison TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)


def get_user_by_username(username: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    return dict(row) if row else None


def create_user(username: str, hashed_password: str) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
            (username, hashed_password),
        )
        return cursor.lastrowid


def get_existing_game_links(user_id: int) -> set[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT game_link FROM reviews WHERE user_id = ?", (user_id,)
        ).fetchall()
    return {row["game_link"] for row in rows}


def save_reviews(reviews: list[dict], user_id: int) -> None:
    with get_conn() as conn:
        for r in reviews:
            conn.execute(
                """
                INSERT INTO reviews (
                    user_id, date, opponents_name, server, game_link, result,
                    played_as, is_won_game, handicap, time_setting, review_notes,
                    key_mistake, key_mistake_cause, positive_point, game_tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    r.get("date"),
                    r.get("opponents_name"),
                    r.get("server"),
                    r.get("game_link"),
                    r.get("result"),
                    r.get("played_as"),
                    r.get("is_won_game"),
                    r.get("handicap"),
                    r.get("time_setting"),
                    r.get("review_notes"),
                    r.get("key_mistake"),
                    r.get("key_mistake_cause"),
                    r.get("positive_point"),
                    r.get("game_tags"),
                ),
            )


def get_unanalysed_reviews(user_id: int) -> list[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(created_at) as last FROM game_analyses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        last_analysis = row["last"] if row else None

        if last_analysis:
            rows = conn.execute(
                "SELECT * FROM reviews WHERE user_id = ? AND created_at > ? ORDER BY date",
                (user_id, last_analysis),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reviews WHERE user_id = ? ORDER BY date", (user_id,)
            ).fetchall()

    return [dict(r) for r in rows]


def save_analysis(
    user_id: int,
    period_start: str,
    period_end: str,
    win_count: int,
    game_count: int,
    notes_analysis: dict,
    tag_counts: dict,
    playing_style: dict,
) -> int:
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO game_analyses (
                user_id, period_start, period_end, win_count, game_count,
                notes_analysis, tag_counts, playing_style
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                period_start,
                period_end,
                win_count,
                game_count,
                json.dumps(notes_analysis),
                json.dumps(tag_counts),
                json.dumps(playing_style),
            ),
        )
        return cursor.lastrowid


def get_previous_analysis(user_id: int, current_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM game_analyses
            WHERE user_id = ? AND id < ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (user_id, current_id),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    for field in ("notes_analysis", "tag_counts", "playing_style", "comparison"):
        if result.get(field):
            result[field] = json.loads(result[field])
    return result


def update_comparison(analysis_id: int, comparison: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE game_analyses SET comparison = ? WHERE id = ?",
            (json.dumps(comparison), analysis_id),
        )


def get_all_analyses(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM game_analyses WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        for field in ("notes_analysis", "tag_counts", "playing_style", "comparison"):
            if item.get(field):
                item[field] = json.loads(item[field])
        results.append(item)
    return results


def get_latest_analysis(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM game_analyses WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    for field in ("notes_analysis", "tag_counts", "playing_style", "comparison"):
        if result.get(field):
            result[field] = json.loads(result[field])
    return result


def get_tag_stats(user_id: int) -> dict:
    """Return tag counts broken down by all games, wins, and losses."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT game_tags, is_won_game FROM reviews WHERE user_id = ? AND game_tags IS NOT NULL",
            (user_id,),
        ).fetchall()

    all_counts: dict[str, int] = {}
    win_counts: dict[str, int] = {}
    loss_counts: dict[str, int] = {}

    for row in rows:
        tags = [t.strip() for t in (row["game_tags"] or "").split(";") if t.strip()]
        for tag in tags:
            all_counts[tag] = all_counts.get(tag, 0) + 1
            if row["is_won_game"]:
                win_counts[tag] = win_counts.get(tag, 0) + 1
            else:
                loss_counts[tag] = loss_counts.get(tag, 0) + 1

    return {"all": all_counts, "wins": win_counts, "losses": loss_counts}


def delete_analysis(analysis_id: int, user_id: int) -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM game_analyses WHERE id = ? AND user_id = ?",
            (analysis_id, user_id),
        )
        return cursor.rowcount > 0


def get_review_count(user_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as count FROM reviews WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row["count"]
