from __future__ import annotations

import heapq
from dataclasses import dataclass
from random import Random

from app.content import TileCatalog

WORLD_WIDTH = 128
WORLD_HEIGHT = 128
VIEWPORT_WIDTH = 30
VIEWPORT_HEIGHT = 22
DEFAULT_WATER_TILE = "🟦"
MIN_VILLAGES = 4
MAX_VILLAGES = 8
MIN_VILLAGE_SPACING = 18
MIN_VILLAGE_SIZE = 10
MAX_VILLAGE_SIZE = 20
BUILDING_MIN_GAP = 3
BUILDING_DENSITY = 0.035
MIN_TERRAIN_SPOT_SIZE = 10
MAX_TERRAIN_SPOT_SIZE = 30


@dataclass(frozen=True)
class PlayerSpawn:
    x: int
    y: int
    tile: str


@dataclass(frozen=True)
class GeneratedMap:
    world: list[list[str]]
    player: PlayerSpawn


@dataclass(frozen=True)
class Village:
    center_x: int
    center_y: int
    width: int
    height: int


def _build_ground_lookup(ground_tiles: tuple[str, ...]) -> dict[str, str]:
    ordered = ("🟢", "🟨", "🟩", "🟫", "⬛")
    lookup = {tile: tile for tile in ground_tiles}
    mapped = {tile: lookup[tile] for tile in ordered if tile in lookup}
    if len(mapped) != len(ground_tiles):
        for tile in ground_tiles:
            mapped.setdefault(tile, tile)
    return mapped


def _terrain_palette(catalog: TileCatalog) -> tuple[str, str, str]:
    lookup = _build_ground_lookup(catalog.ground)
    return (
        lookup["🟩"],
        lookup["🟫"],
        lookup["🟢"],
    )


def _stamp_terrain_spot(
    world: list[list[str]],
    center_x: int,
    center_y: int,
    width: int,
    height: int,
    tile: str,
    rng: Random,
) -> None:
    half_width = width // 2
    half_height = height // 2
    left = max(0, center_x - half_width)
    right = min(WORLD_WIDTH - 1, center_x + width - half_width - 1)
    top = max(0, center_y - half_height)
    bottom = min(WORLD_HEIGHT - 1, center_y + height - half_height - 1)

    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            # Keep spots soft-edged rather than perfectly rectangular.
            edge_bias = (
                x in (left, right)
                or y in (top, bottom)
                or x in (left + 1, right - 1)
                or y in (top + 1, bottom - 1)
            )
            if edge_bias and rng.random() < 0.22:
                continue
            world[y][x] = tile


def _spot_bounds(center_x: int, center_y: int, width: int, height: int) -> tuple[int, int, int, int]:
    half_width = width // 2
    half_height = height // 2
    return (
        max(0, center_x - half_width),
        min(WORLD_WIDTH - 1, center_x + width - half_width - 1),
        max(0, center_y - half_height),
        min(WORLD_HEIGHT - 1, center_y + height - half_height - 1),
    )


def _spot_overlaps_existing(
    occupied: list[tuple[int, int, int, int]], candidate: tuple[int, int, int, int]
) -> bool:
    left, right, top, bottom = candidate
    return any(
        not (right < other_left or other_right < left or bottom < other_top or other_bottom < top)
        for other_left, other_right, other_top, other_bottom in occupied
    )


def _generate_base_world(catalog: TileCatalog, rng: Random) -> list[list[str]]:
    grass_tile, soil_tile, forest_tile = _terrain_palette(catalog)
    world = [[soil_tile for _ in range(WORLD_WIDTH)] for _ in range(WORLD_HEIGHT)]

    spot_plan = (
        (grass_tile, rng.randint(4, 6)),
        (forest_tile, rng.randint(4, 6)),
    )
    occupied_spots: list[tuple[int, int, int, int]] = []
    for tile, count in spot_plan:
        placed = 0
        attempts = 0
        while placed < count and attempts < 200:
            width = rng.randint(MIN_TERRAIN_SPOT_SIZE, MAX_TERRAIN_SPOT_SIZE)
            height = rng.randint(MIN_TERRAIN_SPOT_SIZE, MAX_TERRAIN_SPOT_SIZE)
            half_width = width // 2
            half_height = height // 2
            center_x = rng.randint(half_width, WORLD_WIDTH - (width - half_width))
            center_y = rng.randint(half_height, WORLD_HEIGHT - (height - half_height))
            bounds = _spot_bounds(center_x, center_y, width, height)
            if _spot_overlaps_existing(occupied_spots, bounds):
                attempts += 1
                continue
            _stamp_terrain_spot(world, center_x, center_y, width, height, tile, rng)
            occupied_spots.append(bounds)
            placed += 1
            attempts += 1

    return world


def _in_bounds(x: int, y: int) -> bool:
    return 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT


def _distance_sq(a: tuple[int, int], b: tuple[int, int]) -> int:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return (dx * dx) + (dy * dy)


def _is_walkable(tile: str, catalog: TileCatalog) -> bool:
    return tile not in catalog.blocked


def _is_habitable(tile: str, catalog: TileCatalog) -> bool:
    return tile in catalog.habitable


def _village_site_ok(
    world: list[list[str]],
    x: int,
    y: int,
    width: int,
    height: int,
    catalog: TileCatalog,
) -> bool:
    if world[y][x] not in catalog.habitable:
        return False

    habitable_tiles = 0
    left, right, top, bottom = _village_bounds(Village(x, y, width, height))
    for py in range(top, bottom + 1):
        for px in range(left, right + 1):
            if not _in_bounds(px, py):
                return False
            tile = world[py][px]
            if tile in catalog.blocked:
                return False
            if tile in catalog.habitable:
                habitable_tiles += 1
    return habitable_tiles >= int(width * height * 0.65)


def _village_bounds(village: Village) -> tuple[int, int, int, int]:
    half_width = village.width // 2
    half_height = village.height // 2
    return (
        village.center_x - half_width,
        village.center_x + village.width - half_width - 1,
        village.center_y - half_height,
        village.center_y + village.height - half_height - 1,
    )


def _village_rectangles_overlap(a: Village, b: Village) -> bool:
    a_left, a_right, a_top, a_bottom = _village_bounds(a)
    b_left, b_right, b_top, b_bottom = _village_bounds(b)
    return not (
        a_right < b_left
        or b_right < a_left
        or a_bottom < b_top
        or b_bottom < a_top
    )


def _can_place_village(candidate: Village, villages: list[Village], min_spacing: int) -> bool:
    return all(
        _distance_sq((candidate.center_x, candidate.center_y), (village.center_x, village.center_y))
        >= min_spacing * min_spacing
        and not _village_rectangles_overlap(candidate, village)
        for village in villages
    )


def _stamp_village(world: list[list[str]], village: Village, catalog: TileCatalog) -> None:
    left, right, top, bottom = _village_bounds(village)
    for y in range(top, bottom + 1):
        for x in range(left, right + 1):
            if world[y][x] not in catalog.blocked:
                world[y][x] = catalog.village


def _can_place_building(
    x: int, y: int, placed: list[tuple[int, int]]
) -> bool:
    return all(
        max(abs(x - other_x), abs(y - other_y)) >= BUILDING_MIN_GAP
        for other_x, other_y in placed
    )


def _stamp_buildings(
    world: list[list[str]], village: Village, catalog: TileCatalog, rng: Random
) -> None:
    left, right, top, bottom = _village_bounds(village)
    candidates = [
        (x, y)
        for y in range(top + 1, bottom)
        for x in range(left + 1, right)
        if world[y][x] == catalog.village
    ]
    rng.shuffle(candidates)

    target_count = max(1, int(village.width * village.height * BUILDING_DENSITY))
    placed: list[tuple[int, int]] = []

    for x, y in candidates:
        if _can_place_building(x, y, placed):
            world[y][x] = rng.choice(catalog.buildings)
            placed.append((x, y))
            if len(placed) >= target_count:
                break


def _select_village_centers(
    world: list[list[str]], catalog: TileCatalog, rng: Random
) -> list[Village]:
    target_count = rng.randint(MIN_VILLAGES, MAX_VILLAGES)
    villages: list[Village] = []
    min_spacing = MIN_VILLAGE_SPACING

    while min_spacing >= 6 and len(villages) < MIN_VILLAGES:
        villages.clear()
        attempts = 0
        max_attempts = 4000
        while attempts < max_attempts and len(villages) < target_count:
            width = rng.randint(MIN_VILLAGE_SIZE, MAX_VILLAGE_SIZE)
            height = rng.randint(MIN_VILLAGE_SIZE, MAX_VILLAGE_SIZE)
            half_width = width // 2
            half_height = height // 2
            x = rng.randint(half_width, WORLD_WIDTH - (width - half_width))
            y = rng.randint(half_height, WORLD_HEIGHT - (height - half_height))
            candidate = Village(x, y, width, height)
            if _village_site_ok(world, x, y, width, height, catalog) and _can_place_village(
                candidate, villages, min_spacing
            ):
                villages.append(candidate)
            attempts += 1
        min_spacing -= 2

    if len(villages) < MIN_VILLAGES:
        attempts = 0
        while attempts < 10000 and len(villages) < MIN_VILLAGES:
            width = rng.randint(MIN_VILLAGE_SIZE, MAX_VILLAGE_SIZE)
            height = rng.randint(MIN_VILLAGE_SIZE, MAX_VILLAGE_SIZE)
            half_width = width // 2
            half_height = height // 2
            x = rng.randint(half_width, WORLD_WIDTH - (width - half_width))
            y = rng.randint(half_height, WORLD_HEIGHT - (height - half_height))
            candidate = Village(x, y, width, height)
            if _village_site_ok(world, x, y, width, height, catalog) and _can_place_village(
                candidate, villages, 6
            ):
                villages.append(candidate)
            attempts += 1

    return villages[:target_count]


def _build_village_connections(villages: list[Village]) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    if len(villages) < 2:
        return []

    connected = [villages[0]]
    remaining = villages[1:]
    edges: list[tuple[tuple[int, int], tuple[int, int]]] = []

    while remaining:
        best_from = connected[0]
        best_to = remaining[0]
        best_distance = _distance_sq(
            (best_from.center_x, best_from.center_y),
            (best_to.center_x, best_to.center_y),
        )
        for start in connected:
            for end in remaining:
                distance = _distance_sq((start.center_x, start.center_y), (end.center_x, end.center_y))
                if distance < best_distance:
                    best_from = start
                    best_to = end
                    best_distance = distance
        edges.append(((best_from.center_x, best_from.center_y), (best_to.center_x, best_to.center_y)))
        connected.append(best_to)
        remaining.remove(best_to)

    return edges


def _terrain_cost(tile: str, catalog: TileCatalog) -> int:
    if tile == catalog.road:
        return 1
    if tile == catalog.village:
        return 2
    if tile in catalog.habitable:
        return 3
    if tile in catalog.rough:
        return 10
    return 6


def _random_cost(x: int, y: int, seed: int) -> int:
    salt = ((x * 92821) ^ (y * 68917) ^ seed) & 0xFFFFFFFF
    return Random(salt).randint(0, 3)


def _heuristic(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _carve_road(
    world: list[list[str]],
    start: tuple[int, int],
    goal: tuple[int, int],
    catalog: TileCatalog,
    seed: int,
) -> None:
    frontier: list[tuple[int, int, tuple[int, int]]] = []
    heapq.heappush(frontier, (0, 0, start))
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    cost_so_far: dict[tuple[int, int], int] = {start: 0}

    while frontier:
        _, _, current = heapq.heappop(frontier)
        if current == goal:
            break

        cx, cy = current
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx = cx + dx
            ny = cy + dy
            if not _in_bounds(nx, ny):
                continue
            tile = world[ny][nx]
            if tile in catalog.blocked:
                continue

            next_pos = (nx, ny)
            new_cost = cost_so_far[current] + _terrain_cost(tile, catalog) + _random_cost(nx, ny, seed)
            if next_pos not in cost_so_far or new_cost < cost_so_far[next_pos]:
                cost_so_far[next_pos] = new_cost
                priority = new_cost + _heuristic(next_pos, goal)
                heapq.heappush(frontier, (priority, _random_cost(nx, ny, seed + 17), next_pos))
                came_from[next_pos] = current

    current = goal
    if current not in came_from:
        return

    while current is not None:
        x, y = current
        if world[y][x] != catalog.village:
            world[y][x] = catalog.road
        current = came_from[current]


def _find_spawn(world: list[list[str]], player_tile: str, catalog: TileCatalog) -> PlayerSpawn:
    center_x = WORLD_WIDTH // 2
    center_y = WORLD_HEIGHT // 2

    for radius in range(max(WORLD_WIDTH, WORLD_HEIGHT)):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                x = center_x + dx
                y = center_y + dy
                if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT:
                    if _is_walkable(world[y][x], catalog):
                        return PlayerSpawn(x=x, y=y, tile=player_tile)

    return PlayerSpawn(x=center_x, y=center_y, tile=player_tile)


def generate_map(catalog: TileCatalog) -> GeneratedMap:
    seed = Random().randint(0, 2**31 - 1)
    rng = Random(seed)
    world = _generate_base_world(catalog, rng)

    villages = _select_village_centers(world, catalog, rng)
    for village in villages:
        _stamp_village(world, village, catalog)
        _stamp_buildings(world, village, catalog, rng)

    for index, (start, end) in enumerate(_build_village_connections(villages)):
        _carve_road(world, start, end, catalog, seed + index * 101)

    player = _find_spawn(world, catalog.player, catalog)
    return GeneratedMap(world=world, player=player)
