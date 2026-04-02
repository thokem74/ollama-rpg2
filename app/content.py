from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TileCatalog:
    player: str
    ground: tuple[str, ...]
    trees: tuple[str, ...]
    plants: tuple[str, ...]
    buildings: tuple[str, ...]
    road: str
    village: str
    habitable: frozenset[str]
    blocked: frozenset[str]
    rough: frozenset[str]


ASSET_PATH = Path(__file__).resolve().parent.parent / "assets" / "unicode" / "emoji-rpg.txt"


def _extract_emoji(line: str) -> str:
    _, _, tail = line.partition("#")
    if not tail:
        raise ValueError(f"Line does not contain an emoji definition: {line!r}")

    parts = tail.strip().split(maxsplit=1)
    if not parts:
        raise ValueError(f"Could not parse emoji from line: {line!r}")
    return parts[0]


def load_tile_catalog(asset_path: Path = ASSET_PATH) -> TileCatalog:
    current_section: str | None = None
    player_tile: str | None = None
    ground_tiles: list[str] = []
    tree_tiles: list[str] = []
    plant_tiles: list[str] = []
    building_tiles: list[str] = []

    for raw_line in asset_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("# "):
            current_section = line[2:].strip()
            continue

        if line.startswith("#"):
            continue

        if current_section == "Player" and player_tile is None:
            player_tile = _extract_emoji(line)
        elif current_section == "Ground":
            ground_tiles.append(_extract_emoji(line))
        elif current_section == "Trees":
            tree_tiles.append(_extract_emoji(line))
        elif current_section == "Plants":
            plant_tiles.append(_extract_emoji(line))
        elif current_section == "Buildings":
            building_tiles.append(_extract_emoji(line))

    if player_tile is None:
        raise ValueError("No player tile found in emoji-rpg.txt")
    if not ground_tiles:
        raise ValueError("No ground tiles found in emoji-rpg.txt")
    if not tree_tiles:
        raise ValueError("No tree tiles found in emoji-rpg.txt")
    if not plant_tiles:
        raise ValueError("No plant tiles found in emoji-rpg.txt")
    if not building_tiles:
        raise ValueError("No building tiles found in emoji-rpg.txt")

    lookup = {tile: tile for tile in ground_tiles}

    required = {
        "forest": "🟢",
        "road": "🟥",
        "village": "🟪",
        "grass": "🟩",
        "soil": "🟫",
    }
    missing = [name for name, tile in required.items() if tile not in lookup]
    if missing:
        raise ValueError(f"Missing required terrain tiles: {', '.join(missing)}")

    return TileCatalog(
        player=player_tile,
        ground=tuple(ground_tiles),
        trees=tuple(tree_tiles),
        plants=tuple(plant_tiles),
        buildings=tuple(building_tiles),
        road=lookup["🟥"],
        village=lookup["🟪"],
        habitable=frozenset(tile for tile in (lookup["🟩"], lookup.get("🟨"), lookup["🟫"]) if tile is not None),
        blocked=frozenset(tile for tile in (lookup.get("🟦"),) if tile is not None),
        rough=frozenset(tile for tile in (lookup.get("⬛"), lookup.get("⬜")) if tile is not None),
    )
