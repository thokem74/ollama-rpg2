from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.content import load_tile_catalog
from app.mapgen import VIEWPORT_HEIGHT, VIEWPORT_WIDTH, generate_map

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"

catalog = load_tile_catalog()
app = FastAPI(title="ollama-rpg2")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(INDEX_FILE)


@app.post("/api/map/generate")
async def create_map() -> Response:
    generated = generate_map(catalog)
    payload = {
        "world": generated.world,
        "player": {
            "x": generated.player.x,
            "y": generated.player.y,
            "tile": generated.player.tile,
        },
        "npcs": [
            {"x": npc.x, "y": npc.y, "tile": npc.tile}
            for npc in generated.npcs
        ],
        "collision": {
            "tiles": {
                "trees": list(catalog.trees),
                "plants": list(catalog.plants),
                "buildings": list(catalog.buildings),
            }
        },
        "viewport": {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
    }
    return Response(
        content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        media_type="application/json",
    )
