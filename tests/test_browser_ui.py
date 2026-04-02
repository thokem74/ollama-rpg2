import json
from pathlib import Path

from playwright.sync_api import sync_playwright


STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"
STYLES_FILE = STATIC_DIR / "styles.css"
SCRIPT_FILE = STATIC_DIR / "app.js"

HTML_SHELL = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ollama-rpg2</title>
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <main class="app-shell">
      <section class="hero">
        <p class="eyebrow">World Seedling</p>
        <h1>Emoji Frontier</h1>
        <p class="intro">
          Generate a 128x128 world, then move the player with WASD while the
          camera follows across a 30x22 viewport.
        </p>
        <div class="controls">
          <button id="generate-button" type="button">Generate Map</button>
          <span id="status">Ready to generate a world.</span>
        </div>
      </section>

      <section class="viewport-panel">
        <div class="viewport-header">
          <div>
            <h2>Viewport</h2>
            <p>30 x 22 tiles</p>
          </div>
          <div id="player-position">Player: -, -</div>
        </div>
        <canvas
          id="map-canvas"
          width="1020"
          height="748"
          aria-label="Generated map viewport"
        ></canvas>
      </section>
    </main>
    <script type="module" src="/static/app.js"></script>
  </body>
</html>
"""

MOCK_WORLD = [["🟩" for _ in range(128)] for _ in range(128)]
MOCK_WORLD[10][11] = "🌲"
MOCK_PLAYER = {"x": 10, "y": 10, "tile": "🙂"}
MOCK_NPCS = [{"x": 10, "y": 11, "tile": "🧑‍🦱"}]
MOCK_COLLISION = {
    "tiles": {
        "trees": ["🌲"],
        "plants": ["🌷"],
        "buildings": ["🏠"],
    }
}
MOCK_PAYLOAD = {
    "world": MOCK_WORLD,
    "player": MOCK_PLAYER,
    "npcs": MOCK_NPCS,
    "collision": MOCK_COLLISION,
    "viewport": {"width": 30, "height": 22},
}


def _install_app_routes(page, request_log: list[str]) -> None:
    def fulfill_app(route) -> None:
        url = route.request.url
        if url == "http://ui.test/":
            route.fulfill(status=200, content_type="text/html", body=HTML_SHELL)
        elif url == "http://ui.test/static/styles.css":
            route.fulfill(status=200, content_type="text/css", body=STYLES_FILE.read_text())
        elif url == "http://ui.test/static/app.js":
            route.fulfill(
                status=200,
                content_type="application/javascript",
                body=SCRIPT_FILE.read_text(),
            )
        elif url == "http://ui.test/api/map/generate":
            request_log.append(url)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(MOCK_PAYLOAD, ensure_ascii=False),
            )
        else:
            route.fulfill(status=404, body="not found")

    page.route("http://ui.test/**", fulfill_app)


def _parse_position(label: str) -> tuple[int, int]:
    prefix = "Player: "
    assert label.startswith(prefix), label
    x_text, y_text = label[len(prefix) :].split(", ")
    return int(x_text), int(y_text)


def test_browser_persists_map_and_player_state_after_reload() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        request_log: list[str] = []
        _install_app_routes(page, request_log)
        page.goto("http://ui.test/", wait_until="load")

        assert page.locator("h1").text_content() == "Emoji Frontier"
        assert page.locator("#status").text_content() == "Ready to generate a world."
        assert page.locator("#player-position").text_content() == "Player: -, -"

        page.locator("#generate-button").click()
        page.wait_for_function(
            """
            () => document.querySelector("#status")?.textContent ===
              "World ready. Use WASD to move."
            """
        )
        assert len(request_log) == 1

        player_label = page.locator("#player-position").text_content()
        assert player_label is not None
        start_x, start_y = _parse_position(player_label)

        page.keyboard.press("d")
        page.wait_for_function(
            """
            () => document.querySelector("#status")?.textContent === "Blocked by obstacle."
            """
        )
        blocked_tree_label = page.locator("#player-position").text_content()
        assert blocked_tree_label is not None
        assert _parse_position(blocked_tree_label) == (start_x, start_y)

        page.keyboard.press("s")
        page.wait_for_function(
            """
            () => document.querySelector("#status")?.textContent === "Blocked by obstacle."
            """
        )
        blocked_npc_label = page.locator("#player-position").text_content()
        assert blocked_npc_label is not None
        assert _parse_position(blocked_npc_label) == (start_x, start_y)

        page.keyboard.press("a")
        page.wait_for_function("""() => document.querySelector("#player-position")?.textContent === "Player: 9, 10" """)

        moved_label = page.locator("#player-position").text_content()
        assert moved_label is not None
        end_x, end_y = _parse_position(moved_label)

        assert (start_x, start_y) == (MOCK_PLAYER["x"], MOCK_PLAYER["y"])
        assert (end_x, end_y) == (MOCK_PLAYER["x"] - 1, MOCK_PLAYER["y"])
        assert page.locator("#status").text_content() == "World ready. Use WASD to move."

        page.reload(wait_until="load")
        page.wait_for_function(
            """
            () => document.querySelector("#status")?.textContent ===
              "Restored saved world. Use WASD to move."
            """
        )
        restored_label = page.locator("#player-position").text_content()
        assert restored_label is not None
        assert _parse_position(restored_label) == (MOCK_PLAYER["x"] - 1, MOCK_PLAYER["y"])
        assert len(request_log) == 1

        page.keyboard.press("d")
        page.wait_for_function("""() => document.querySelector("#player-position")?.textContent === "Player: 10, 10" """)
        page.keyboard.press("d")
        page.wait_for_function(
            """
            () => document.querySelector("#status")?.textContent === "Blocked by obstacle."
            """
        )
        blocked_after_restore_label = page.locator("#player-position").text_content()
        assert blocked_after_restore_label is not None
        assert _parse_position(blocked_after_restore_label) == (MOCK_PLAYER["x"], MOCK_PLAYER["y"])

        page.reload(wait_until="load")
        page.wait_for_function(
            """
            () => document.querySelector("#status")?.textContent ===
              "Restored saved world. Use WASD to move."
            """
        )
        reloaded_after_block_label = page.locator("#player-position").text_content()
        assert reloaded_after_block_label is not None
        assert _parse_position(reloaded_after_block_label) == (MOCK_PLAYER["x"], MOCK_PLAYER["y"])
        assert len(request_log) == 1

        browser.close()


def test_browser_ignores_invalid_saved_world() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        request_log: list[str] = []
        _install_app_routes(page, request_log)
        page.add_init_script(
            """
            window.localStorage.setItem("ollama-rpg2:map-state:v1", "{broken");
            """
        )
        page.goto("http://ui.test/", wait_until="load")

        assert page.locator("#status").text_content() == "Ready to generate a world."
        assert page.locator("#player-position").text_content() == "Player: -, -"
        assert len(request_log) == 0

        page.locator("#generate-button").click()
        page.wait_for_function(
            """
            () => document.querySelector("#status")?.textContent ===
              "World ready. Use WASD to move."
            """
        )
        assert len(request_log) == 1

        browser.close()
