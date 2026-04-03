import asyncio
import json
from collections import deque
from datetime import datetime
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

    monkeypatch.setattr(
        "app.lore._call_ollama",
        lambda base_url, model, prompt, **kwargs: json.dumps(
            {
                "worldLore": "A patient frontier grows between fields and footpaths.",
                "villages": [
                    {
                        "id": "village:1:1:2:2",
                        "name": "Moss Hollow",
                        "description": "A snug village where every porch faces the same market square.",
                    }
                ],
                "npcs": [
                    {
                        "id": "npc:4:1",
                        "name": "Toma Reed",
                        "description": "A farmer who knows every shortcut through the valley.",
                    }
                ],
            },
            ensure_ascii=False,
        ),
    )
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


def test_lore_generate_endpoint_rejects_malformed_ollama_output(monkeypatch) -> None:
    world = [["🟩" for _ in range(4)] for _ in range(4)]
    world[1][1] = "🟪"
    npcs = [{"id": "npc:2:1", "x": 2, "y": 1, "tile": "🧑‍🌾"}]

    monkeypatch.setattr(
        "app.lore._call_ollama",
        lambda base_url, model, prompt, **kwargs: "not valid json at all",
    )
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_GM_MODEL", "gm-model")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(create_lore(LoreRequest.model_validate({"world": world, "npcs": npcs})))

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Ollama returned invalid JSON lore."


def test_lore_generate_endpoint_repairs_common_ollama_formatting_and_id_issues(monkeypatch) -> None:
    world = [["🟩" for _ in range(5)] for _ in range(5)]
    world[1][1] = "🟪"
    world[1][2] = "🟪"
    npcs = [{"id": "npc:3:1", "x": 3, "y": 1, "tile": "🧑‍🌾"}]

    monkeypatch.setattr(
        "app.lore._call_ollama",
        lambda base_url, model, prompt, **kwargs: (
            'Here is your lore:\n'
            + json.dumps(
                {
                    "worldLore": "A windy trade path ties the settlement to the open grasslands.",
                    "villages": [
                        {
                            "name": "Bramble Post",
                            "description": "A tiny waypoint where caravans rest before dusk.",
                        }
                    ],
                    "npcs": [
                        {
                            "id": "wrong-id",
                            "name": "Edda Pike",
                            "description": "A patient guide who knows the safest roadside camps.",
                        }
                    ],
                },
                ensure_ascii=False,
            )
        ),
    )
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test")
    monkeypatch.setenv("OLLAMA_GM_MODEL", "gm-model")

    response = asyncio.run(create_lore(LoreRequest.model_validate({"world": world, "npcs": npcs})))
    payload = json.loads(response.body)

    assert payload["worldLore"] == "A windy trade path ties the settlement to the open grasslands."
    assert payload["villages"][0]["id"] == "village:1:1:2:1"
    assert payload["villages"][0]["name"] == "Bramble Post"
    assert payload["npcs"][0]["id"] == "npc:3:1"
    assert payload["npcs"][0]["name"] == "Edda Pike"


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
    text = lore._call_ollama("http://ollama.test", "gm-model", prompt, log_lore=True)

    assert '"worldLore":"A bright path crosses the valley."' in text

    records = [
        json.loads(line)
        for line in (tmp_path / "custom-lore.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [record["event"] for record in records] == ["lore_request", "lore_response"]
    assert records[0]["endpoint"] == "http://ollama.test/api/generate"
    assert records[0]["model"] == "gm-model"
    assert records[0]["prompt"] == prompt
    assert records[0]["requestBody"]["prompt"] == prompt
    assert records[1]["rawHttpPayload"]
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
        lore._call_ollama("http://ollama.test", "gm-model", "Prompt", log_lore=True)

    assert exc_info.value.args[0] == "Could not reach Ollama at http://ollama.test/api/generate."

    records = [json.loads(line) for line in (tmp_path / "errors.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [record["event"] for record in records] == ["lore_request", "lore_error"]
    assert records[1]["errorType"] == "URLError"
    assert "connection refused" in records[1]["errorMessage"]
    assert isinstance(records[1]["durationMs"], int)


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

    def fake_call_ollama(base_url: str, model: str, prompt: str) -> str:
        captured["base_url"] = base_url
        captured["model"] = model
        captured["prompt"] = prompt
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
    assert '"maxWords": 7' in captured["prompt"]
    assert '"name": "Tobin"' in captured["prompt"]


def test_npc_chat_endpoint_rejects_malformed_ollama_output(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.lore._call_ollama",
        lambda base_url, model, prompt: "not valid json at all",
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
        lambda base_url, model, prompt: json.dumps(
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
