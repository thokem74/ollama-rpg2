from __future__ import annotations

from dataclasses import dataclass
from random import Random

from app.content import TileCatalog

WORLD_WIDTH = 128
WORLD_HEIGHT = 128
VIEWPORT_WIDTH = 15
VIEWPORT_HEIGHT = 11
DEFAULT_WATER_TILE = "🟦"


@dataclass(frozen=True)
class PlayerSpawn:
    x: int
    y: int
    tile: str


@dataclass(frozen=True)
class GeneratedMap:
    world: list[list[str]]
    player: PlayerSpawn


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _value_noise(x: float, y: float, seed: int, step: int, salt: int) -> float:
    x0 = int(x // step)
    y0 = int(y // step)
    tx = (x % step) / step
    ty = (y % step) / step

    def corner(cx: int, cy: int) -> float:
        corner_seed = ((cx * 73856093) ^ (cy * 19349663) ^ seed ^ salt) & 0xFFFFFFFF
        corner_rng = Random(corner_seed)
        return corner_rng.random()

    c00 = corner(x0, y0)
    c10 = corner(x0 + 1, y0)
    c01 = corner(x0, y0 + 1)
    c11 = corner(x0 + 1, y0 + 1)

    top = _lerp(c00, c10, tx)
    bottom = _lerp(c01, c11, tx)
    return _lerp(top, bottom, ty)


def _blended_noise(x: int, y: int, seed: int) -> float:
    large = _value_noise(x, y, seed, step=32, salt=101)
    medium = _value_noise(x + 11, y + 17, seed, step=16, salt=211)
    detail = _value_noise(x + 23, y + 29, seed, step=8, salt=307)
    return (large * 0.55) + (medium * 0.3) + (detail * 0.15)


def _build_ground_lookup(ground_tiles: tuple[str, ...]) -> dict[str, str]:
    ordered = ("🟥", "🟨", "🟩", "🟦", "🟫", "⬛", "⬜")
    lookup = {tile: tile for tile in ground_tiles}
    mapped = {tile: lookup[tile] for tile in ordered if tile in lookup}
    if len(mapped) != len(ground_tiles):
        for tile in ground_tiles:
            mapped.setdefault(tile, tile)
    return mapped


def _pick_tile(value: float, ground_tiles: tuple[str, ...]) -> str:
    lookup = _build_ground_lookup(ground_tiles)
    thresholds = (
        (0.08, lookup.get("🟦", ground_tiles[0])),
        (0.14, lookup.get("⬜", ground_tiles[0])),
        (0.25, lookup.get("⬛", ground_tiles[0])),
        (0.37, lookup.get("🟥", ground_tiles[0])),
        (0.49, lookup.get("🟨", ground_tiles[0])),
        (0.73, lookup.get("🟫", ground_tiles[0])),
    )
    for threshold, tile in thresholds:
        if value < threshold:
            return tile
    return lookup.get("🟩", ground_tiles[-1])


def _find_spawn(world: list[list[str]], player_tile: str) -> PlayerSpawn:
    center_x = WORLD_WIDTH // 2
    center_y = WORLD_HEIGHT // 2

    for radius in range(max(WORLD_WIDTH, WORLD_HEIGHT)):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                x = center_x + dx
                y = center_y + dy
                if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT:
                    if world[y][x] != DEFAULT_WATER_TILE:
                        return PlayerSpawn(x=x, y=y, tile=player_tile)

    return PlayerSpawn(x=center_x, y=center_y, tile=player_tile)


def generate_map(catalog: TileCatalog) -> GeneratedMap:
    seed = Random().randint(0, 2**31 - 1)
    world: list[list[str]] = []

    for y in range(WORLD_HEIGHT):
        row: list[str] = []
        for x in range(WORLD_WIDTH):
            noise_value = _blended_noise(x, y, seed)
            row.append(_pick_tile(noise_value, catalog.ground))
        world.append(row)

    player = _find_spawn(world, catalog.player)
    return GeneratedMap(world=world, player=player)
