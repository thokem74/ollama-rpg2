import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"
INDEX_FILE = STATIC_DIR / "index.html"
STYLES_FILE = STATIC_DIR / "styles.css"
SCRIPT_FILE = STATIC_DIR / "app.js"

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
MOCK_NPC_CHAT_PAYLOAD = {"reply": "Bring me two blossoms and I will help however I can."}


def _install_app_routes(page, request_log: list[str]) -> None:
    def fulfill_app(route) -> None:
        url = route.request.url
        if url == "http://ui.test/":
            route.fulfill(status=200, content_type="text/html", body=INDEX_FILE.read_text())
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
        elif url == "http://ui.test/api/npc/chat":
            request_log.append(url)
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(MOCK_NPC_CHAT_PAYLOAD, ensure_ascii=False),
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


def test_browser_uses_full_window_and_resizes_map() -> None:
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright)
        page = browser.new_page(viewport={"width": 1680, "height": 980})
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

        initial_layout = page.evaluate(
            """
            () => {
              const shell = document.querySelector(".app-shell");
              const canvas = document.querySelector("#map-canvas");
              const worldLayout = document.querySelector(".world-layout");
              const historyPanel = document.querySelector(".history-panel");
              const chatPanel = document.querySelector(".chat-panel");
              return {
                shellWidth: shell.getBoundingClientRect().width,
                canvasWidth: canvas.getBoundingClientRect().width,
                worldHeight: worldLayout.getBoundingClientRect().height,
                historyPanelHeight: historyPanel.getBoundingClientRect().height,
                chatPanelHeight: chatPanel.getBoundingClientRect().height,
                windowHeight: window.innerHeight,
              };
            }
            """
        )

        assert initial_layout["shellWidth"] > 1400
        assert initial_layout["canvasWidth"] > 720
        assert initial_layout["worldHeight"] > initial_layout["windowHeight"] * 0.6

        page.set_viewport_size({"width": 1320, "height": 980})
        page.wait_for_function(
            """
            () => {
              const canvas = document.querySelector("#map-canvas");
              return canvas && canvas.getBoundingClientRect().width < 900;
            }
            """
        )

        resized_canvas_width = page.locator("#map-canvas").evaluate(
            "(node) => node.getBoundingClientRect().width"
        )
        resized_panel_heights = page.evaluate(
            """
            () => {
              const historyPanel = document.querySelector(".history-panel");
              const chatPanel = document.querySelector(".chat-panel");
              return {
                historyPanelHeight: historyPanel.getBoundingClientRect().height,
                chatPanelHeight: chatPanel.getBoundingClientRect().height,
              };
            }
            """
        )
        assert resized_canvas_width < initial_layout["canvasWidth"]
        assert abs(resized_panel_heights["historyPanelHeight"] - initial_layout["historyPanelHeight"]) <= 2
        assert abs(resized_panel_heights["chatPanelHeight"] - initial_layout["chatPanelHeight"]) <= 2

        page.keyboard.press("d")
        page.wait_for_function(
            """() => document.querySelector("#player-position")?.textContent === "Player: 9, 10" """
        )
        assert len(request_log) == 1

        browser.close()


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
        page.wait_for_function("""() => document.querySelectorAll("#history-window .history-entry").length === 3""")
        assert page.locator("#history-window .history-entry h3").nth(2).text_content() == "Sunrest"
        assert page.locator("#history-window .history-entry").nth(2).locator("p").count() == 0

        page.keyboard.press("d")
        page.wait_for_function("""() => document.querySelector("#player-position")?.textContent === "Player: 10, 10" """)
        page.keyboard.press("d")
        page.wait_for_function("""() => document.querySelectorAll("#history-window .history-entry").length === 4""")
        assert page.locator("#history-window .history-entry h3").nth(3).text_content() == "Mira Fen"
        assert (
            page.locator("#history-window .history-entry p").nth(2).text_content()
            == MOCK_LORE_PAYLOAD["npcs"][0]["description"]
        )

        page.keyboard.press("a")
        page.wait_for_function("""() => document.querySelector("#player-position")?.textContent === "Player: 10, 10" """)
        page.keyboard.press("d")
        page.wait_for_function("""() => document.querySelectorAll("#history-window .history-entry").length === 5""")
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


def test_browser_npc_chat_focus_and_persistence() -> None:
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

        page.keyboard.press("d")
        page.wait_for_function("""() => document.querySelector("#player-position")?.textContent === "Player: 9, 10" """)
        page.keyboard.press("d")
        page.wait_for_function("""() => document.querySelector("#player-position")?.textContent === "Player: 10, 10" """)
        page.keyboard.press("d")
        page.wait_for_function("""() => document.querySelector("#player-position")?.textContent === "Player: 11, 10" """)

        page.keyboard.press("e")
        page.wait_for_function("""() => document.activeElement?.id === "chat-input" """)
        assert page.locator("#chat-title").text_content() == "Mira Fen"
        assert (
            page.locator("#chat-description").text_content()
            == MOCK_LORE_PAYLOAD["npcs"][0]["description"]
        )

        page.locator("#chat-input").fill("how can i help you")
        page.keyboard.press("w")
        assert page.locator("#player-position").text_content() == "Player: 11, 10"
        assert page.locator("#chat-input").input_value() == "how can i help youw"

        page.keyboard.press("Enter")
        page.wait_for_function("""() => document.querySelectorAll("#chat-window .chat-message").length === 2""")
        page.wait_for_function("""() => document.activeElement?.id === "chat-input" """)
        assert page.locator("#chat-window .chat-message").nth(0).text_content() == "You: how can i help youw"
        assert (
            page.locator("#chat-window .chat-message").nth(1).text_content()
            == f"Mira Fen: {MOCK_NPC_CHAT_PAYLOAD['reply']}"
        )

        page.locator("#chat-input").fill("temporary draft")
        page.keyboard.press("Escape")
        page.wait_for_function("""() => document.activeElement?.id === "map-canvas" """)
        assert page.locator("#chat-input").input_value() == ""

        page.reload(wait_until="load")
        page.wait_for_function(
            """
            () => document.querySelector("#status")?.textContent ===
              "Restored saved world. Use WASD to move."
            """
        )
        assert page.locator("#chat-window .chat-message").count() == 2
        page.keyboard.press("e")
        page.wait_for_function("""() => document.activeElement?.id === "chat-input" """)
        assert "http://ui.test/api/npc/chat" in request_log

        browser.close()


def test_browser_requires_lore_before_opening_npc_chat() -> None:
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

        page.keyboard.press("d")
        page.wait_for_function("""() => document.querySelector("#player-position")?.textContent === "Player: 9, 10" """)
        page.keyboard.press("d")
        page.wait_for_function("""() => document.querySelector("#player-position")?.textContent === "Player: 10, 10" """)
        page.keyboard.press("e")

        assert page.locator("#status").text_content() == "Generate lore before talking to NPCs."
        assert page.locator("#chat-title").text_content() == "No conversation"
        assert page.locator("#chat-window .chat-empty").text_content() == "No NPC selected."
        assert "http://ui.test/api/npc/chat" not in request_log

        browser.close()


def test_browser_ignores_invalid_saved_world() -> None:
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright)
        page = browser.new_page()
        request_log: list[str] = []
        _install_app_routes(page, request_log)
        page.add_init_script(
            """
            window.localStorage.setItem("ollama-rpg2:map-state:v3", "{broken");
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


def test_browser_stacks_without_horizontal_overflow_on_small_screens() -> None:
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright)
        page = browser.new_page(viewport={"width": 820, "height": 1180})
        request_log: list[str] = []
        _install_app_routes(page, request_log)
        page.goto("http://ui.test/", wait_until="load")

        layout = page.evaluate(
            """
            () => {
              const worldLayout = document.querySelector(".world-layout");
              const historyPanel = document.querySelector(".history-panel");
              const viewportPanel = document.querySelector(".viewport-panel");
              const chatPanel = document.querySelector(".chat-panel");
              const canvas = document.querySelector("#map-canvas");
              return {
                columns: getComputedStyle(worldLayout).gridTemplateColumns,
                bodyScrollWidth: document.body.scrollWidth,
                windowWidth: window.innerWidth,
                historyTop: historyPanel.getBoundingClientRect().top,
                viewportTop: viewportPanel.getBoundingClientRect().top,
                chatTop: chatPanel.getBoundingClientRect().top,
                canvasWidth: canvas.getBoundingClientRect().width,
                viewportWidth: viewportPanel.getBoundingClientRect().width,
              };
            }
            """
        )

        assert layout["columns"].count("px") == 1
        assert layout["bodyScrollWidth"] <= layout["windowWidth"]
        assert layout["historyTop"] < layout["viewportTop"] < layout["chatTop"]
        assert layout["canvasWidth"] <= layout["viewportWidth"]
        assert len(request_log) == 0

        browser.close()


def test_browser_side_panels_scroll_without_resizing() -> None:
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright)
        page = browser.new_page(viewport={"width": 1680, "height": 980})
        request_log: list[str] = []
        _install_app_routes(page, request_log)
        page.goto("http://ui.test/", wait_until="load")

        layout = page.evaluate(
            """
            () => {
              const historyPanel = document.querySelector(".history-panel");
              const chatPanel = document.querySelector(".chat-panel");
              const historyWindow = document.querySelector("#history-window");
              const chatWindow = document.querySelector("#chat-window");
              const chatForm = document.querySelector("#chat-form");

              for (let index = 0; index < 24; index += 1) {
                const historyEntry = document.createElement("article");
                historyEntry.className = "history-entry";
                historyEntry.innerHTML = `<h3>Entry ${index}</h3><p>Overflow content ${index}</p>`;
                historyWindow.append(historyEntry);

                const message = document.createElement("p");
                message.className = "chat-message";
                message.textContent = `Message ${index} `.repeat(8);
                chatWindow.append(message);
              }

              return {
                historyPanelHeight: historyPanel.getBoundingClientRect().height,
                chatPanelHeight: chatPanel.getBoundingClientRect().height,
                historyClientHeight: historyWindow.clientHeight,
                historyScrollHeight: historyWindow.scrollHeight,
                chatClientHeight: chatWindow.clientHeight,
                chatScrollHeight: chatWindow.scrollHeight,
                chatFormBottom: chatForm.getBoundingClientRect().bottom,
                chatPanelBottom: chatPanel.getBoundingClientRect().bottom,
              };
            }
            """
        )

        assert 680 <= layout["historyPanelHeight"] <= 780
        assert 680 <= layout["chatPanelHeight"] <= 780
        assert layout["historyScrollHeight"] > layout["historyClientHeight"]
        assert layout["chatScrollHeight"] > layout["chatClientHeight"]
        assert layout["chatFormBottom"] <= layout["chatPanelBottom"]
        assert len(request_log) == 0

        browser.close()
