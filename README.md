# ollama-rpg2

A browser-based top-down open-world RPG game built with FastAPI, vanilla JavaScript, canvas text rendering, local Ollama integration, and backend-authoritative runtime state.

## Stack

- Backend: Python 3.12+ with FastAPI
- Frontend: HTML, CSS, vanilla JavaScript
- Rendering: HTML5 canvas with semantic glyph mapping
- AI: Ollama at `OLLAMA_BASE_URL`
- Persistence: one browser `localStorage` autosave slot

## Current Slice

The first implemented slice provides:

- a FastAPI backend
- a `POST /api/map/generate` endpoint that returns a `128x128` emoji world
- a browser UI with a `Generate Map` button
- a `15x11` viewport that follows the player
- `W`, `A`, `S`, `D` movement

Map generation currently uses only the `# Ground` tiles from [assets/unicode/emoji-rpg.txt](/home/thokem/Workspace/ollama-rpg2/assets/unicode/emoji-rpg.txt), while the player uses the `# Player` emoji from that same file.

## Run

1. Create a virtual environment and activate it.
`python3 -m venv .venv`
`source .venv/bin/activate
2. Install dependencies with `pip install -e .[dev]`.
3. Start the app with `uvicorn app.main:app --reload --port 8017`.
4. Open `http://127.0.0.1:8017`.

## Tests

Run `pytest`.

## Ollama Config

The app reads its Ollama settings from `.env`.

The example values in [.env.example](/home/thokem/Workspace/ollama-rpg2/.env.example) are:

- `OLLAMA_BASE_URL=http://192.168.56.1:11434`
- `OLLAMA_GM_MODEL=llama3.2:3b`
- `OLLAMA_NPC_MODEL=llama3.2:3b`
- `OLLAMA_NPC_MAX_WORDS=100`

What they control:

- `OLLAMA_BASE_URL`: the Ollama server URL used for lore generation and NPC chat
- `OLLAMA_GM_MODEL`: the model used for world, village, and NPC lore generation
- `OLLAMA_NPC_MODEL`: the model used for NPC conversation replies
- `OLLAMA_NPC_MAX_WORDS`: the maximum number of words allowed in an NPC reply after normalization

Copy `.env.example` to `.env` and adjust the values for your local Ollama setup.

## Enable Logging

Logging is disabled by default.

To enable all app logging, set this in your `.env`:

`APP_LOGGING_ENABLED=true`

or in terminal:

`export APP_LOGGING_ENABLED=true`

You can copy the values from [.env.example](/home/thokem/Workspace/ollama-rpg2/.env.example) and then change the logging flag there.

When logging is enabled, the app writes these files in `logs/`:

- `ollama_lore.jsonl`
- `ollama_npc_chat.jsonl`
- `world_lore.txt`
- `village_lore.txt`
- `npc_lore.txt`
- `npc_chat.txt`

## Lore Log Formatting

If you want to inspect the lore JSONL logs more easily in VS Code, convert them into a pretty JSON array:

`python3 scripts/jsonl_to_pretty_json.py logs/ollama_lore.jsonl`

This writes `logs/ollama_lore.pretty.json` by default. You can also choose an explicit output path:

`python3 scripts/jsonl_to_pretty_json.py logs/ollama_lore.jsonl --output logs/ollama_lore.json`
