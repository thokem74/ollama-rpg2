import json
from pathlib import Path

import pytest
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
          <button id="generate-lore-button" type="button">Generate Lore</button>
          <button id="reset-button" type="button">Reset</button>
          <span id="status">Ready to generate a world.</span>
        </div>
      </section>

      <section class="world-layout">
        <aside class="history-panel">
          <div class="history-header">
            <div>
              <h2>History</h2>
              <p>World lore and discoveries</p>
            </div>
          </div>
          <div id="history-window" class="history-window" aria-live="polite">
            <p class="history-empty">Generate lore to begin your chronicle.</p>
          </div>
        </aside>

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
      </section>
    </main>
    <script type="module" src="/static/app.js"></script>
  </body>
</html>
"""

MOCK_WORLD = [["🟩" for _ in range(128)] for _ in range(128)]
for y in range(10, 13):
    for x in range(9, 12):
        MOCK_WORLD[y][x] = "🟪"
MOCK_PLAYER = {"x": 8, "y": 10, "tile": "🙂"}
MOCK_NPCS = [{"id": "npc:12:10", "x": 12, "y": 10, "tile": "🧑‍🦱"}]
MOCK_VILLAGES = [
    {
        "id": "village:9:10:11:12",
        "bounds": {"left": 9, "right": 11, "top": 10, "bottom": 12},
        "center": {"x": 10, "y": 11},
        "size": {"width": 3, "height": 3},
    }
]
MOCK_COLLISION = {
    "tiles": {
        "trees": [],
        "plants": [],
        "buildings": [],
    }
}
MOCK_PAYLOAD = {
    "world": MOCK_WORLD,
    "player": MOCK_PLAYER,
    "npcs": MOCK_NPCS,
    "villages": MOCK_VILLAGES,
    "collision": MOCK_COLLISION,
    "viewport": {"width": 30, "height": 22},
}
MOCK_LORE_PAYLOAD = {
    "worldLore": "The frontier is young, sunlit, and full of travelers chasing rumor and rest.",
    "villages": [
        {
            "id": "village:9:10:11:12",
            "name": "Sunrest",
            "description": "A compact hill village where traders swap gossip beside bright gardens.",
            "bounds": {"left": 9, "right": 11, "top": 10, "bottom": 12},
            "center": {"x": 10, "y": 11},
            "tileCount": 9,
        }
    ],
    "npcs": [
        {
            "id": "npc:12:10",
            "x": 12,
            "y": 10,
            "tile": "🧑‍🦱",
            "name": "Mira Fen",
            "description": "A cheerful courier who always seems one step ahead of the news.",
        }
    ],
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
        elif url == "http://ui.test/api/lore/generate":
            request_log.append(url)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(MOCK_LORE_PAYLOAD, ensure_ascii=False),
            )
        else:
            route.fulfill(status=404, body="not found")

    page.route("http://ui.test/**", fulfill_app)


def _launch_browser(playwright):
    try:
        return playwright.chromium.launch(args=["--disable-setuid-sandbox"])
    except Exception as exc:  # pragma: no cover - environment-specific fallback
        pytest.skip(f"Playwright browser could not launch in this environment: {exc}")


def _parse_position(label: str) -> tuple[int, int]:
    prefix = "Player: "
    assert label.startswith(prefix), label
    x_text, y_text = label[len(prefix) :].split(", ")
    return int(x_text), int(y_text)


def test_browser_generates_lore_tracks_history_and_persists_after_reload() -> None:
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright)
        page = browser.new_page()
        request_log: list[str] = []
        _install_app_routes(page, request_log)
        page.goto("http://ui.test/", wait_until="load")

        assert page.locator("h1").text_content() == "Emoji Frontier"
        assert page.locator("#status").text_content() == "Ready to generate a world."
        assert page.locator("#player-position").text_content() == "Player: -, -"
        assert page.locator("#generate-lore-button").is_disabled()
        assert page.locator(".history-empty").text_content() == "Generate a map, then generate lore to begin your chronicle."

        page.locator("#generate-button").click()
        page.wait_for_function(
            """
            () => document.querySelector("#status")?.textContent ===
              "World ready. Use WASD to move."
            """
        )
        assert len(request_log) == 1
        assert not page.locator("#generate-lore-button").is_disabled()

        page.locator("#generate-lore-button").click()
        page.wait_for_function(
            """
            () => document.querySelector("#status")?.textContent ===
              "Lore recorded. Explore the world."
            """
        )
        assert len(request_log) == 2
        assert page.locator("#history-window .history-entry").count() == 1
        assert page.locator("#history-window .history-entry h3").nth(0).text_content() == "World Lore"
        assert (
            page.locator("#history-window .history-entry p").nth(0).text_content()
            == MOCK_LORE_PAYLOAD["worldLore"]
        )

        page.keyboard.press("d")
        page.wait_for_function("""() => document.querySelector("#player-position")?.textContent === "Player: 9, 10" """)
        assert page.locator("#history-window .history-entry").count() == 2
        assert page.locator("#history-window .history-entry h3").nth(1).text_content() == "Sunrest"
        assert (
            page.locator("#history-window .history-entry p").nth(1).text_content()
            == MOCK_LORE_PAYLOAD["villages"][0]["description"]
        )

        page.keyboard.press("a")
        page.wait_for_function("""() => document.querySelector("#player-position")?.textContent === "Player: 8, 10" """)
        page.keyboard.press("d")
        page.wait_for_function("""() => document.querySelector("#history-window .history-entry").length === 3""")
        assert page.locator("#history-window .history-entry h3").nth(2).text_content() == "Sunrest"
        assert page.locator("#history-window .history-entry").nth(2).locator("p").count() == 0

        page.keyboard.press("d")
        page.wait_for_function("""() => document.querySelector("#player-position")?.textContent === "Player: 10, 10" """)
        page.keyboard.press("d")
        page.wait_for_function("""() => document.querySelector("#history-window .history-entry").length === 4""")
        assert page.locator("#history-window .history-entry h3").nth(3).text_content() == "Mira Fen"
        assert (
            page.locator("#history-window .history-entry p").nth(2).text_content()
            == MOCK_LORE_PAYLOAD["npcs"][0]["description"]
        )

        page.keyboard.press("a")
        page.wait_for_function("""() => document.querySelector("#player-position")?.textContent === "Player: 10, 10" """)
        page.keyboard.press("d")
        page.wait_for_function("""() => document.querySelector("#history-window .history-entry").length === 5""")
        assert page.locator("#history-window .history-entry h3").nth(4).text_content() == "Mira Fen"
        assert page.locator("#history-window .history-entry").nth(4).locator("p").count() == 0

        page.reload(wait_until="load")
        page.wait_for_function(
            """
            () => document.querySelector("#status")?.textContent ===
              "Restored saved world. Use WASD to move."
            """
        )
        restored_label = page.locator("#player-position").text_content()
        assert restored_label is not None
        assert _parse_position(restored_label) == (11, 10)
        assert page.locator("#history-window .history-entry").count() == 5
        assert len(request_log) == 2

        browser.close()


def test_browser_ignores_invalid_saved_world() -> None:
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright)
        page = browser.new_page()
        request_log: list[str] = []
        _install_app_routes(page, request_log)
        page.add_init_script(
            """
            window.localStorage.setItem("ollama-rpg2:map-state:v2", "{broken");
            """
        )
        page.goto("http://ui.test/", wait_until="load")

        assert page.locator("#status").text_content() == "Ready to generate a world."
        assert page.locator("#player-position").text_content() == "Player: -, -"
        assert page.locator(".history-empty").text_content() == "Generate a map, then generate lore to begin your chronicle."
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


def test_browser_reset_clears_saved_world_and_history() -> None:
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright)
        page = browser.new_page()
        request_log: list[str] = []
        _install_app_routes(page, request_log)
        page.goto("http://ui.test/", wait_until="load")

        page.locator("#generate-button").click()
        page.wait_for_function(
            """
            () => document.querySelector("#status")?.textContent ===
              "World ready. Use WASD to move."
            """
        )
        page.locator("#generate-lore-button").click()
        page.wait_for_function(
            """
            () => document.querySelector("#status")?.textContent ===
              "Lore recorded. Explore the world."
            """
        )
        assert page.locator("#history-window .history-entry").count() == 1

        page.locator("#reset-button").click()
        page.wait_for_function(
            """
            () => document.querySelector("#status")?.textContent ===
              "Ready to generate a world."
            """
        )
        assert page.locator("#player-position").text_content() == "Player: -, -"
        assert page.locator(".history-empty").text_content() == "Generate a map, then generate lore to begin your chronicle."
        assert page.locator("#generate-lore-button").is_disabled()

        page.reload(wait_until="load")
        assert page.locator("#status").text_content() == "Ready to generate a world."
        assert page.locator("#player-position").text_content() == "Player: -, -"
        assert page.locator(".history-empty").text_content() == "Generate a map, then generate lore to begin your chronicle."
        assert len(request_log) == 2

        browser.close()
