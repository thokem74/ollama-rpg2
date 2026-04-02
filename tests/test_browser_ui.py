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
          camera follows across a 15x11 viewport.
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
            <p>15 x 11 tiles</p>
          </div>
          <div id="player-position">Player: -, -</div>
        </div>
        <canvas
          id="map-canvas"
          width="720"
          height="528"
          aria-label="Generated map viewport"
        ></canvas>
      </section>
    </main>
    <script type="module" src="/static/app.js"></script>
  </body>
</html>
"""

MOCK_WORLD = [["🟩" for _ in range(128)] for _ in range(128)]
MOCK_PLAYER = {"x": 10, "y": 10, "tile": "🙂"}


def _parse_position(label: str) -> tuple[int, int]:
    prefix = "Player: "
    assert label.startswith(prefix), label
    x_text, y_text = label[len(prefix) :].split(", ")
    return int(x_text), int(y_text)


def test_browser_can_generate_map_and_move_player() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
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
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "world": MOCK_WORLD,
                            "player": MOCK_PLAYER,
                            "viewport": {"width": 15, "height": 11},
                        },
                        ensure_ascii=False,
                    ),
                )
            else:
                route.fulfill(status=404, body="not found")

        page.route("http://ui.test/**", fulfill_app)
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

        player_label = page.locator("#player-position").text_content()
        assert player_label is not None
        start_x, start_y = _parse_position(player_label)

        page.keyboard.press("d")
        page.wait_for_function(
            """
            previous => document.querySelector("#player-position")?.textContent !== previous
            """,
            arg=player_label,
        )

        moved_label = page.locator("#player-position").text_content()
        assert moved_label is not None
        end_x, end_y = _parse_position(moved_label)

        assert (start_x, start_y) == (MOCK_PLAYER["x"], MOCK_PLAYER["y"])
        assert (end_x, end_y) == (MOCK_PLAYER["x"] + 1, MOCK_PLAYER["y"])

        browser.close()
