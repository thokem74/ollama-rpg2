import asyncio
import json
from collections import deque

from app.content import load_tile_catalog
from app.main import app, create_map
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
    viewport = payload["viewport"]
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

    assert viewport == {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}

    settlement_tiles = {catalog.village, *catalog.buildings}
    village_clusters = _find_clusters(world, settlement_tiles)
    assert 4 <= len(village_clusters) <= MAX_VILLAGES
    assert all(100 <= len(cluster) <= 400 for cluster in village_clusters)
    building_positions = [
        (x, y)
        for y, row in enumerate(world)
        for x, tile in enumerate(row)
        if tile in catalog.buildings
    ]
    assert building_positions
    for index, (x, y) in enumerate(building_positions):
        for other_x, other_y in building_positions[index + 1 :]:
            assert max(abs(x - other_x), abs(y - other_y)) >= 3

    road_tiles = sum(tile == catalog.road for row in world for tile in row)
    assert road_tiles > 0

    centers = [_cluster_center(cluster) for cluster in village_clusters]
    for index, center in enumerate(centers):
        for other in centers[index + 1 :]:
            dx = center[0] - other[0]
            dy = center[1] - other[1]
            assert (dx * dx) + (dy * dy) >= (MIN_VILLAGE_SPACING - 4) ** 2


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


def test_app_routes_include_ui_and_generation_endpoint() -> None:
    routes = {
        (method, route.path)
        for route in app.routes
        if hasattr(route, "methods")
        for method in route.methods
    }

    assert ("GET", "/") in routes
    assert ("POST", "/api/map/generate") in routes
