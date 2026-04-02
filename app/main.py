from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.content import load_tile_catalog
from app.lore import (
    generate_lore_payload,
    generate_npc_chat_reply,
    serialize_generated_villages,
    validate_world_shape,
)
from app.mapgen import VIEWPORT_HEIGHT, VIEWPORT_WIDTH, generate_map

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"

catalog = load_tile_catalog()
app = FastAPI(title="ollama-rpg2")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class LoreNpcRequest(BaseModel):
    x: int
    y: int
    tile: str
    id: str | None = None


class LoreRequest(BaseModel):
    world: list[list[str]]
    npcs: list[LoreNpcRequest]


class NpcChatLoreNpc(BaseModel):
    id: str
    name: str
    description: str


class NpcChatRequest(BaseModel):
    npcId: str
    playerLine: str
    worldLore: str
    npc: NpcChatLoreNpc
    transcript: list[list[str]]


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
            {"id": f"npc:{npc.x}:{npc.y}", "x": npc.x, "y": npc.y, "tile": npc.tile}
            for npc in generated.npcs
        ],
        "villages": serialize_generated_villages(generated.villages),
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


@app.post("/api/lore/generate")
async def create_lore(request: LoreRequest) -> Response:
    try:
        validate_world_shape(request.world)
        payload = await generate_lore_payload(
            world=request.world,
            npcs=[npc.model_dump() for npc in request.npcs],
            catalog=catalog,
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return Response(
        content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        media_type="application/json",
    )


@app.post("/api/npc/chat")
async def create_npc_chat(request: NpcChatRequest) -> Response:
    try:
        reply = await generate_npc_chat_reply(
            npc_id=request.npcId,
            world_lore=request.worldLore,
            npc=request.npc.model_dump(),
            transcript=request.transcript,
            player_line=request.playerLine,
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return Response(
        content=json.dumps({"reply": reply}, ensure_ascii=False, separators=(",", ":")),
        media_type="application/json",
    )
