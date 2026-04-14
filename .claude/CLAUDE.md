# Go Game Review Analyser

A web application that parses hand-written Go game review notes and uses Claude to extract structured insights, track progress across batches of games, and surface coaching-style findings through a Streamlit frontend. Built as a personal tool first, with the intention of growing into a multi-user SaaS product.

## Project Structure

```
src/                              # Production pipeline
  main.py                         # FastAPI entry point (served by Uvicorn)
  routers/
    auth.py                       # Register and token endpoints
    pipeline.py                   # Upload and trigger endpoints (Stages 1–3)
    analyses.py                   # Retrieve analysis results and comparisons
  pipeline/
    parser.py                     # Markdown parsing logic
    summariser.py                 # Stage 1: extract structured fields via Claude
    analyser.py                   # Stage 2: pattern analysis via Claude
    comparator.py                 # Stage 3: compare analyses via Claude
    db.py                         # SQLite read/write helpers
  frontend/
    app.py                        # Streamlit entry point (calls the FastAPI backend)
  prompt_configs.json             # LLM system prompts keyed by task name
```

## Pipeline Overview

### Stage 1 — Summarise
1. User uploads one or more markdown review files via the Streamlit UI
2. Parse each file into metadata and free-form notes (`parse_game_reviews`)
3. Skip games whose `game_link` already exists in the database (`get_existing_game_links`)
4. Send each new game's notes to Claude to extract structured fields (`summarise_game_reviews`)
5. Write results to the `reviews` table in `game_reviews.db`

### Stage 2 — Analyse
1. Read all reviews added since the most recent analysis (i.e. `reviews.created_at` > last `game_analyses.created_at`); refuse to run if fewer than 20 such games exist
2. Run two analysis functions against the Claude API:
   - `analyse_review_notes` — recurring patterns, habits, and overall impression (uses all batch games)
   - `analyse_playing_style` — qualitative assessment across 7 skill dimensions (excludes games with handicap > 1, as handicap games force a style that isn't representative)
3. Count game tags for the current batch (`analyse_tags`) — computed in-memory from `reviews`
4. Compute win rate for the batch (all games including handicap); store `win_count` and `game_count`
5. Persist the analysis to the `game_analyses` table (`save_analysis`)

### Stage 3 — Compare
Runs automatically at the end of `POST /analyse`, immediately after Stage 2 completes. Skipped if this is the first analysis in the database for this user.

1. Retrieve the most recent *previous* analysis (the one before the one just saved) from `game_analyses`
2. Compute tag trends programmatically by comparing `tag_counts` between the two analyses: surface only tags that appeared, disappeared, or changed by 2 or more games (to filter noise)
3. Send the previous and current `recurring_mistakes`/`recurring_strengths` and playing style assessments to Claude (`compare_analyses`)
4. Produce a structured comparison: `improved`, `same`, `regressed`
5. Persist the comparison result and tag trends by updating the `comparison` column of the current analysis row

## Backend (FastAPI)

The FastAPI app in `src/main.py` is the authoritative backend. All pipeline logic runs here; the frontend is a thin client that calls it.

Key endpoints:
- `POST /upload` — accept one or more `.md` files; triggers Stage 1 for any new games
- `POST /analyse` — trigger Stage 2 for the current batch, then Stage 3 automatically if a previous analysis exists
- `GET /analyses` — list all past analyses
- `GET /analyses/latest` — retrieve the most recent analysis and comparison

**Local development**: `uvicorn src.main:app --reload`

**Production**: deploy behind a production ASGI server (e.g. Uvicorn managed by Gunicorn, or a platform like Fly.io or Render that handles this automatically).

## Front-end (Streamlit)

The Streamlit app in `src/frontend/app.py` is a thin client that calls the FastAPI backend. It should support:

- **Upload**: Accept one or more `.md` game review files; trigger Stage 1 automatically on upload
- **Run analysis**: Button to trigger Stage 2 (and Stage 3 if a prior analysis exists) for the current batch
- **Win rate**: Line chart of win rate over time across all batches (x = analysis date, y = win rate)
- **Tag visualisations**: Bar charts of top tags overall, by win, and by loss
- **Recurring patterns**: List of recurring mistakes (with cause hypothesis and suggested focus) and recurring strengths; overall impression paragraph
- **Playing style**: Qualitative description of the player's tendencies across the 7 dimensions, derived from non-handicap games only
- **Progress over time** *(shown when at least two analyses exist)*: What has improved, stayed the same, or regressed since the previous batch; tag trends showing tags that appeared, disappeared, or meaningfully changed in frequency

## Authentication

The API uses OAuth2 password flow (username + password → JWT access token). FastAPI's built-in `OAuth2PasswordBearer` handles this. All endpoints except `POST /auth/register` and `POST /auth/token` require a valid token.

- `POST /auth/register` — create a new user (username + password)
- `POST /auth/token` — exchange credentials for a JWT access token

The authenticated user's `id` is injected as `user_id` into all DB reads and writes, ensuring data is fully isolated between users. Passwords are stored as bcrypt hashes — never plaintext.

## Database Schema (`game_reviews.db`)

**`users`** — one row per registered user:
`id, username, hashed_password`

**`reviews`** — one row per game:
`user_id, date, opponents_name, server, game_link, result, played_as, is_won_game, handicap, time_setting, review_notes, key_mistake, key_mistake_cause, positive_point, game_tags, created_at`

- `game_link` is always present (all games are reviewed on AI Sensei)
- `created_at` is used to determine which games belong to the current (unanalysed) batch
- `game_link` deduplication is scoped per `user_id`

**`game_analyses`** — one row per analysis run (i.e. per batch):
`id, user_id, period_start, period_end, win_count, game_count, notes_analysis, tag_counts, playing_style, comparison, created_at`

- `win_count`, `game_count`: used to compute win rate and render the O/X string; covers all games in the batch including handicap
- `tag_counts`: JSON of tag frequencies for this batch; used in Stage 3 to compute tag trends
- `notes_analysis`: JSON output of `analyse_review_notes` (recurring mistakes, strengths, overall impression)
- `playing_style`: qualitative assessment per dimension as returned by `analyse_playing_style`
- `comparison`: JSON output of `compare_analyses` plus tag trends; NULL for the first batch

## Review Note Format

Each markdown file contains:
- A metadata header block with backtick-quoted values (Date, Opponent's Name, Server, Game Link, Result, Played as, Handicap, Time setting)
- A `___` separator
- Free-form bullet-point review notes (end-of-game notes, move comments, AI notes, evaluation)


## LLM Integration

- **Stage 1 model**: `claude-haiku-4-5-20251001` — structured field extraction is mechanical; Haiku is fast and cheap enough for per-game calls
- **Stage 2 model**: `claude-sonnet-4-6` — pattern analysis and coaching insights require stronger reasoning
- **Stage 3 model**: `claude-haiku-4-5-20251001` — comparing structured JSON outputs is straightforward; Haiku is sufficient
- **Output**: Responses should be parsed into whatever Python type best matches the output — a `dict` for structured multi-field responses, a `list` for collections, or a plain `str` for narrative text. Don't force JSON where a simpler type is more natural.
- **API key**: Read from the `CLAUDE_API_KEY` environment variable
- **Client**: Use the `anthropic` Python SDK (`uv add anthropic`)

### Prompts
Stored in `prompt_configs.json`. 

Keys and their roles:
- `go_review_system_prompt` *(Stage 1)* — instructs the model to extract four structured fields from a single game's raw notes: `key_mistake`, `key_mistake_cause`, `positive_point`, and `game_tags`. `key_mistake`, `key_mistake_cause`, and `positive_point` are stored in `reviews` for reference but are not used in later pipeline stages. `game_tags` flows into Stage 2 for tag counting. Tags must be drawn from a fixed vocabulary; new tags are only invented when nothing in the vocabulary fits.
- `go_review_notes_analyser` *(Stage 2)* — given the combined raw notes from the current batch, identifies recurring patterns and returns a three-field structure: `recurring_mistakes` (each with `pattern`, `cause_hypothesis`, and `focus`), `recurring_strengths` (each with `pattern` and `cause_hypothesis`), and `overall_impression` (a short paragraph naming the single most impactful area to improve).
- `go_playing_style_analyser` *(Stage 2)* — given the combined raw notes and win/loss record for non-handicap games, produces a qualitative description of the player's tendencies across the 7 skill dimensions. Each dimension returns a short descriptive assessment grounded in specific evidence from the notes. No numeric scores.
- `go_review_progress_analyser` *(Stage 3)* — given the `recurring_mistakes`/`recurring_strengths` and playing style assessments from both the previous and current analysis (raw notes are not re-sent), produces a structured comparison with three fields: `improved`, `same`, and `regressed`. Tag trends are computed programmatically and not passed to the model.

## Game Tag Vocabulary

Tags are extracted per game in Stage 1. The model must draw from this vocabulary wherever possible; new tags are only invented when nothing fits, and must match the style of existing tags (short, noun-phrase or verb-phrase, no punctuation). 2–6 tags per game; prefer specific over general.

**Mistakes — Aggression & Style**
- Tried too hard to kill
- Overly aggressive play
- Played too passively
- Played too heavily
- Played slow moves
- Played unnecessary moves
- Complicated the game

**Mistakes — Shape & Technique**
- Played weak shape
- Made bad shape
- Misplayed joseki
- Misplayed cut
- Missed tesuji
- Missed weakness

**Mistakes — Reading**
- Not trusting my reading
- Many reading mistakes

**Mistakes — Life & Death**
- Mishandled invasion
- Failed deep invasion
- Died with surrounded group
- Allowed group to get surrounded
- Tried to surround when I couldn't
- Missed kill
- Missed chance to live

**Mistakes — Score & Endgame**
- Didn't count score
- Lost points in endgame
- Endgame trouble
- Endgame blunder
- Resigned too early

**Positives — Fighting**
- Lived with surrounded group
- Lived with deep invasion
- Successfully invaded opponent's area
- Exploited opponent's weak shape
- Punished overplay
- Outplayed opponent
- Found nice tesuji
- Withstood aggressive player

**Positives — Opening & Strategy**
- Played strong opening
- Played solid game
- Built large framework
- Created moyo
- Kept groups disconnected

**Positives — Mental & Endgame**
- Played calmly
- Counted during game
- Gained points in endgame

**Situational**
- Ko situation
- Handicap too thick
- Handicap too thin
- Opponent resigned early
- Opponent blundered
- Opponent ran out of time

## Playing Style Dimensions

The seven dimensions used to assess a player's tendencies and skill level. Each is described qualitatively based on specific evidence from the notes. Only non-handicap games are used, as handicap games constrain playing style in ways that aren't representative.

| Dimension | Definition |
|---|---|
| **Knowledge** | Understanding of theory: joseki, fuseki, fundamental life-and-death, common shapes. Assessed on cases where the player faces a joseki and makes active mistakes within it — not merely uncertainty about direction. Moves described as "typical" or "normal" are a positive signal. Endgame play is not a strong signal for this dimension. |
| **Reading** | Primarily mid-game fighting ability: visualising sequences, searching branches, avoiding misreads in tactical encounters. Correctly reading endgame sequences (as distinct from simply counting) is also a positive signal. |
| **Territorial Intuition** | Accurate understanding of who is ahead in the game. |
| **Technical Intuition** | Sense for shape strength and weakness; knowing how to combine weaknesses for disproportionate results. |
| **Strategy** | Ability to choose goals and directions within the game that lead to good results. |
| **Game Experience** | Knowing when to deviate from theory; composure in unfamiliar positions. Only in-game behaviour counts — post-game review remarks are excluded. Weak signals include late-game blunders that immediately lose the game, and positions that appear favourable but go badly due to misplaying during a fight. |
| **Mind Control** | Awareness of bad habits; ability to concentrate throughout a long or hard game and avoid careless play. |

Assessments should be grounded in specific evidence from the notes and avoid vague generalisations. The goal is to give the player a clear sense of where they are strong and where they are not, without the false precision of a numeric score.

## Database Notes

The current implementation uses SQLite, which is appropriate for a single-user tool. SQLite does not handle concurrent writes, so migrating to PostgreSQL will be necessary before opening the app to multiple users. The database layer is isolated in `src/pipeline/db.py` to make this migration straightforward — avoid writing raw SQL outside of that module.

## Environment

Dependencies are managed with [uv](https://github.com/astral-sh/uv). Use `uv add` to add packages and `uv run` to execute scripts.

## Coding Conventions

- All business logic lives in `src/pipeline/`; routers only handle HTTP concerns, and `frontend/app.py` only calls the API and renders UI. Do not over-invest in the Streamlit frontend — it is likely to be replaced with a proper frontend as the product matures.
- Functions skip already-processed games by checking `game_link` against the database, making the pipeline idempotent.
- `analyse_playing_style` runs once (not multiple times — repeated runs don't improve quality).
