from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib import error, request

from app.content import TileCatalog
from app.mapgen import Village, village_payload

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILES = (BASE_DIR / ".env", BASE_DIR / ".env.example")
DEFAULT_LORE_LOG_PATH = Path("logs/ollama_lore.jsonl")
DEFAULT_NPC_CHAT_LOG_PATH = Path("logs/ollama_npc_chat.jsonl")
WORLD_LORE_TEXT_LOG_PATH = Path("logs/world_lore.txt")
VILLAGE_LORE_TEXT_LOG_PATH = Path("logs/village_lore.txt")
NPC_LORE_TEXT_LOG_PATH = Path("logs/npc_lore.txt")
NPC_CHAT_TEXT_LOG_PATH = Path("logs/npc_chat.txt")
SUPPORTED_LANGUAGES = {"en", "de"}


def normalize_language(language: str | None) -> str:
    if language in SUPPORTED_LANGUAGES:
        return language
    return "en"


def _language_name(language: str) -> str:
    return "German" if normalize_language(language) == "de" else "English"


def _language_instruction(language: str) -> str:
    return f"Write every natural-language field in {_language_name(language)}.\n"


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


def _parse_bool_setting(name: str, default: bool) -> bool:
    value = get_setting(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_lore_log_path() -> Path:
    configured = get_setting("OLLAMA_LORE_LOG_PATH")
    if not configured:
        return BASE_DIR / DEFAULT_LORE_LOG_PATH

    path = Path(configured)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def _resolve_npc_chat_log_path() -> Path:
    return BASE_DIR / DEFAULT_NPC_CHAT_LOG_PATH


def _logging_enabled() -> bool:
    return _parse_bool_setting("APP_LOGGING_ENABLED", default=False)


def _append_jsonl_log_record(record: dict[str, Any], *, log_path: Path, label: str) -> None:
    if not _logging_enabled():
        return

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")
    except OSError as exc:
        print(f"Warning: could not write {label} log to {log_path}: {exc}", file=sys.stderr)

    if _logging_enabled() and _parse_bool_setting("OLLAMA_LORE_LOG_CONSOLE", default=False):
        details = [record.get("event", label)]
        if "model" in record:
            details.append(f"model={record['model']}")
        if "durationMs" in record:
            details.append(f"durationMs={record['durationMs']}")
        print(f"[{label}-log] {' '.join(details)}", file=sys.stderr)


def _append_lore_log_record(record: dict[str, Any]) -> None:
    _append_jsonl_log_record(record, log_path=_resolve_lore_log_path(), label="lore")


def _append_npc_chat_log_record(record: dict[str, Any]) -> None:
    _append_jsonl_log_record(record, log_path=_resolve_npc_chat_log_path(), label="npc-chat")


def _resolve_text_log_path(relative_path: Path) -> Path:
    return BASE_DIR / relative_path


def _append_text_log_line(relative_path: Path, line: str) -> None:
    if not _logging_enabled():
        return

    log_path = _resolve_text_log_path(relative_path)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(_normalize_whitespace(line))
            handle.write("\n")
    except OSError as exc:
        print(f"Warning: could not write lore text log to {log_path}: {exc}", file=sys.stderr)


def _append_final_lore_text_logs(payload: dict[str, Any]) -> None:
    timestamp = _utc_timestamp()
    world_lore = _sanitize_text(payload.get("worldLore")) or ""
    _append_text_log_line(WORLD_LORE_TEXT_LOG_PATH, f"{timestamp} | {world_lore}")

    for village in payload.get("villages", []):
        center = village.get("center", {})
        _append_text_log_line(
            VILLAGE_LORE_TEXT_LOG_PATH,
            (
                f"{timestamp} | id={village['id']} | center=({center.get('x')},{center.get('y')}) | "
                f"name={village['name']} | description={village['description']}"
            ),
        )

    for npc in payload.get("npcs", []):
        _append_text_log_line(
            NPC_LORE_TEXT_LOG_PATH,
            (
                f"{timestamp} | id={npc['id']} | pos=({npc.get('x')},{npc.get('y')}) | "
                f"name={npc['name']} | description={npc['description']}"
            ),
        )


def _append_npc_chat_text_log_line(speaker: str, text: str) -> None:
    _append_text_log_line(
        NPC_CHAT_TEXT_LOG_PATH,
        f"{_utc_timestamp()} | {speaker} | {text}",
    )


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


def _build_world_lore_prompt(
    world_summary: dict[str, Any],
    village_count: int,
    npc_count: int,
    language: str,
) -> str:
    context = {
        "world": world_summary,
        "villageCount": village_count,
        "npcCount": npc_count,
    }
    return (
        "You are the game master for a whimsical emoji RPG world.\n"
        "Write concise, flavorful world lore for the provided world state.\n"
        f"{_language_instruction(language)}"
        "Return strict JSON only with this shape:\n"
        '{"worldLore":"string"}\n'
        "Rules:\n"
        "- Keep worldLore to 2-4 sentences.\n"
        "- Focus on the overall frontier, mood, and travel between settlements.\n"
        "- Do not describe individual named villages or NPCs.\n"
        "- Do not invent extra keys.\n"
        "Context:\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )


def _build_village_lore_prompt(world_lore: str, village: dict[str, Any], language: str) -> str:
    context = {
        "worldLore": world_lore,
        "village": {
            "id": village["id"],
            "bounds": village["bounds"],
            "center": village["center"],
            "tileCount": village["tileCount"],
        },
    }
    return (
        "You are the game master for a whimsical emoji RPG world.\n"
        "Write a concise name and description for exactly one village.\n"
        f"{_language_instruction(language)}"
        "Return strict JSON only with this shape:\n"
        '{"id":"string","name":"string","description":"string"}\n'
        "Rules:\n"
        "- Use the provided village id exactly.\n"
        "- Keep the description to 1 short sentence.\n"
        "- Do not invent extra keys.\n"
        "Context:\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )


def _build_npc_lore_prompt(world_lore: str, npc: dict[str, Any], language: str) -> str:
    context = {
        "worldLore": world_lore,
        "npc": {
            "id": npc["id"],
            "x": npc["x"],
            "y": npc["y"],
            "tile": npc["tile"],
        },
    }
    return (
        "You are the game master for a whimsical emoji RPG world.\n"
        "Write a concise name and description for exactly one NPC.\n"
        f"{_language_instruction(language)}"
        "Return strict JSON only with this shape:\n"
        '{"id":"string","name":"string","description":"string"}\n'
        "Rules:\n"
        "- Use the provided npc id exactly.\n"
        "- Keep the description to 1 short sentence.\n"
        "- Do not invent extra keys.\n"
        "Context:\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )


def _build_village_repair_prompt(
    world_lore: str,
    village: dict[str, Any],
    taken_names: list[str],
    language: str,
) -> str:
    context = {
        "worldLore": world_lore,
        "unavailableNames": taken_names,
        "village": {
            "id": village["id"],
            "bounds": village["bounds"],
            "center": village["center"],
            "tileCount": village["tileCount"],
        },
    }
    return (
        "You are the game master for a whimsical emoji RPG world.\n"
        "A previously generated village name collided with another village name.\n"
        "Write a replacement name and description for exactly one village.\n"
        f"{_language_instruction(language)}"
        "Return strict JSON only with this shape:\n"
        '{"id":"string","name":"string","description":"string"}\n'
        "Rules:\n"
        "- Use the provided village id exactly.\n"
        "- The name must not match any unavailableNames entry, case-insensitively.\n"
        "- Keep the description to 1 short sentence.\n"
        "- Do not invent extra keys.\n"
        "Context:\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )


def _build_npc_repair_prompt(
    world_lore: str,
    npc: dict[str, Any],
    taken_names: list[str],
    language: str,
) -> str:
    context = {
        "worldLore": world_lore,
        "unavailableNames": taken_names,
        "npc": {
            "id": npc["id"],
            "x": npc["x"],
            "y": npc["y"],
            "tile": npc["tile"],
        },
    }
    return (
        "You are the game master for a whimsical emoji RPG world.\n"
        "A previously generated NPC name collided with another NPC name.\n"
        "Write a replacement name and description for exactly one NPC.\n"
        f"{_language_instruction(language)}"
        "Return strict JSON only with this shape:\n"
        '{"id":"string","name":"string","description":"string"}\n'
        "Rules:\n"
        "- Use the provided npc id exactly.\n"
        "- The name must not match any unavailableNames entry, case-insensitively.\n"
        "- Keep the description to 1 short sentence.\n"
        "- Do not invent extra keys.\n"
        "Context:\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )


def _call_ollama(
    base_url: str,
    model: str,
    prompt: str,
    *,
    log_lore: bool = False,
    log_npc_chat: bool = False,
    lore_kind: str | None = None,
    entity_id: str | None = None,
    npc_id: str | None = None,
) -> str:
    endpoint = f"{base_url.rstrip('/')}/api/generate"
    body_payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    body = json.dumps(body_payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started_at = perf_counter()

    if log_lore:
        _append_lore_log_record(
            {
                "timestamp": _utc_timestamp(),
                "event": "lore_request",
                "endpoint": endpoint,
                "model": model,
                "loreKind": lore_kind,
                "entityId": entity_id,
                "prompt": prompt,
                "requestBody": body_payload,
            }
        )
    if log_npc_chat:
        _append_npc_chat_log_record(
            {
                "timestamp": _utc_timestamp(),
                "event": "npc_chat_request",
                "endpoint": endpoint,
                "model": model,
                "npcId": npc_id,
                "prompt": prompt,
                "requestBody": body_payload,
            }
        )

    try:
        with request.urlopen(req, timeout=60) as response:
            raw_http_payload = response.read().decode("utf-8")
            payload = json.loads(raw_http_payload)
        text = payload.get("response")
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Ollama returned an empty lore response.")
    except Exception as exc:
        if log_lore:
            _append_lore_log_record(
                {
                    "timestamp": _utc_timestamp(),
                    "event": "lore_error",
                    "endpoint": endpoint,
                    "model": model,
                    "loreKind": lore_kind,
                    "entityId": entity_id,
                    "durationMs": round((perf_counter() - started_at) * 1000),
                    "errorType": type(exc).__name__,
                    "errorMessage": str(exc),
                }
            )
        if log_npc_chat:
            _append_npc_chat_log_record(
                {
                    "timestamp": _utc_timestamp(),
                    "event": "npc_chat_error",
                    "endpoint": endpoint,
                    "model": model,
                    "npcId": npc_id,
                    "durationMs": round((perf_counter() - started_at) * 1000),
                    "errorType": type(exc).__name__,
                    "errorMessage": str(exc),
                }
            )
        if isinstance(exc, error.URLError):
            raise RuntimeError(f"Could not reach Ollama at {endpoint}.") from exc
        raise

    if log_lore:
        _append_lore_log_record(
            {
                "timestamp": _utc_timestamp(),
                "event": "lore_response",
                "endpoint": endpoint,
                "model": model,
                "loreKind": lore_kind,
                "entityId": entity_id,
                "durationMs": round((perf_counter() - started_at) * 1000),
                "rawHttpPayload": raw_http_payload,
                "responseText": text,
            }
        )
    if log_npc_chat:
        _append_npc_chat_log_record(
            {
                "timestamp": _utc_timestamp(),
                "event": "npc_chat_response",
                "endpoint": endpoint,
                "model": model,
                "npcId": npc_id,
                "durationMs": round((perf_counter() - started_at) * 1000),
                "rawHttpPayload": raw_http_payload,
                "replyText": text,
            }
        )
    return text


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _parse_positive_int_setting(name: str) -> int:
    value = require_setting(name)
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"Setting {name} must be an integer.") from exc

    if parsed <= 0:
        raise RuntimeError(f"Setting {name} must be greater than 0.")
    return parsed


def _parse_positive_int_setting_with_default(name: str, default: int) -> int:
    value = get_setting(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"Setting {name} must be an integer.") from exc

    if parsed <= 0:
        raise RuntimeError(f"Setting {name} must be greater than 0.")
    return parsed


def _limit_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).strip()


def _validate_lore_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _fallback_world_lore(village_count: int, npc_count: int, language: str) -> str:
    if normalize_language(language) == "de":
        return (
            f"Eine junge Grenzregion verbindet {village_count} Doerfer auf der Karte, und "
            f"{npc_count} wandernde Gestalten tragen Geschichten zwischen ihnen hin und her."
        )
    return (
        f"A young frontier links {village_count} villages across the map, and "
        f"{npc_count} wandering figures carry stories between them."
    )


def _fallback_village_name(village: dict[str, Any], index: int, language: str) -> str:
    center = village["center"]
    if normalize_language(language) == "de":
        return f"Dorf {index + 1} ({center['x']},{center['y']})"
    return f"Village {index + 1} ({center['x']},{center['y']})"


def _fallback_village_description(village: dict[str, Any], language: str) -> str:
    center = village["center"]
    if normalize_language(language) == "de":
        return (
            f"Ein abgelegener Ort nahe ({center['x']}, {center['y']}), an dem Reisende sich "
            "sammeln, bevor sie die Grenzregion durchqueren."
        )
    return (
        f"A settled outpost near ({center['x']}, {center['y']}) where travelers gather "
        "before crossing the frontier."
    )


def _fallback_npc_name(npc: dict[str, Any], index: int, language: str) -> str:
    if normalize_language(language) == "de":
        return f"Wanderer {index + 1} ({npc['x']},{npc['y']})"
    return f"Wanderer {index + 1} ({npc['x']},{npc['y']})"


def _fallback_npc_description(npc: dict[str, Any], language: str) -> str:
    if normalize_language(language) == "de":
        return f"Ein umherziehender Mensch, der oft in der Naehe von ({npc['x']}, {npc['y']}) zu sehen ist."
    return f"A roaming local often seen near ({npc['x']}, {npc['y']})."


def _sanitize_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = _normalize_whitespace(value)
    return text or None


def _normalize_name_key(value: str | None) -> str | None:
    text = _sanitize_text(value)
    if text is None:
        return None
    return text.lower()


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


def _extract_world_lore(raw_text: str) -> str:
    payload = _extract_json_object(raw_text)
    return _sanitize_text(payload.get("worldLore")) or ""


def _extract_named_entry(raw_text: str, expected_id: str, kind: str) -> dict[str, str]:
    payload = _extract_json_object(raw_text)
    entry_id = _sanitize_text(payload.get("id"))
    if entry_id and entry_id != expected_id:
        raise ValueError(f"Ollama returned mismatched {kind} id.")

    name = _sanitize_text(payload.get("name"))
    description = _sanitize_text(payload.get("description"))
    if not name or not description:
        raise ValueError(f"Ollama returned invalid JSON {kind} lore.")

    return {
        "id": expected_id,
        "name": name,
        "description": description,
    }


def _find_duplicate_name_ids(entries: list[dict[str, str]]) -> set[str]:
    ids_by_name: dict[str, list[str]] = {}
    for entry in entries:
        key = _normalize_name_key(entry.get("name"))
        if key is None:
            continue
        ids_by_name.setdefault(key, []).append(entry["id"])

    duplicate_ids: set[str] = set()
    for ids in ids_by_name.values():
        if len(ids) > 1:
            duplicate_ids.update(ids)
    return duplicate_ids


def _normalize_named_entries(
    entries: Any,
    expected_entities: list[dict[str, Any]],
    kind: str,
    language: str,
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
            fallback_name = _fallback_village_name(entity, index, language)
            fallback_description = _fallback_village_description(entity, language)
        else:
            fallback_name = _fallback_npc_name(entity, index, language)
            fallback_description = _fallback_npc_description(entity, language)

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
    language: str,
) -> dict[str, Any]:
    world_lore = _sanitize_text(raw_payload.get("worldLore")) or _fallback_world_lore(
        len(villages), len(npcs), language
    )
    village_lore = _normalize_named_entries(raw_payload.get("villages"), villages, "village", language)
    npc_lore = _normalize_named_entries(raw_payload.get("npcs"), npcs, "npc", language)

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
    language: str = "en",
) -> dict[str, Any]:
    validate_world_shape(world)
    normalized_language = normalize_language(language)

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
    base_url = require_setting("OLLAMA_BASE_URL")
    model = require_setting("OLLAMA_GM_MODEL")
    batch_size = _parse_positive_int_setting_with_default("OLLAMA_LORE_BATCH_SIZE", 3)
    retry_count = _parse_positive_int_setting_with_default("OLLAMA_LORE_RETRY_COUNT", 1)
    world_summary = _build_world_summary(world)

    async def call_lore(
        prompt: str,
        *,
        lore_kind: str,
        entity_id: str | None = None,
    ) -> str:
        return await asyncio.to_thread(
            _call_ollama,
            base_url,
            model,
            prompt,
            log_lore=True,
            lore_kind=lore_kind,
            entity_id=entity_id,
        )

    async def generate_world_lore() -> str:
        prompt = _build_world_lore_prompt(
            world_summary, len(villages), len(sorted_npcs), normalized_language
        )
        last_error: Exception | None = None
        for _ in range(retry_count + 1):
            try:
                world_lore = _extract_world_lore(await call_lore(prompt, lore_kind="world"))
                if world_lore:
                    return world_lore
                raise ValueError("Ollama returned invalid JSON world lore.")
            except (RuntimeError, ValueError) as exc:
                last_error = exc
        if last_error:
            _append_lore_log_record(
                {
                    "timestamp": _utc_timestamp(),
                    "event": "lore_fallback",
                    "loreKind": "world",
                    "errorType": type(last_error).__name__,
                    "errorMessage": str(last_error),
                }
            )
        return _fallback_world_lore(len(villages), len(sorted_npcs), normalized_language)

    async def generate_named_entry(
        entity: dict[str, Any],
        *,
        lore_kind: str,
    ) -> dict[str, str] | None:
        prompt = (
            _build_village_lore_prompt(world_lore, entity, normalized_language)
            if lore_kind == "village"
            else _build_npc_lore_prompt(world_lore, entity, normalized_language)
        )
        last_error: Exception | None = None
        for _ in range(retry_count + 1):
            try:
                return _extract_named_entry(
                    await call_lore(prompt, lore_kind=lore_kind, entity_id=entity["id"]),
                    entity["id"],
                    lore_kind,
                )
            except (RuntimeError, ValueError) as exc:
                last_error = exc

        if last_error:
            _append_lore_log_record(
                {
                    "timestamp": _utc_timestamp(),
                    "event": "lore_fallback",
                    "loreKind": lore_kind,
                    "entityId": entity["id"],
                    "errorType": type(last_error).__name__,
                    "errorMessage": str(last_error),
                }
            )
        return None

    async def generate_in_batches(
        entities: list[dict[str, Any]],
        *,
        lore_kind: str,
    ) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        for start in range(0, len(entities), batch_size):
            batch = entities[start : start + batch_size]
            batch_results = await asyncio.gather(
                *(generate_named_entry(entity, lore_kind=lore_kind) for entity in batch)
            )
            results.extend(result for result in batch_results if result is not None)
        return results

    async def repair_duplicate_names(
        entities: list[dict[str, Any]],
        entries: list[dict[str, str]],
        *,
        kind: str,
    ) -> list[dict[str, str]]:
        duplicate_ids = _find_duplicate_name_ids(entries)
        if not duplicate_ids:
            return entries

        entries_by_id = {entry["id"]: entry for entry in entries}
        accepted_names: set[str] = {
            key
            for entry in entries
            if entry["id"] not in duplicate_ids
            for key in [_normalize_name_key(entry.get("name"))]
            if key is not None
        }
        repaired_entries: dict[str, dict[str, str]] = {
            entry["id"]: entry for entry in entries if entry["id"] not in duplicate_ids
        }

        for entity in entities:
            entity_id = entity["id"]
            if entity_id not in duplicate_ids:
                continue

            if kind == "village":
                prompt = _build_village_repair_prompt(
                    world_lore,
                    entity,
                    sorted(entry["name"] for entry in repaired_entries.values()),
                    normalized_language,
                )
                repair_kind = "village_repair"
            else:
                prompt = _build_npc_repair_prompt(
                    world_lore,
                    entity,
                    sorted(entry["name"] for entry in repaired_entries.values()),
                    normalized_language,
                )
                repair_kind = "npc_repair"

            try:
                repaired = _extract_named_entry(
                    await call_lore(prompt, lore_kind=repair_kind, entity_id=entity_id),
                    entity_id,
                    kind,
                )
                repaired_key = _normalize_name_key(repaired.get("name"))
                if repaired_key is None or repaired_key in accepted_names:
                    raise ValueError(f"Ollama returned duplicate {kind} name during repair.")
            except (RuntimeError, ValueError) as exc:
                _append_lore_log_record(
                    {
                        "timestamp": _utc_timestamp(),
                        "event": "lore_fallback",
                        "loreKind": repair_kind,
                        "entityId": entity_id,
                        "errorType": type(exc).__name__,
                        "errorMessage": str(exc),
                    }
                )
                continue

            repaired_entries[entity_id] = repaired
            accepted_names.add(repaired_key)

        return [repaired_entries[entry["id"]] for entry in entries if entry["id"] in repaired_entries]

    world_lore = await generate_world_lore()
    village_entries = await generate_in_batches(villages, lore_kind="village")
    npc_entries = await generate_in_batches(sorted_npcs, lore_kind="npc")
    village_entries = await repair_duplicate_names(villages, village_entries, kind="village")
    npc_entries = await repair_duplicate_names(sorted_npcs, npc_entries, kind="npc")
    raw_payload = {
        "worldLore": world_lore,
        "villages": village_entries,
        "npcs": npc_entries,
    }
    merged_payload = _merge_lore(raw_payload, villages, sorted_npcs, normalized_language)
    _append_final_lore_text_logs(merged_payload)
    return merged_payload


def _build_npc_chat_prompt(
    world_lore: str,
    npc: dict[str, str],
    transcript: list[list[str]],
    player_line: str,
    max_words: int,
    language: str,
) -> str:
    context = {
        "worldLore": world_lore,
        "npc": npc,
        "recentTranscript": transcript,
        "playerLine": player_line,
        "maxWords": max_words,
    }
    return (
        "You are roleplaying a single NPC in a whimsical emoji RPG world.\n"
        "Stay fully in character as the provided NPC.\n"
        "Base your response only on the NPC's name, description, world lore, and recent transcript.\n"
        "Do not speak as a narrator, system, assistant, or any other character.\n"
        "Reply with no more than the provided maxWords limit.\n"
        f"{_language_instruction(language)}"
        "Return strict JSON only with this shape:\n"
        '{"reply":"string"}\n'
        "Context:\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )


def _extract_npc_reply(raw_text: str, max_words: int) -> str:
    raw_payload = _extract_json_object(raw_text)
    reply = raw_payload.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        raise ValueError("Ollama returned invalid JSON npc chat.")
    normalized = _normalize_whitespace(reply)
    limited = _limit_words(normalized, max_words)
    if not limited:
        raise ValueError("Ollama returned invalid JSON npc chat.")
    return limited


async def generate_npc_chat_reply(
    *,
    npc_id: str,
    world_lore: str,
    npc: dict[str, str],
    transcript: list[list[str]],
    player_line: str,
    language: str = "en",
) -> str:
    if not npc_id.strip():
        raise ValueError("npcId must be a non-empty string.")

    normalized_world_lore = _sanitize_text(world_lore)
    if not normalized_world_lore:
        raise ValueError("worldLore must be a non-empty string.")

    normalized_player_line = _sanitize_text(player_line)
    if not normalized_player_line:
        raise ValueError("playerLine must be a non-empty string.")
    normalized_language = normalize_language(language)

    normalized_npc = {
        "id": _sanitize_text(npc.get("id")),
        "name": _sanitize_text(npc.get("name")),
        "description": _sanitize_text(npc.get("description")),
    }
    if normalized_npc["id"] != npc_id:
        raise ValueError("npc.id must match npcId.")
    if not normalized_npc["name"] or not normalized_npc["description"]:
        raise ValueError("npc must include non-empty name and description.")

    normalized_transcript: list[list[str]] = []
    for entry in transcript:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError("transcript entries must be [speaker, text].")
        speaker, text = entry
        if speaker not in {"u", "n"}:
            raise ValueError("transcript speaker must be 'u' or 'n'.")
        normalized_text = _sanitize_text(text)
        if not normalized_text:
            continue
        normalized_transcript.append([speaker, normalized_text])

    base_url = require_setting("OLLAMA_BASE_URL")
    model = require_setting("OLLAMA_NPC_MODEL")
    max_words = _parse_positive_int_setting("OLLAMA_NPC_MAX_WORDS")
    prompt = _build_npc_chat_prompt(
        normalized_world_lore,
        normalized_npc,
        normalized_transcript,
        normalized_player_line,
        max_words,
        normalized_language,
    )
    _append_npc_chat_text_log_line("Player", normalized_player_line)
    try:
        raw_text = _call_ollama(
            base_url,
            model,
            prompt,
            log_npc_chat=True,
            npc_id=npc_id,
        )
        reply = _extract_npc_reply(raw_text, max_words)
    except (RuntimeError, ValueError):
        _append_npc_chat_text_log_line(normalized_npc["name"], "[NPC chat request failed]")
        raise

    _append_npc_chat_text_log_line(normalized_npc["name"], reply)
    return reply
