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
