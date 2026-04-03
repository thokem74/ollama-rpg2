import asyncio
import json
from collections import deque
from datetime import datetime
from pathlib import Path
from urllib import error

from fastapi import HTTPException
import pytest

import app.lore as lore
from app.content import load_tile_catalog
from app.main import NpcChatRequest, LoreRequest, app, create_lore, create_map, create_npc_chat
from app.mapgen import (
    MIN_VILLAGE_SPACING,
    MAX_VILLAGES,
    VIEWPORT_HEIGHT,
    VIEWPORT_WIDTH,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)


def _find_clusters(world: list[list[str]], target: str | set[str]) -> list[set[tuple[int, int]]]:
    target_tiles = {target} if isinstance(target, str) else target
    seen: set[tuple[int, int]] = set()
    clusters: list[set[tuple[int, int]]] = []

    for y, row in enumerate(world):
        for x, tile in enumerate(row):
            if tile not in target_tiles or (x, y) in seen:
                continue

            cluster: set[tuple[int, int]] = set()
            queue = deque([(x, y)])
            seen.add((x, y))

            while queue:
                cx, cy = queue.popleft()
                cluster.add((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx = cx + dx
                    ny = cy + dy
                    if 0 <= nx < WORLD_WIDTH and 0 <= ny < WORLD_HEIGHT:
                        if world[ny][nx] in target_tiles and (nx, ny) not in seen:
                            seen.add((nx, ny))
                            queue.append((nx, ny))

            clusters.append(cluster)

    return clusters


def _cluster_center(cluster: set[tuple[int, int]]) -> tuple[int, int]:
    xs = [x for x, _ in cluster]
    ys = [y for _, y in cluster]
    return (round(sum(xs) / len(xs)), round(sum(ys) / len(ys)))


def _largest_cluster_size(world: list[list[str]], target: str) -> int:
    clusters = _find_clusters(world, target)
    if not clusters:
        return 0
    return max(len(cluster) for cluster in clusters)


def test_tile_catalog_loads_expected_sections() -> None:
    catalog = load_tile_catalog()

    assert catalog.player == "🙂"
    assert {"🟢", "🟥", "🟩", "🟪", "🟫"}.issubset(set(catalog.ground))
    assert len(catalog.npcs) > 0
    assert len(catalog.trees) > 0
    assert len(catalog.plants) > 0
    assert len(catalog.buildings) > 0
    assert catalog.road == "🟥"
    assert catalog.village == "🟪"
    assert catalog.habitable == frozenset(("🟩", "🟫"))
    assert catalog.blocked == frozenset()
    assert catalog.rough == frozenset()


def test_generate_map_response_shape_and_tiles() -> None:
    response = asyncio.run(create_map())
    assert response.media_type == "application/json"

    payload = json.loads(response.body)
    world = payload["world"]
    player = payload["player"]
    npcs = payload["npcs"]
    collision = payload["collision"]
    viewport = payload["viewport"]
    villages = payload["villages"]
    catalog = load_tile_catalog()

    assert len(world) == WORLD_HEIGHT
    assert all(len(row) == WORLD_WIDTH for row in world)

    allowed_tiles = set(catalog.ground) | set(catalog.trees) | set(catalog.plants) | set(catalog.buildings)
    assert all(tile in allowed_tiles for row in world for tile in row)
    assert all(tile != "🟦" for row in world for tile in row)
    assert all(tile != "⬜" for row in world for tile in row)

    grass_count = sum(tile == "🟩" for row in world for tile in row)
    forest_count = sum(tile == "🟢" for row in world for tile in row)
    tree_count = sum(tile in catalog.trees for row in world for tile in row)
    plant_count = sum(tile in catalog.plants for row in world for tile in row)
    sand_count = sum(tile == "🟨" for row in world for tile in row)
    soil_count = sum(tile == "🟫" for row in world for tile in row)
    rock_count = sum(tile == "⬛" for row in world for tile in row)
    assert soil_count > grass_count
    assert soil_count > forest_count
    assert grass_count > 0
    assert forest_count > 0
    assert tree_count > 0
    assert plant_count > 0
    assert sand_count == 0
    assert rock_count == 0
    assert _largest_cluster_size(world, "🟢") >= 50
    assert _largest_cluster_size(world, "🟩") >= 50

    assert player["tile"] == "🙂"
    assert 0 <= player["x"] < WORLD_WIDTH
    assert 0 <= player["y"] < WORLD_HEIGHT
    assert world[player["y"]][player["x"]] != "🟦"
    assert npcs
    assert all(npc["tile"] in catalog.npcs for npc in npcs)
    assert all(npc["id"] == f"npc:{npc['x']}:{npc['y']}" for npc in npcs)
    assert collision == {
        "tiles": {
            "trees": list(catalog.trees),
            "plants": list(catalog.plants),
            "buildings": list(catalog.buildings),
        }
    }

    assert viewport == {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}

    settlement_tiles = {catalog.village, *catalog.buildings}
    village_clusters = _find_clusters(world, settlement_tiles)
    assert 4 <= len(village_clusters) <= MAX_VILLAGES
    assert all(100 <= len(cluster) <= 400 for cluster in village_clusters)
    assert all(world[npc["y"]][npc["x"]] == catalog.village for npc in npcs)
    feature_positions = [
        (x, y)
        for y, row in enumerate(world)
        for x, tile in enumerate(row)
        if tile in set(catalog.trees) | set(catalog.plants) | set(catalog.buildings)
    ]
    feature_positions.extend((npc["x"], npc["y"]) for npc in npcs)
    assert feature_positions
    for index, (x, y) in enumerate(feature_positions):
        for other_x, other_y in feature_positions[index + 1 :]:
            assert max(abs(x - other_x), abs(y - other_y)) >= 3

    road_tiles = sum(tile == catalog.road for row in world for tile in row)
    assert road_tiles > 0

    centers = [_cluster_center(cluster) for cluster in village_clusters]
    for index, center in enumerate(centers):
        for other in centers[index + 1 :]:
            dx = center[0] - other[0]
            dy = center[1] - other[1]
            assert (dx * dx) + (dy * dy) >= (MIN_VILLAGE_SPACING - 4) ** 2

    assert len(villages) >= len(village_clusters)
    assert len(villages) <= MAX_VILLAGES
    assert all(village["id"].startswith("village:") for village in villages)
    assert all(village["bounds"]["left"] <= village["center"]["x"] <= village["bounds"]["right"] for village in villages)
    assert all(village["bounds"]["top"] <= village["center"]["y"] <= village["bounds"]["bottom"] for village in villages)
    assert len({village["id"] for village in villages}) == len(villages)


def test_road_network_connects_village_clusters() -> None:
    payload = json.loads(asyncio.run(create_map()).body)
    world = payload["world"]
    catalog = load_tile_catalog()
    village_clusters = _find_clusters(world, catalog.village)
    assert 4 <= len(village_clusters) <= MAX_VILLAGES

    walkable = set(catalog.habitable) | set(catalog.rough) | {catalog.road, catalog.village}
    start = next(iter(village_clusters[0]))
    queue = deque([start])
    seen = {start}

    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx = x + dx
            ny = y + dy
            if 0 <= nx < WORLD_WIDTH and 0 <= ny < WORLD_HEIGHT:
                if (nx, ny) not in seen and world[ny][nx] in walkable:
                    seen.add((nx, ny))
                    queue.append((nx, ny))

    assert all(any(point in seen for point in cluster) for cluster in village_clusters)
    assert all(
        world[y][x] != catalog.road or any(
            (
                0 <= x + dx < WORLD_WIDTH
                and 0 <= y + dy < WORLD_HEIGHT
                and world[y + dy][x + dx] in {catalog.road, catalog.village}
            )
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
        )
        for y, row in enumerate(world)
        for x, tile in enumerate(row)
        if tile == catalog.road
    )


def test_lore_generate_endpoint_returns_world_village_and_npc_lore(monkeypatch) -> None:
    world = [["🟩" for _ in range(6)] for _ in range(6)]
    for y in range(1, 3):
        for x in range(1, 3):
            world[y][x] = "🟪"
    npcs = [{"id": "npc:4:1", "x": 4, "y": 1, "tile": "🧑‍🌾"}]
    calls: list[tuple[str | None, str | None]] = []

    def fake_call_ollama(base_url, model, prompt, **kwargs):
        calls.append((kwargs.get("lore_kind"), kwargs.get("entity_id")))
        lore_kind = kwargs.get("lore_kind")
        entity_id = kwargs.get("entity_id")
        if lore_kind == "world":
            return json.dumps(
                {"worldLore": "A patient frontier grows between fields and footpaths."},
                ensure_ascii=False,
            )
        if lore_kind == "village":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Moss Hollow",
                    "description": "A snug village where every porch faces the same market square.",
                },
                ensure_ascii=False,
            )
        if lore_kind == "npc":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Toma Reed",
                    "description": "A farmer who knows every shortcut through the valley.",
                },
                ensure_ascii=False,
            )
        raise AssertionError(f"Unexpected lore kind: {lore_kind}")

    monkeypatch.setattr("app.lore._call_ollama", fake_call_ollama)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_GM_MODEL", "gm-model")

    response = asyncio.run(create_lore(LoreRequest.model_validate({"world": world, "npcs": npcs})))
    assert response.media_type == "application/json"
    payload = json.loads(response.body)
    assert payload["worldLore"] == "A patient frontier grows between fields and footpaths."
    assert payload["villages"] == [
        {
            "id": "village:1:1:2:2",
            "name": "Moss Hollow",
            "description": "A snug village where every porch faces the same market square.",
            "bounds": {"left": 1, "right": 2, "top": 1, "bottom": 2},
            "center": {"x": 2, "y": 2},
            "tileCount": 4,
        }
    ]
    assert payload["npcs"] == [
        {
            "id": "npc:4:1",
            "x": 4,
            "y": 1,
            "tile": "🧑‍🌾",
            "name": "Toma Reed",
            "description": "A farmer who knows every shortcut through the valley.",
        }
    ]
    assert calls == [("world", None), ("village", "village:1:1:2:2"), ("npc", "npc:4:1")]


def test_lore_generate_endpoint_retries_failed_entity_and_recovers(monkeypatch) -> None:
    world = [["🟩" for _ in range(5)] for _ in range(5)]
    world[1][1] = "🟪"
    npcs = [{"id": "npc:2:1", "x": 2, "y": 1, "tile": "🧑‍🌾"}]
    attempts = {"village": 0}

    def fake_call_ollama(base_url, model, prompt, **kwargs):
        lore_kind = kwargs.get("lore_kind")
        entity_id = kwargs.get("entity_id")
        if lore_kind == "world":
            return json.dumps({"worldLore": "A windy trade path ties the settlement to the road."}, ensure_ascii=False)
        if lore_kind == "village":
            attempts["village"] += 1
            if attempts["village"] == 1:
                return '{"id":"wrong","name":"Bad","description":"Bad."}'
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Bramble Post",
                    "description": "A tiny waypoint where caravans rest before dusk.",
                },
                ensure_ascii=False,
            )
        if lore_kind == "npc":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Edda Pike",
                    "description": "A patient guide who knows the safest roadside camps.",
                },
                ensure_ascii=False,
            )
        raise AssertionError(f"Unexpected lore kind: {lore_kind}")

    monkeypatch.setattr("app.lore._call_ollama", fake_call_ollama)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_GM_MODEL", "gm-model")
    monkeypatch.setenv("OLLAMA_LORE_RETRY_COUNT", "1")

    response = asyncio.run(create_lore(LoreRequest.model_validate({"world": world, "npcs": npcs})))
    payload = json.loads(response.body)

    assert attempts["village"] == 2
    assert payload["villages"][0]["name"] == "Bramble Post"
    assert payload["npcs"][0]["name"] == "Edda Pike"


def test_lore_generate_endpoint_falls_back_after_retry_exhaustion(monkeypatch) -> None:
    world = [["🟩" for _ in range(5)] for _ in range(5)]
    world[1][1] = "🟪"
    world[1][2] = "🟪"
    npcs = [{"id": "npc:3:1", "x": 3, "y": 1, "tile": "🧑‍🌾"}]

    def fake_call_ollama(base_url, model, prompt, **kwargs):
        lore_kind = kwargs.get("lore_kind")
        if lore_kind == "world":
            return "not valid json at all"
        if lore_kind in {"village", "npc"}:
            return '{"id":"wrong-id"}'
        raise AssertionError(f"Unexpected lore kind: {lore_kind}")

    monkeypatch.setattr("app.lore._call_ollama", fake_call_ollama)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_GM_MODEL", "gm-model")
    monkeypatch.setenv("OLLAMA_LORE_RETRY_COUNT", "1")

    response = asyncio.run(create_lore(LoreRequest.model_validate({"world": world, "npcs": npcs})))
    payload = json.loads(response.body)

    assert payload["worldLore"] == "A young frontier links 1 villages across the map, and 1 wandering figures carry stories between them."
    assert payload["villages"][0]["id"] == "village:1:1:2:1"
    assert payload["villages"][0]["name"] == "Village 1 (2,1)"
    assert payload["villages"][0]["description"] == "A settled outpost near (2, 1) where travelers gather before crossing the frontier."
    assert payload["npcs"][0]["id"] == "npc:3:1"
    assert payload["npcs"][0]["name"] == "Wanderer 1 (3,1)"
    assert payload["npcs"][0]["description"] == "A roaming local often seen near (3, 1)."


def test_lore_generate_endpoint_preserves_order_across_batched_generation(monkeypatch) -> None:
    world = [["🟩" for _ in range(8)] for _ in range(8)]
    for y in range(1, 3):
        for x in range(1, 3):
            world[y][x] = "🟪"
    for y in range(4, 6):
        for x in range(4, 6):
            world[y][x] = "🟪"
    npcs = [
        {"id": "npc:6:1", "x": 6, "y": 1, "tile": "🧑‍🌾"},
        {"id": "npc:1:6", "x": 1, "y": 6, "tile": "👩‍🌾"},
    ]

    def fake_call_ollama(base_url, model, prompt, **kwargs):
        lore_kind = kwargs.get("lore_kind")
        entity_id = kwargs.get("entity_id")
        if lore_kind == "world":
            return json.dumps({"worldLore": "Roads and rumors tie the frontier together."}, ensure_ascii=False)
        if lore_kind == "village":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": f"Village {entity_id[-1]}",
                    "description": f"Description for {entity_id}.",
                },
                ensure_ascii=False,
            )
        if lore_kind == "npc":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": f"NPC {entity_id[-1]}",
                    "description": f"Description for {entity_id}.",
                },
                ensure_ascii=False,
            )
        raise AssertionError(f"Unexpected lore kind: {lore_kind}")

    monkeypatch.setattr("app.lore._call_ollama", fake_call_ollama)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_GM_MODEL", "gm-model")
    monkeypatch.setenv("OLLAMA_LORE_BATCH_SIZE", "2")

    response = asyncio.run(create_lore(LoreRequest.model_validate({"world": world, "npcs": npcs})))
    payload = json.loads(response.body)

    assert [village["id"] for village in payload["villages"]] == [
        "village:1:1:2:2",
        "village:4:4:5:5",
    ]
    assert [npc["id"] for npc in payload["npcs"]] == ["npc:6:1", "npc:1:6"]
    assert [village["name"] for village in payload["villages"]] == ["Village 2", "Village 5"]
    assert [npc["name"] for npc in payload["npcs"]] == ["NPC 1", "NPC 6"]


def test_lore_generate_repairs_duplicate_village_names(monkeypatch) -> None:
    world = [["🟩" for _ in range(8)] for _ in range(8)]
    for y in range(1, 3):
        for x in range(1, 3):
            world[y][x] = "🟪"
    for y in range(4, 6):
        for x in range(4, 6):
            world[y][x] = "🟪"
    npcs: list[dict[str, object]] = []
    calls: list[tuple[str | None, str | None]] = []

    def fake_call_ollama(base_url, model, prompt, **kwargs):
        lore_kind = kwargs.get("lore_kind")
        entity_id = kwargs.get("entity_id")
        calls.append((lore_kind, entity_id))
        if lore_kind == "world":
            return json.dumps({"worldLore": "Quiet roads link the frontier."}, ensure_ascii=False)
        if lore_kind == "village":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Oakrest",
                    "description": f"Description for {entity_id}.",
                },
                ensure_ascii=False,
            )
        if lore_kind == "village_repair":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Stoneharbor",
                    "description": f"Repaired description for {entity_id}.",
                },
                ensure_ascii=False,
            )
        raise AssertionError(f"Unexpected lore kind: {lore_kind}")

    monkeypatch.setattr("app.lore._call_ollama", fake_call_ollama)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_GM_MODEL", "gm-model")

    response = asyncio.run(create_lore(LoreRequest.model_validate({"world": world, "npcs": npcs})))
    payload = json.loads(response.body)

    assert [village["name"] for village in payload["villages"]] == ["Stoneharbor", "Village 2 (4,4)"]
    assert ("village_repair", "village:1:1:2:2") in calls
    assert ("village_repair", "village:4:4:5:5") in calls


def test_lore_generate_repairs_case_insensitive_duplicate_npc_names(monkeypatch) -> None:
    world = [["🟩" for _ in range(8)] for _ in range(8)]
    world[1][1] = "🟪"
    npcs = [
        {"id": "npc:2:1", "x": 2, "y": 1, "tile": "🧑‍🌾"},
        {"id": "npc:4:1", "x": 4, "y": 1, "tile": "👩‍🌾"},
    ]
    calls: list[tuple[str | None, str | None]] = []

    def fake_call_ollama(base_url, model, prompt, **kwargs):
        lore_kind = kwargs.get("lore_kind")
        entity_id = kwargs.get("entity_id")
        calls.append((lore_kind, entity_id))
        if lore_kind == "world":
            return json.dumps({"worldLore": "The frontier is alive with rumor."}, ensure_ascii=False)
        if lore_kind == "village":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Hillview",
                    "description": "A village at the edge of the road.",
                },
                ensure_ascii=False,
            )
        if lore_kind == "npc":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Mira" if entity_id == "npc:2:1" else "mira",
                    "description": f"Description for {entity_id}.",
                },
                ensure_ascii=False,
            )
        if lore_kind == "npc_repair":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Tobin",
                    "description": f"Repaired description for {entity_id}.",
                },
                ensure_ascii=False,
            )
        raise AssertionError(f"Unexpected lore kind: {lore_kind}")

    monkeypatch.setattr("app.lore._call_ollama", fake_call_ollama)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_GM_MODEL", "gm-model")

    response = asyncio.run(create_lore(LoreRequest.model_validate({"world": world, "npcs": npcs})))
    payload = json.loads(response.body)

    assert [npc["name"] for npc in payload["npcs"]] == ["Tobin", "Wanderer 2 (4,1)"]
    assert ("npc_repair", "npc:2:1") in calls
    assert ("npc_repair", "npc:4:1") in calls


def test_lore_generate_falls_back_when_repair_name_still_duplicates(monkeypatch) -> None:
    world = [["🟩" for _ in range(8)] for _ in range(8)]
    world[1][1] = "🟪"
    npcs = [
        {"id": "npc:2:1", "x": 2, "y": 1, "tile": "🧑‍🌾"},
        {"id": "npc:4:1", "x": 4, "y": 1, "tile": "👩‍🌾"},
    ]

    def fake_call_ollama(base_url, model, prompt, **kwargs):
        lore_kind = kwargs.get("lore_kind")
        entity_id = kwargs.get("entity_id")
        if lore_kind == "world":
            return json.dumps({"worldLore": "A patient frontier grows between fields and footpaths."}, ensure_ascii=False)
        if lore_kind == "village":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Moss Hollow",
                    "description": "A snug village where every porch faces the same market square.",
                },
                ensure_ascii=False,
            )
        if lore_kind == "npc":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Tobin",
                    "description": "A farmer who knows every shortcut through the valley.",
                },
                ensure_ascii=False,
            )
        if lore_kind == "npc_repair":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Tobin",
                    "description": "Another duplicated name.",
                },
                ensure_ascii=False,
            )
        raise AssertionError(f"Unexpected lore kind: {lore_kind}")

    monkeypatch.setattr("app.lore._call_ollama", fake_call_ollama)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_GM_MODEL", "gm-model")

    response = asyncio.run(create_lore(LoreRequest.model_validate({"world": world, "npcs": npcs})))
    payload = json.loads(response.body)

    assert payload["villages"][0]["name"] == "Moss Hollow"
    assert [npc["name"] for npc in payload["npcs"]] == ["Tobin", "Wanderer 2 (4,1)"]


def test_lore_generate_falls_back_when_repair_response_is_invalid(monkeypatch) -> None:
    world = [["🟩" for _ in range(8)] for _ in range(8)]
    world[1][1] = "🟪"
    npcs = [
        {"id": "npc:2:1", "x": 2, "y": 1, "tile": "🧑‍🌾"},
        {"id": "npc:4:1", "x": 4, "y": 1, "tile": "👩‍🌾"},
    ]

    def fake_call_ollama(base_url, model, prompt, **kwargs):
        lore_kind = kwargs.get("lore_kind")
        entity_id = kwargs.get("entity_id")
        if lore_kind == "world":
            return json.dumps({"worldLore": "Rumor and trade fill the roads."}, ensure_ascii=False)
        if lore_kind == "village":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Hillview",
                    "description": "A village at the edge of the road.",
                },
                ensure_ascii=False,
            )
        if lore_kind == "npc":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Mira" if entity_id == "npc:2:1" else "mira",
                    "description": f"Description for {entity_id}.",
                },
                ensure_ascii=False,
            )
        if lore_kind == "npc_repair":
            return '{"id":"wrong-id"}'
        raise AssertionError(f"Unexpected lore kind: {lore_kind}")

    monkeypatch.setattr("app.lore._call_ollama", fake_call_ollama)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_GM_MODEL", "gm-model")

    response = asyncio.run(create_lore(LoreRequest.model_validate({"world": world, "npcs": npcs})))
    payload = json.loads(response.body)

    assert [npc["name"] for npc in payload["npcs"]] == ["Wanderer 1 (2,1)", "Wanderer 2 (4,1)"]


def test_lore_generate_writes_human_readable_text_logs(monkeypatch, tmp_path) -> None:
    world = [["🟩" for _ in range(6)] for _ in range(6)]
    for y in range(1, 3):
        for x in range(1, 3):
            world[y][x] = "🟪"
    npcs = [{"id": "npc:4:1", "x": 4, "y": 1, "tile": "🧑‍🌾"}]

    def fake_call_ollama(base_url, model, prompt, **kwargs):
        lore_kind = kwargs.get("lore_kind")
        entity_id = kwargs.get("entity_id")
        if lore_kind == "world":
            return json.dumps(
                {"worldLore": "A patient frontier grows\nbetween fields and footpaths."},
                ensure_ascii=False,
            )
        if lore_kind == "village":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Moss Hollow",
                    "description": "A snug village\nwhere every porch faces the same market square.",
                },
                ensure_ascii=False,
            )
        if lore_kind == "npc":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Toma Reed",
                    "description": "A farmer\nwho knows every shortcut through the valley.",
                },
                ensure_ascii=False,
            )
        raise AssertionError(f"Unexpected lore kind: {lore_kind}")

    monkeypatch.setattr("app.lore._call_ollama", fake_call_ollama)
    monkeypatch.setattr(lore, "BASE_DIR", tmp_path)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_GM_MODEL", "gm-model")

    asyncio.run(create_lore(LoreRequest.model_validate({"world": world, "npcs": npcs})))

    world_lines = (tmp_path / "logs/world_lore.txt").read_text(encoding="utf-8").splitlines()
    village_lines = (tmp_path / "logs/village_lore.txt").read_text(encoding="utf-8").splitlines()
    npc_lines = (tmp_path / "logs/npc_lore.txt").read_text(encoding="utf-8").splitlines()

    assert len(world_lines) == 1
    assert len(village_lines) == 1
    assert len(npc_lines) == 1
    assert " | A patient frontier grows between fields and footpaths." in world_lines[0]
    assert "id=village:1:1:2:2 | center=(2,2) | name=Moss Hollow | description=A snug village where every porch faces the same market square." in village_lines[0]
    assert "id=npc:4:1 | pos=(4,1) | name=Toma Reed | description=A farmer who knows every shortcut through the valley." in npc_lines[0]
    for line in world_lines + village_lines + npc_lines:
        timestamp = line.split(" | ", 1)[0]
        assert timestamp.endswith("Z")
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def test_lore_text_logs_reflect_final_repaired_and_fallback_names(monkeypatch, tmp_path) -> None:
    world = [["🟩" for _ in range(8)] for _ in range(8)]
    world[1][1] = "🟪"
    npcs = [
        {"id": "npc:2:1", "x": 2, "y": 1, "tile": "🧑‍🌾"},
        {"id": "npc:4:1", "x": 4, "y": 1, "tile": "👩‍🌾"},
    ]

    def fake_call_ollama(base_url, model, prompt, **kwargs):
        lore_kind = kwargs.get("lore_kind")
        entity_id = kwargs.get("entity_id")
        if lore_kind == "world":
            return json.dumps({"worldLore": "Rumor and trade fill the roads."}, ensure_ascii=False)
        if lore_kind == "village":
            return json.dumps(
                {"id": entity_id, "name": "Hillview", "description": "A village at the edge of the road."},
                ensure_ascii=False,
            )
        if lore_kind == "npc":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Mira" if entity_id == "npc:2:1" else "mira",
                    "description": f"Description for {entity_id}.",
                },
                ensure_ascii=False,
            )
        if lore_kind == "npc_repair":
            return '{"id":"wrong-id"}'
        raise AssertionError(f"Unexpected lore kind: {lore_kind}")

    monkeypatch.setattr("app.lore._call_ollama", fake_call_ollama)
    monkeypatch.setattr(lore, "BASE_DIR", tmp_path)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_GM_MODEL", "gm-model")

    asyncio.run(create_lore(LoreRequest.model_validate({"world": world, "npcs": npcs})))

    village_lines = (tmp_path / "logs/village_lore.txt").read_text(encoding="utf-8").splitlines()
    npc_lines = (tmp_path / "logs/npc_lore.txt").read_text(encoding="utf-8").splitlines()

    assert "name=Hillview" in village_lines[0]
    assert "name=Wanderer 1 (2,1)" in npc_lines[0]
    assert "name=Wanderer 2 (4,1)" in npc_lines[1]


def test_lore_generate_survives_human_readable_log_write_failure(monkeypatch, tmp_path) -> None:
    world = [["🟩" for _ in range(6)] for _ in range(6)]
    for y in range(1, 3):
        for x in range(1, 3):
            world[y][x] = "🟪"
    npcs = [{"id": "npc:4:1", "x": 4, "y": 1, "tile": "🧑‍🌾"}]

    def fake_call_ollama(base_url, model, prompt, **kwargs):
        lore_kind = kwargs.get("lore_kind")
        entity_id = kwargs.get("entity_id")
        if lore_kind == "world":
            return json.dumps({"worldLore": "A patient frontier grows between fields and footpaths."}, ensure_ascii=False)
        if lore_kind == "village":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Moss Hollow",
                    "description": "A snug village where every porch faces the same market square.",
                },
                ensure_ascii=False,
            )
        if lore_kind == "npc":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Toma Reed",
                    "description": "A farmer who knows every shortcut through the valley.",
                },
                ensure_ascii=False,
            )
        raise AssertionError(f"Unexpected lore kind: {lore_kind}")

    original_open = Path.open

    def fake_open(self: Path, *args, **kwargs):
        if self.name in {"world_lore.txt", "village_lore.txt", "npc_lore.txt"}:
            raise OSError("disk full")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr("app.lore._call_ollama", fake_call_ollama)
    monkeypatch.setattr(lore, "BASE_DIR", tmp_path)
    monkeypatch.setattr(Path, "open", fake_open)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_GM_MODEL", "gm-model")

    response = asyncio.run(create_lore(LoreRequest.model_validate({"world": world, "npcs": npcs})))
    payload = json.loads(response.body)

    assert payload["worldLore"] == "A patient frontier grows between fields and footpaths."
    assert payload["villages"][0]["name"] == "Moss Hollow"
    assert payload["npcs"][0]["name"] == "Toma Reed"


def test_call_ollama_logs_lore_request_and_response(monkeypatch, tmp_path) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "response": '{"worldLore":"A bright path crosses the valley.","villages":[],"npcs":[]}'
                },
                ensure_ascii=False,
            ).encode("utf-8")

    monkeypatch.setenv("OLLAMA_LORE_LOG_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_LORE_LOG_PATH", str(tmp_path / "custom-lore.jsonl"))
    monkeypatch.setattr(lore.request, "urlopen", lambda req, timeout=60: FakeResponse())

    prompt = "Write concise lore."
    text = lore._call_ollama(
        "http://ollama.test",
        "gm-model",
        prompt,
        log_lore=True,
        lore_kind="village",
        entity_id="village:1:1:2:2",
    )

    assert '"worldLore":"A bright path crosses the valley."' in text

    records = [
        json.loads(line)
        for line in (tmp_path / "custom-lore.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [record["event"] for record in records] == ["lore_request", "lore_response"]
    assert records[0]["endpoint"] == "http://ollama.test/api/generate"
    assert records[0]["model"] == "gm-model"
    assert records[0]["loreKind"] == "village"
    assert records[0]["entityId"] == "village:1:1:2:2"
    assert records[0]["prompt"] == prompt
    assert records[0]["requestBody"]["prompt"] == prompt
    assert records[1]["rawHttpPayload"]
    assert records[1]["loreKind"] == "village"
    assert records[1]["entityId"] == "village:1:1:2:2"
    assert records[1]["responseText"] == text
    assert isinstance(records[1]["durationMs"], int)
    assert records[1]["durationMs"] >= 0
    for record in records:
        assert record["timestamp"].endswith("Z")
        datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))


def test_call_ollama_logs_lore_errors(monkeypatch, tmp_path) -> None:
    def fake_urlopen(req, timeout=60):
        raise error.URLError("connection refused")

    monkeypatch.setenv("OLLAMA_LORE_LOG_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_LORE_LOG_PATH", str(tmp_path / "errors.jsonl"))
    monkeypatch.setattr(lore.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as exc_info:
        lore._call_ollama(
            "http://ollama.test",
            "gm-model",
            "Prompt",
            log_lore=True,
            lore_kind="npc",
            entity_id="npc:2:3",
        )

    assert exc_info.value.args[0] == "Could not reach Ollama at http://ollama.test/api/generate."

    records = [json.loads(line) for line in (tmp_path / "errors.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [record["event"] for record in records] == ["lore_request", "lore_error"]
    assert records[0]["loreKind"] == "npc"
    assert records[0]["entityId"] == "npc:2:3"
    assert records[1]["loreKind"] == "npc"
    assert records[1]["entityId"] == "npc:2:3"
    assert records[1]["errorType"] == "URLError"
    assert "connection refused" in records[1]["errorMessage"]
    assert isinstance(records[1]["durationMs"], int)


def test_call_ollama_logs_repair_lore_kinds(monkeypatch, tmp_path) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"response": '{"id":"npc:4:1","name":"Tobin","description":"A watchful local."}'},
                ensure_ascii=False,
            ).encode("utf-8")

    monkeypatch.setenv("OLLAMA_LORE_LOG_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_LORE_LOG_PATH", str(tmp_path / "repair.jsonl"))
    monkeypatch.setattr(lore.request, "urlopen", lambda req, timeout=60: FakeResponse())

    lore._call_ollama(
        "http://ollama.test",
        "gm-model",
        "Prompt",
        log_lore=True,
        lore_kind="npc_repair",
        entity_id="npc:4:1",
    )

    records = [json.loads(line) for line in (tmp_path / "repair.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [record["loreKind"] for record in records] == ["npc_repair", "npc_repair"]
    assert [record["entityId"] for record in records] == ["npc:4:1", "npc:4:1"]


def test_call_ollama_skips_logging_when_disabled(monkeypatch, tmp_path) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"response": '{"worldLore":"Quiet roads.","villages":[],"npcs":[]}'}, ensure_ascii=False).encode("utf-8")

    log_path = tmp_path / "disabled.jsonl"
    monkeypatch.setenv("OLLAMA_LORE_LOG_ENABLED", "false")
    monkeypatch.setenv("OLLAMA_LORE_LOG_PATH", str(log_path))
    monkeypatch.setattr(lore.request, "urlopen", lambda req, timeout=60: FakeResponse())

    lore._call_ollama("http://ollama.test", "gm-model", "Prompt", log_lore=True)

    assert not log_path.exists()


def test_app_routes_include_ui_and_generation_endpoint() -> None:
    routes = {
        (method, route.path)
        for route in app.routes
        if hasattr(route, "methods")
        for method in route.methods
    }

    assert ("GET", "/") in routes
    assert ("POST", "/api/map/generate") in routes
    assert ("POST", "/api/lore/generate") in routes
    assert ("POST", "/api/npc/chat") in routes


def test_npc_chat_endpoint_returns_reply_and_uses_npc_settings(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_call_ollama(base_url: str, model: str, prompt: str, **kwargs) -> str:
        captured["base_url"] = base_url
        captured["model"] = model
        captured["prompt"] = prompt
        captured["npc_id"] = kwargs.get("npc_id")
        captured["log_npc_chat"] = kwargs.get("log_npc_chat")
        return json.dumps({"reply": "I can spare a little help, traveler."}, ensure_ascii=False)

    monkeypatch.setattr("app.lore._call_ollama", fake_call_ollama)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_NPC_MODEL", "npc-model")
    monkeypatch.setenv("OLLAMA_NPC_MAX_WORDS", "7")

    response = asyncio.run(
        create_npc_chat(
            NpcChatRequest.model_validate(
                {
                    "npcId": "npc:4:1",
                    "playerLine": "Can you help me?",
                    "worldLore": "A soft frontier links gardens, paths, and hill villages.",
                    "npc": {
                        "id": "npc:4:1",
                        "name": "Tobin",
                        "description": "A village tender who worries over the market flowers.",
                    },
                    "transcript": [["u", "Hello there"], ["n", "Welcome, traveler."]],
                }
            )
        )
    )

    payload = json.loads(response.body)
    assert payload == {"reply": "I can spare a little help, traveler."}
    assert captured["base_url"] == "http://ollama.test"
    assert captured["model"] == "npc-model"
    assert captured["npc_id"] == "npc:4:1"
    assert captured["log_npc_chat"] is True
    assert '"maxWords": 7' in captured["prompt"]
    assert '"name": "Tobin"' in captured["prompt"]


def test_npc_chat_endpoint_rejects_malformed_ollama_output(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.lore._call_ollama",
        lambda base_url, model, prompt, **kwargs: "not valid json at all",
    )
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_NPC_MODEL", "npc-model")
    monkeypatch.setenv("OLLAMA_NPC_MAX_WORDS", "12")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            create_npc_chat(
                NpcChatRequest.model_validate(
                    {
                        "npcId": "npc:3:1",
                        "playerLine": "Hello",
                        "worldLore": "A bright road crosses the frontier.",
                        "npc": {
                            "id": "npc:3:1",
                            "name": "Edda Pike",
                            "description": "A patient guide who knows the valley.",
                        },
                        "transcript": [],
                    }
                )
            )
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Ollama returned invalid JSON lore."


def test_npc_chat_endpoint_enforces_max_words(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.lore._call_ollama",
        lambda base_url, model, prompt, **kwargs: json.dumps(
            {
                "reply": "one two three four five six seven eight nine",
            },
            ensure_ascii=False,
        ),
    )
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_NPC_MODEL", "npc-model")
    monkeypatch.setenv("OLLAMA_NPC_MAX_WORDS", "5")

    response = asyncio.run(
        create_npc_chat(
            NpcChatRequest.model_validate(
                {
                    "npcId": "npc:7:4",
                    "playerLine": "Tell me more.",
                    "worldLore": "The roads are full of rumor and trade.",
                    "npc": {
                        "id": "npc:7:4",
                        "name": "Mira Fen",
                        "description": "A cheerful courier with news to spare.",
                    },
                    "transcript": [["u", "Hello"]],
                }
            )
        )
    )

    payload = json.loads(response.body)
    assert payload == {"reply": "one two three four five"}


def test_npc_chat_endpoint_requires_npc_settings(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_NPC_MODEL", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_NPC_MAX_WORDS", "5")
    monkeypatch.setattr("app.lore.ENV_FILES", ())

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            create_npc_chat(
                NpcChatRequest.model_validate(
                    {
                        "npcId": "npc:9:2",
                        "playerLine": "Hi",
                        "worldLore": "A quiet map waits beyond the road.",
                        "npc": {
                            "id": "npc:9:2",
                            "name": "Nell",
                            "description": "A watchful local.",
                        },
                        "transcript": [],
                    }
                )
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Missing required setting: OLLAMA_NPC_MODEL"


def test_npc_chat_logs_request_and_response_to_dedicated_jsonl(monkeypatch, tmp_path) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"response": '{"reply":"I can spare a little help, traveler."}'},
                ensure_ascii=False,
            ).encode("utf-8")

    monkeypatch.setenv("OLLAMA_LORE_LOG_ENABLED", "true")
    monkeypatch.setattr(lore, "BASE_DIR", tmp_path)
    monkeypatch.setattr(lore.request, "urlopen", lambda req, timeout=60: FakeResponse())

    reply = asyncio.run(
        lore.generate_npc_chat_reply(
            npc_id="npc:4:1",
            world_lore="A soft frontier links gardens, paths, and hill villages.",
            npc={
                "id": "npc:4:1",
                "name": "Tobin",
                "description": "A village tender who worries over the market flowers.",
            },
            transcript=[["u", "Hello there"], ["n", "Welcome, traveler."]],
            player_line="Can you help me?",
        )
    )

    assert reply == "I can spare a little help, traveler."
    records = [
        json.loads(line)
        for line in (tmp_path / "logs/ollama_npc_chat.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [record["event"] for record in records] == ["npc_chat_request", "npc_chat_response"]
    assert records[0]["npcId"] == "npc:4:1"
    assert records[0]["prompt"]
    assert records[0]["requestBody"]["prompt"] == records[0]["prompt"]
    assert records[1]["npcId"] == "npc:4:1"
    assert records[1]["rawHttpPayload"]
    assert records[1]["replyText"] == '{"reply":"I can spare a little help, traveler."}'
    for record in records:
        assert record["timestamp"].endswith("Z")
        datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
        assert isinstance(record.get("durationMs", 0), int) or record["event"] == "npc_chat_request"


def test_npc_chat_logs_errors_to_dedicated_jsonl(monkeypatch, tmp_path) -> None:
    def fake_urlopen(req, timeout=60):
        raise error.URLError("connection refused")

    monkeypatch.setenv("OLLAMA_LORE_LOG_ENABLED", "true")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_NPC_MODEL", "npc-model")
    monkeypatch.setenv("OLLAMA_NPC_MAX_WORDS", "12")
    monkeypatch.setattr(lore, "BASE_DIR", tmp_path)
    monkeypatch.setattr(lore.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(
            lore.generate_npc_chat_reply(
                npc_id="npc:3:1",
                world_lore="A bright road crosses the frontier.",
                npc={
                    "id": "npc:3:1",
                    "name": "Edda Pike",
                    "description": "A patient guide who knows the valley.",
                },
                transcript=[],
                player_line="Hello",
            )
        )

    assert exc_info.value.args[0] == "Could not reach Ollama at http://ollama.test/api/generate."
    records = [
        json.loads(line)
        for line in (tmp_path / "logs/ollama_npc_chat.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [record["event"] for record in records] == ["npc_chat_request", "npc_chat_error"]
    assert records[0]["npcId"] == "npc:3:1"
    assert records[1]["npcId"] == "npc:3:1"
    assert records[1]["errorType"] == "URLError"
    assert "connection refused" in records[1]["errorMessage"]


def test_lore_generation_does_not_write_to_npc_chat_jsonl(monkeypatch, tmp_path) -> None:
    world = [["🟩" for _ in range(6)] for _ in range(6)]
    for y in range(1, 3):
        for x in range(1, 3):
            world[y][x] = "🟪"
    npcs = [{"id": "npc:4:1", "x": 4, "y": 1, "tile": "🧑‍🌾"}]

    def fake_call_ollama(base_url, model, prompt, **kwargs):
        lore_kind = kwargs.get("lore_kind")
        entity_id = kwargs.get("entity_id")
        if lore_kind == "world":
            return json.dumps({"worldLore": "A patient frontier grows between fields and footpaths."}, ensure_ascii=False)
        if lore_kind == "village":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Moss Hollow",
                    "description": "A snug village where every porch faces the same market square.",
                },
                ensure_ascii=False,
            )
        if lore_kind == "npc":
            return json.dumps(
                {
                    "id": entity_id,
                    "name": "Toma Reed",
                    "description": "A farmer who knows every shortcut through the valley.",
                },
                ensure_ascii=False,
            )
        raise AssertionError(f"Unexpected lore kind: {lore_kind}")

    monkeypatch.setenv("OLLAMA_LORE_LOG_ENABLED", "true")
    monkeypatch.setattr(lore, "BASE_DIR", tmp_path)
    monkeypatch.setattr("app.lore._call_ollama", fake_call_ollama)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_GM_MODEL", "gm-model")

    asyncio.run(create_lore(LoreRequest.model_validate({"world": world, "npcs": npcs})))

    assert not (tmp_path / "logs/ollama_npc_chat.jsonl").exists()


def test_npc_chat_survives_jsonl_log_write_failure(monkeypatch, tmp_path) -> None:
    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"response": '{"reply":"I can spare a little help, traveler."}'},
                ensure_ascii=False,
            ).encode("utf-8")

    original_open = Path.open

    def fake_open(self: Path, *args, **kwargs):
        if self.name == "ollama_npc_chat.jsonl":
            raise OSError("disk full")
        return original_open(self, *args, **kwargs)

    monkeypatch.setenv("OLLAMA_LORE_LOG_ENABLED", "true")
    monkeypatch.setattr(lore, "BASE_DIR", tmp_path)
    monkeypatch.setattr(lore.request, "urlopen", lambda req, timeout=60: FakeResponse())
    monkeypatch.setattr(Path, "open", fake_open)

    reply = asyncio.run(
        lore.generate_npc_chat_reply(
            npc_id="npc:4:1",
            world_lore="A soft frontier links gardens, paths, and hill villages.",
            npc={
                "id": "npc:4:1",
                "name": "Tobin",
                "description": "A village tender who worries over the market flowers.",
            },
            transcript=[["u", "Hello there"], ["n", "Welcome, traveler."]],
            player_line="Can you help me?",
        )
    )

    assert reply == "I can spare a little help, traveler."
