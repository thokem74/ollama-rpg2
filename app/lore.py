from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path
from typing import Any
from urllib import error, request

from app.content import TileCatalog
from app.mapgen import Village, village_payload

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILES = (BASE_DIR / ".env", BASE_DIR / ".env.example")


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def get_setting(name: str) -> str | None:
    if name in os.environ:
        return os.environ[name]

    for path in ENV_FILES:
        values = _parse_env_file(path)
        if name in values:
            return values[name]
    return None


def require_setting(name: str) -> str:
    value = get_setting(name)
    if value:
        return value
    raise RuntimeError(f"Missing required setting: {name}")


def village_id_from_bounds(left: int, right: int, top: int, bottom: int) -> str:
    return f"village:{left}:{top}:{right}:{bottom}"


def npc_id_from_position(x: int, y: int) -> str:
    return f"npc:{x}:{y}"


def derive_villages_from_world(world: list[list[str]], catalog: TileCatalog) -> list[dict[str, Any]]:
    target_tiles = {catalog.village, *catalog.buildings}
    seen: set[tuple[int, int]] = set()
    villages: list[dict[str, Any]] = []

    for y, row in enumerate(world):
        for x, tile in enumerate(row):
            if tile not in target_tiles or (x, y) in seen:
                continue

            queue = deque([(x, y)])
            seen.add((x, y))
            tiles: list[tuple[int, int]] = []

            while queue:
                current_x, current_y = queue.popleft()
                tiles.append((current_x, current_y))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    next_x = current_x + dx
                    next_y = current_y + dy
                    if not (0 <= next_y < len(world) and 0 <= next_x < len(world[next_y])):
                        continue
                    if (next_x, next_y) in seen:
                        continue
                    if world[next_y][next_x] not in target_tiles:
                        continue
                    seen.add((next_x, next_y))
                    queue.append((next_x, next_y))

            xs = [tile_x for tile_x, _ in tiles]
            ys = [tile_y for _, tile_y in tiles]
            left = min(xs)
            right = max(xs)
            top = min(ys)
            bottom = max(ys)
            villages.append(
                {
                    "id": village_id_from_bounds(left, right, top, bottom),
                    "bounds": {
                        "left": left,
                        "right": right,
                        "top": top,
                        "bottom": bottom,
                    },
                    "center": {
                        "x": round(sum(xs) / len(xs)),
                        "y": round(sum(ys) / len(ys)),
                    },
                    "tileCount": len(tiles),
                }
            )

    villages.sort(key=lambda village: (village["bounds"]["top"], village["bounds"]["left"]))
    return villages


def serialize_generated_villages(villages: list[Village]) -> list[dict[str, Any]]:
    payload = [village_payload(village) for village in villages]
    payload.sort(key=lambda village: (village["bounds"]["top"], village["bounds"]["left"]))
    return payload


def serialize_npcs(npcs: list[Any]) -> list[dict[str, Any]]:
    payload = [
        {
            "id": npc_id_from_position(npc.x, npc.y),
            "x": npc.x,
            "y": npc.y,
            "tile": npc.tile,
        }
        for npc in npcs
    ]
    payload.sort(key=lambda npc: (npc["y"], npc["x"]))
    return payload


def validate_world_shape(world: list[list[str]]) -> None:
    if not world or not all(isinstance(row, list) and row for row in world):
        raise ValueError("World must be a non-empty 2D tile grid.")

    width = len(world[0])
    if any(len(row) != width for row in world):
        raise ValueError("World rows must all have the same width.")
    if any(not all(isinstance(tile, str) for tile in row) for row in world):
        raise ValueError("World tiles must all be strings.")


def _build_world_summary(world: list[list[str]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in world:
        for tile in row:
            counts[tile] = counts.get(tile, 0) + 1
    return {
        "width": len(world[0]),
        "height": len(world),
        "tileCounts": counts,
    }


def _build_prompt(
    world: list[list[str]],
    villages: list[dict[str, Any]],
    npcs: list[dict[str, Any]],
) -> str:
    context = {
        "world": _build_world_summary(world),
        "villages": villages,
        "npcs": npcs,
    }
    return (
        "You are the game master for a whimsical emoji RPG world.\n"
        "Write concise, flavorful lore for the provided world state.\n"
        "Return strict JSON only with this shape:\n"
        '{'
        '"worldLore":"string",'
        '"villages":[{"id":"string","name":"string","description":"string"}],'
        '"npcs":[{"id":"string","name":"string","description":"string"}]'
        "}\n"
        "Rules:\n"
        "- Keep worldLore to 2-4 sentences.\n"
        "- Keep every village and NPC description to 1 short sentence.\n"
        "- Use every provided id exactly once in the matching array.\n"
        "- Do not invent extra entries or extra keys.\n"
        "- Names must be unique within villages and within npcs.\n"
        "Context:\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )


def _call_ollama(base_url: str, model: str, prompt: str) -> str:
    endpoint = f"{base_url.rstrip('/')}/api/generate"
    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach Ollama at {endpoint}.") from exc

    text = payload.get("response")
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Ollama returned an empty lore response.")
    return text


def _validate_lore_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _fallback_world_lore(village_count: int, npc_count: int) -> str:
    return (
        f"A young frontier links {village_count} villages across the map, and "
        f"{npc_count} wandering figures carry stories between them."
    )


def _fallback_village_name(village: dict[str, Any], index: int) -> str:
    center = village["center"]
    return f"Village {index + 1} ({center['x']},{center['y']})"


def _fallback_village_description(village: dict[str, Any]) -> str:
    center = village["center"]
    return (
        f"A settled outpost near ({center['x']}, {center['y']}) where travelers gather "
        "before crossing the frontier."
    )


def _fallback_npc_name(npc: dict[str, Any], index: int) -> str:
    return f"Wanderer {index + 1} ({npc['x']},{npc['y']})"


def _fallback_npc_description(npc: dict[str, Any]) -> str:
    return f"A roaming local often seen near ({npc['x']}, {npc['y']})."


def _sanitize_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Ollama returned invalid JSON lore.") from None
        try:
            payload = json.loads(raw_text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError("Ollama returned invalid JSON lore.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Ollama lore response must be a JSON object.")
    return payload


def _normalize_named_entries(
    entries: Any,
    expected_entities: list[dict[str, Any]],
    kind: str,
) -> dict[str, dict[str, str]]:
    expected_ids = {entity["id"] for entity in expected_entities}
    explicit_matches: dict[str, dict[str, str]] = {}
    positional_candidates: list[dict[str, Any]] = []

    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_id = _sanitize_text(entry.get("id"))
            name = _sanitize_text(entry.get("name"))
            description = _sanitize_text(entry.get("description"))
            candidate = {"name": name, "description": description}

            if entry_id in expected_ids and entry_id not in explicit_matches:
                explicit_matches[entry_id] = candidate
            else:
                positional_candidates.append(candidate)

    normalized: dict[str, dict[str, str]] = {}
    positional_index = 0

    for index, entity in enumerate(expected_entities):
        entry = explicit_matches.get(entity["id"])
        if entry is None and positional_index < len(positional_candidates):
            entry = positional_candidates[positional_index]
            positional_index += 1

        if kind == "village":
            fallback_name = _fallback_village_name(entity, index)
            fallback_description = _fallback_village_description(entity)
        else:
            fallback_name = _fallback_npc_name(entity, index)
            fallback_description = _fallback_npc_description(entity)

        normalized[entity["id"]] = {
            "name": entry["name"] if entry and entry.get("name") else fallback_name,
            "description": (
                entry["description"] if entry and entry.get("description") else fallback_description
            ),
        }

    return normalized


def _merge_lore(
    raw_payload: dict[str, Any],
    villages: list[dict[str, Any]],
    npcs: list[dict[str, Any]],
) -> dict[str, Any]:
    world_lore = _sanitize_text(raw_payload.get("worldLore")) or _fallback_world_lore(len(villages), len(npcs))
    village_lore = _normalize_named_entries(raw_payload.get("villages"), villages, "village")
    npc_lore = _normalize_named_entries(raw_payload.get("npcs"), npcs, "npc")

    merged_villages = [
        {
            **village,
            "name": village_lore[village["id"]]["name"],
            "description": village_lore[village["id"]]["description"],
        }
        for village in villages
    ]
    merged_npcs = [
        {
            **npc,
            "name": npc_lore[npc["id"]]["name"],
            "description": npc_lore[npc["id"]]["description"],
        }
        for npc in npcs
    ]

    return {
        "worldLore": world_lore,
        "villages": merged_villages,
        "npcs": merged_npcs,
    }


async def generate_lore_payload(
    world: list[list[str]],
    npcs: list[dict[str, Any]],
    catalog: TileCatalog,
) -> dict[str, Any]:
    validate_world_shape(world)

    villages = derive_villages_from_world(world, catalog)
    sorted_npcs = sorted(
        [
            {
                "id": npc.get("id") or npc_id_from_position(npc["x"], npc["y"]),
                "x": npc["x"],
                "y": npc["y"],
                "tile": npc["tile"],
            }
            for npc in npcs
        ],
        key=lambda npc: (npc["y"], npc["x"]),
    )

    prompt = _build_prompt(world, villages, sorted_npcs)
    base_url = require_setting("OLLAMA_BASE_URL")
    model = require_setting("OLLAMA_GM_MODEL")
    raw_text = _call_ollama(base_url, model, prompt)
    raw_payload = _extract_json_object(raw_text)
    return _merge_lore(raw_payload, villages, sorted_npcs)
