import asyncio
import json

from app.content import load_tile_catalog
from app.main import app, create_map
from app.mapgen import VIEWPORT_HEIGHT, VIEWPORT_WIDTH, WORLD_HEIGHT, WORLD_WIDTH


def test_tile_catalog_loads_expected_sections() -> None:
    catalog = load_tile_catalog()

    assert catalog.player == "🙂"
    assert catalog.ground == ("🟥", "🟨", "🟩", "🟦", "🟫", "⬛", "⬜")


def test_generate_map_response_shape_and_tiles() -> None:
    response = asyncio.run(create_map())
    assert response.media_type == "application/json"

    payload = json.loads(response.body)
    world = payload["world"]
    player = payload["player"]
    viewport = payload["viewport"]

    assert len(world) == WORLD_HEIGHT
    assert all(len(row) == WORLD_WIDTH for row in world)

    allowed_tiles = set(load_tile_catalog().ground)
    assert all(tile in allowed_tiles for row in world for tile in row)

    assert player["tile"] == "🙂"
    assert 0 <= player["x"] < WORLD_WIDTH
    assert 0 <= player["y"] < WORLD_HEIGHT
    assert world[player["y"]][player["x"]] != "🟦"

    assert viewport == {"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}


def test_app_routes_include_ui_and_generation_endpoint() -> None:
    routes = {
        (method, route.path)
        for route in app.routes
        if hasattr(route, "methods")
        for method in route.methods
    }

    assert ("GET", "/") in routes
    assert ("POST", "/api/map/generate") in routes
