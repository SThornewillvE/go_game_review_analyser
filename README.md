# go_game_review_analyser

A tool for analysing personal Go game review notes using LLMs.

## Overview

After reviewing Go games (with an AI or teacher), notes are written in structured markdown files covering move-by-move observations, questions, AI feedback, and evaluations. This tool processes those notes to surface patterns and trends across many games.

## How it works

1. **Ingest** — Markdown game review files are parsed to extract metadata (date, opponent, server, result, etc.) and free-text review notes.
2. **Summarise** — An LLM (GPT) reads each game's notes and extracts structured fields: key mistake, cause of the mistake, a positive point, and tags describing recurring themes.
3. **Store** — Summaries are persisted to a SQLite database, skipping games already processed.
4. **Analyse** — All stored summaries are fed back to the LLM to produce an overall `did_well` / `needs_work` assessment. Tag frequencies are also computed to highlight the most common patterns.

## Structure

```
prototype/                  # Exploratory notebooks and scripts
  game_review_notes/        # Markdown game review files
src/
  main.py                   # FastAPI app exposing /games/summarise and /games/analyse
  helpers.py                # Core logic: parsing, LLM calls, DB operations
  prompt_configs.json       # LLM system prompts
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/games/summarise` | Parse new review files and store GPT summaries |
| `GET`  | `/games/analyse`   | Generate an overall analysis and return top tags |

## Requirements

- Python 3.11+
- OpenAI API key set as `OPENAI_API_KEY`
- Dependencies listed in `environment.yml`
