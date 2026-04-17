# Go Game Review Analyser

A web application that parses hand-written Go game review notes and uses Claude to extract structured insights, track progress across batches of games, and surface coaching-style findings through a Streamlit frontend.

## How it works

1. **Upload** one or more Markdown review files → Claude (Haiku) extracts structured fields per game (Stage 1)
2. **Analyse** the current batch (≥ 20 games) → Claude (Sonnet) identifies recurring patterns and assesses playing style (Stage 2)
3. **Compare** → Claude (Haiku) automatically compares the new analysis against the previous batch to surface what has improved, stayed the same, or regressed (Stage 3)

## Setup

### Prerequisites

- Python ≥ 3.11
- [uv](https://github.com/astral-sh/uv) for dependency management
- An Anthropic API key

### Install dependencies

```bash
uv sync
```

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `CLAUDE_API_KEY` | Yes | — | Your Anthropic API key |
| `SECRET_KEY` | Yes (production) | `change-me-in-production` | Secret used to sign JWT tokens |
| `BACKEND_URL` | No | `http://localhost:8000` | URL the Streamlit frontend uses to reach the API |

Set them in your shell or a `.env` file (loaded manually or via your process manager):

```bash
export CLAUDE_API_KEY=sk-ant-...
export SECRET_KEY=a-long-random-string
```

## Running locally

### 1. Start the backend

```bash
uvicorn src.main:app --reload
```

The API will be available at `http://localhost:8000`. Interactive docs are at `http://localhost:8000/docs`.

### 2. Start the frontend

In a separate terminal:

```bash
streamlit run src/frontend/app.py
```

The Streamlit UI will open at `http://localhost:8501`.

## First-time use

1. Open the Streamlit UI and register an account on the **Register** tab.
2. Log in.
3. Upload one or more `.md` game review files using the template format (see below) and click **Process uploaded files**.
4. Once you have at least 20 games uploaded, click **Run analysis on current batch**.
5. Results (recurring patterns, playing style, win rate chart, tag breakdown) will appear below. After a second batch is analysed, a progress comparison section will also appear.

## Review file format

Each Markdown file should follow this structure:

```
Date: `2026-03-23`
Opponent's Name: `OpponentName`
Server: `OGS`
Game Link: `https://ai-sensei.com/...`
Result: `B+2.5`
Played as: `Black`
Handicap: `0`
Time setting: `20m + 5x30s`
___
* End of game notes
  * ...
* Game
  * move 19 - ...
* AI notes
  * ...
* Evaluation
  * What went well
    * ...
```

The `___` separator divides the metadata header from the free-form notes. All games must have a `Game Link` (AI Sensei URL) — this is used for deduplication.

## Project structure

```
src/
  main.py                   # FastAPI entry point
  prompt_configs.json       # Claude prompts for all pipeline stages
  routers/
    auth.py                 # /auth/register, /auth/token
    pipeline.py             # /upload, /analyse
    analyses.py             # /analyses, /analyses/latest, /analyses/tag-stats
  pipeline/
    db.py                   # SQLite helpers
    parser.py               # Markdown parsing
    llm.py                  # Anthropic client + response helper
    summariser.py           # Stage 1: per-game structured extraction
    analyser.py             # Stage 2: pattern analysis + playing style
    comparator.py           # Stage 3: progress comparison + tag trends
  frontend/
    app.py                  # Streamlit UI
```

## API reference

All endpoints except `/auth/register` and `/auth/token` require a `Bearer` token in the `Authorization` header.

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/register` | Create a new user |
| `POST` | `/auth/token` | Exchange credentials for a JWT |
| `POST` | `/upload` | Upload `.md` files; triggers Stage 1 |
| `POST` | `/analyse` | Run Stage 2 (+ Stage 3 if a prior analysis exists) |
| `GET` | `/analyses` | List all past analyses |
| `GET` | `/analyses/latest` | Full latest analysis with comparison |
| `GET` | `/analyses/tag-stats` | Tag counts broken down by all/wins/losses |

## Production deployment

For production, run behind a process manager (e.g. Gunicorn managing Uvicorn workers) or deploy to a platform like [Fly.io](https://fly.io) or [Render](https://render.com):

```bash
gunicorn src.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

**Note:** The current implementation uses SQLite, which does not support concurrent writes. Migrate to PostgreSQL before opening the app to multiple simultaneous users. The database layer is isolated in `src/pipeline/db.py` to make this straightforward.
