const canvas = document.getElementById("map-canvas");
const context = canvas.getContext("2d");
const generateButton = document.getElementById("generate-button");
const statusLabel = document.getElementById("status");
const playerPosition = document.getElementById("player-position");

const state = {
  world: [],
  player: null,
  viewport: { width: 30, height: 22 },
};

const emojiFontSize = 30;
const tileGap = 4;
const tileStep = emojiFontSize + tileGap;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function hasWorld() {
  return state.world.length > 0 && state.player;
}

function cameraOrigin() {
  const worldHeight = state.world.length;
  const worldWidth = state.world[0]?.length ?? 0;
  const halfWidth = Math.floor(state.viewport.width / 2);
  const halfHeight = Math.floor(state.viewport.height / 2);

  const left = clamp(state.player.x - halfWidth, 0, worldWidth - state.viewport.width);
  const top = clamp(state.player.y - halfHeight, 0, worldHeight - state.viewport.height);
  return { left, top };
}

function updateStatus(text) {
  statusLabel.textContent = text;
}

function updatePlayerLabel() {
  if (!state.player) {
    playerPosition.textContent = "Player: -, -";
    return;
  }

  playerPosition.textContent = `Player: ${state.player.x}, ${state.player.y}`;
}

function resizeCanvas() {
  canvas.width = state.viewport.width * tileStep - tileGap;
  canvas.height = state.viewport.height * tileStep - tileGap;
}

function drawViewport() {
  resizeCanvas();
  context.clearRect(0, 0, canvas.width, canvas.height);

  if (!hasWorld()) {
    context.fillStyle = "#f7f7ec";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "#5f8f33";
    context.font = "24px Trebuchet MS";
    context.textAlign = "center";
    context.fillText("Generate a map to begin.", canvas.width / 2, canvas.height / 2);
    return;
  }

  const camera = cameraOrigin();

  context.fillStyle = "#f7f7ec";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.font = `${emojiFontSize}px 'Apple Color Emoji', 'Segoe UI Emoji', sans-serif`;

  for (let row = 0; row < state.viewport.height; row += 1) {
    for (let col = 0; col < state.viewport.width; col += 1) {
      const worldX = camera.left + col;
      const worldY = camera.top + row;
      const tile = state.world[worldY][worldX];
      const centerX = col * tileStep + emojiFontSize / 2;
      const centerY = row * tileStep + emojiFontSize / 2;

      context.fillText(tile, centerX, centerY + 2);

      if (state.player.x === worldX && state.player.y === worldY) {
        context.fillText(state.player.tile, centerX, centerY + 2);
      }
    }
  }
}

async function generateMap() {
  generateButton.disabled = true;
  updateStatus("Generating world...");

  try {
    const response = await fetch("/api/map/generate", { method: "POST" });
    if (!response.ok) {
      throw new Error(`Map generation failed with ${response.status}`);
    }

    const payload = await response.json();
    state.world = payload.world;
    state.player = payload.player;
    state.viewport = payload.viewport;
    updatePlayerLabel();
    drawViewport();
    updateStatus("World ready. Use WASD to move.");
  } catch (error) {
    console.error(error);
    updateStatus("Could not generate the map.");
  } finally {
    generateButton.disabled = false;
  }
}

function movePlayer(dx, dy) {
  if (!hasWorld()) {
    return;
  }

  const worldHeight = state.world.length;
  const worldWidth = state.world[0].length;
  state.player.x = clamp(state.player.x + dx, 0, worldWidth - 1);
  state.player.y = clamp(state.player.y + dy, 0, worldHeight - 1);
  updatePlayerLabel();
  drawViewport();
}

generateButton.addEventListener("click", () => {
  generateMap();
});

window.addEventListener("keydown", (event) => {
  const key = event.key.toLowerCase();
  if (["w", "a", "s", "d"].includes(key)) {
    event.preventDefault();
  }

  if (key === "w") {
    movePlayer(0, -1);
  } else if (key === "s") {
    movePlayer(0, 1);
  } else if (key === "a") {
    movePlayer(-1, 0);
  } else if (key === "d") {
    movePlayer(1, 0);
  }
});

drawViewport();
