from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TileCatalog:
    player: str
    ground: tuple[str, ...]
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

    if player_tile is None:
        raise ValueError("No player tile found in emoji-rpg.txt")
    if not ground_tiles:
        raise ValueError("No ground tiles found in emoji-rpg.txt")

    lookup = {tile: tile for tile in ground_tiles}

    required = {
        "road": "🟥",
        "village": "🟪",
        "grass": "🟩",
        "sand": "🟨",
        "soil": "🟫",
        "rock": "⬛",
    }
    missing = [name for name, tile in required.items() if tile not in lookup]
    if missing:
        raise ValueError(f"Missing required terrain tiles: {', '.join(missing)}")

    return TileCatalog(
        player=player_tile,
        ground=tuple(ground_tiles),
        road=lookup["🟥"],
        village=lookup["🟪"],
        habitable=frozenset((lookup["🟩"], lookup["🟨"], lookup["🟫"])),
        blocked=frozenset(tile for tile in (lookup.get("🟦"),) if tile is not None),
        rough=frozenset(tile for tile in (lookup["⬛"], lookup.get("⬜")) if tile is not None),
    )
