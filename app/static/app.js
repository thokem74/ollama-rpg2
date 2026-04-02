const canvas = document.getElementById("map-canvas");
const context = canvas.getContext("2d");
const generateButton = document.getElementById("generate-button");
const generateLoreButton = document.getElementById("generate-lore-button");
const resetButton = document.getElementById("reset-button");
const statusLabel = document.getElementById("status");
const playerPosition = document.getElementById("player-position");
const historyWindow = document.getElementById("history-window");
const STORAGE_KEY = "ollama-rpg2:map-state:v2";

const state = {
  world: [],
  player: null,
  npcs: [],
  villages: [],
  collision: {
    tiles: {
      trees: [],
      plants: [],
      buildings: [],
    },
  },
  viewport: { width: 30, height: 22 },
  lore: null,
  historyEntries: [],
  discoveredVillageIds: new Set(),
  discoveredNpcIds: new Set(),
  currentVillageId: null,
  adjacentNpcIds: new Set(),
  busy: {
    map: false,
    lore: false,
  },
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

function storageAvailable() {
  try {
    return typeof window !== "undefined" && !!window.localStorage;
  } catch (error) {
    console.warn("Local storage is unavailable.", error);
    return false;
  }
}

function isTileList(value) {
  return Array.isArray(value) && value.every((tile) => typeof tile === "string");
}

function isValidWorld(world) {
  return (
    Array.isArray(world) &&
    world.length > 0 &&
    world.every((row) => Array.isArray(row) && row.length > 0 && row.every((tile) => typeof tile === "string"))
  );
}

function isValidPlayer(player) {
  return (
    player &&
    Number.isInteger(player.x) &&
    Number.isInteger(player.y) &&
    typeof player.tile === "string"
  );
}

function isValidNpcs(npcs) {
  return (
    Array.isArray(npcs) &&
    npcs.every(
      (npc) =>
        npc &&
        typeof npc.id === "string" &&
        Number.isInteger(npc.x) &&
        Number.isInteger(npc.y) &&
        typeof npc.tile === "string"
    )
  );
}

function isValidVillages(villages) {
  return (
    Array.isArray(villages) &&
    villages.every(
      (village) =>
        village &&
        typeof village.id === "string" &&
        village.bounds &&
        Number.isInteger(village.bounds.left) &&
        Number.isInteger(village.bounds.right) &&
        Number.isInteger(village.bounds.top) &&
        Number.isInteger(village.bounds.bottom) &&
        village.center &&
        Number.isInteger(village.center.x) &&
        Number.isInteger(village.center.y)
    )
  );
}

function isValidCollision(collision) {
  return (
    collision &&
    collision.tiles &&
    isTileList(collision.tiles.trees) &&
    isTileList(collision.tiles.plants) &&
    isTileList(collision.tiles.buildings)
  );
}

function isValidViewport(viewport) {
  return viewport && Number.isInteger(viewport.width) && Number.isInteger(viewport.height);
}

function isStringArray(values) {
  return Array.isArray(values) && values.every((value) => typeof value === "string");
}

function isValidHistoryEntries(entries) {
  return (
    Array.isArray(entries) &&
    entries.every(
      (entry) =>
        entry &&
        typeof entry.type === "string" &&
        typeof entry.title === "string" &&
        (entry.description === undefined || typeof entry.description === "string") &&
        (entry.entityId === undefined || typeof entry.entityId === "string") &&
        (entry.timestamp === undefined || Number.isInteger(entry.timestamp))
    )
  );
}

function isValidLoreEntity(entity) {
  return (
    entity &&
    typeof entity.id === "string" &&
    typeof entity.name === "string" &&
    typeof entity.description === "string"
  );
}

function isValidLore(lore) {
  return (
    lore === null ||
    (
      lore &&
      typeof lore.worldLore === "string" &&
      Array.isArray(lore.villages) &&
      lore.villages.every(
        (village) => isValidLoreEntity(village) && isValidVillages([village])
      ) &&
      Array.isArray(lore.npcs) &&
      lore.npcs.every(
        (npc) =>
          isValidLoreEntity(npc) &&
          typeof npc.id === "string" &&
          Number.isInteger(npc.x) &&
          Number.isInteger(npc.y) &&
          typeof npc.tile === "string"
      )
    )
  );
}

function canRestoreState(payload) {
  return (
    payload &&
    isValidWorld(payload.world) &&
    isValidPlayer(payload.player) &&
    isValidNpcs(payload.npcs) &&
    isValidVillages(payload.villages) &&
    isValidCollision(payload.collision) &&
    isValidViewport(payload.viewport) &&
    isValidLore(payload.lore) &&
    isValidHistoryEntries(payload.historyEntries) &&
    isStringArray(payload.discoveredVillageIds) &&
    isStringArray(payload.discoveredNpcIds) &&
    (payload.currentVillageId === null || typeof payload.currentVillageId === "string") &&
    isStringArray(payload.adjacentNpcIds)
  );
}

function applyPayload(payload) {
  state.world = payload.world;
  state.player = payload.player;
  state.npcs = payload.npcs;
  state.villages = payload.villages ?? [];
  state.collision = payload.collision;
  state.viewport = payload.viewport;
  state.lore = payload.lore ?? null;
  state.historyEntries = payload.historyEntries ?? [];
  state.discoveredVillageIds = new Set(payload.discoveredVillageIds ?? []);
  state.discoveredNpcIds = new Set(payload.discoveredNpcIds ?? []);
  state.currentVillageId = payload.currentVillageId ?? null;
  state.adjacentNpcIds = new Set(payload.adjacentNpcIds ?? []);
}

function snapshotState() {
  return {
    world: state.world,
    player: state.player,
    npcs: state.npcs,
    villages: state.villages,
    collision: state.collision,
    viewport: state.viewport,
    lore: state.lore,
    historyEntries: state.historyEntries,
    discoveredVillageIds: Array.from(state.discoveredVillageIds),
    discoveredNpcIds: Array.from(state.discoveredNpcIds),
    currentVillageId: state.currentVillageId,
    adjacentNpcIds: Array.from(state.adjacentNpcIds),
  };
}

function clearSavedState() {
  if (!storageAvailable()) {
    return;
  }

  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch (error) {
    console.warn("Could not clear saved world.", error);
  }
}

function saveState() {
  if (!storageAvailable() || !hasWorld()) {
    return;
  }

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshotState()));
  } catch (error) {
    console.warn("Could not save world.", error);
  }
}

function setBusyFlag(kind, value) {
  state.busy[kind] = value;
  updateActionButtons();
}

function updateActionButtons() {
  const busy = state.busy.map || state.busy.lore;
  generateButton.disabled = busy;
  generateLoreButton.disabled = busy || !hasWorld();
  resetButton.disabled = busy;
}

function restoreSavedState() {
  if (!storageAvailable()) {
    return false;
  }

  let rawPayload;
  try {
    rawPayload = window.localStorage.getItem(STORAGE_KEY);
  } catch (error) {
    console.warn("Could not read saved world.", error);
    return false;
  }

  if (!rawPayload) {
    return false;
  }

  try {
    const payload = JSON.parse(rawPayload);
    if (!canRestoreState(payload)) {
      clearSavedState();
      return false;
    }

    applyPayload(payload);
    return true;
  } catch (error) {
    console.warn("Saved world is invalid.", error);
    clearSavedState();
    return false;
  }
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

function collidesWithNpc(x, y) {
  return state.npcs.some((npc) => npc.x === x && npc.y === y);
}

function collidesWithTile(x, y) {
  const tile = state.world[y]?.[x];
  const blockingTiles = new Set([
    ...state.collision.tiles.trees,
    ...state.collision.tiles.plants,
    ...state.collision.tiles.buildings,
  ]);
  return blockingTiles.has(tile);
}

function resizeCanvas() {
  canvas.width = state.viewport.width * tileStep - tileGap;
  canvas.height = state.viewport.height * tileStep - tileGap;
}

function createHistoryEntry(type, title, description, entityId) {
  return {
    type,
    title,
    description,
    entityId,
    timestamp: Date.now(),
  };
}

function appendHistoryEntry(entry) {
  state.historyEntries.push(entry);
  renderHistory();
  saveState();
}

function renderHistory() {
  historyWindow.replaceChildren();

  if (state.historyEntries.length === 0) {
    const empty = document.createElement("p");
    empty.className = "history-empty";
    empty.textContent = hasWorld()
      ? "Generate lore to begin your chronicle."
      : "Generate a map, then generate lore to begin your chronicle.";
    historyWindow.append(empty);
    return;
  }

  for (const entry of state.historyEntries) {
    const article = document.createElement("article");
    article.className = "history-entry";

    const title = document.createElement("h3");
    title.textContent = entry.title;
    article.append(title);

    if (entry.description) {
      const description = document.createElement("p");
      description.textContent = entry.description;
      article.append(description);
    }

    historyWindow.append(article);
  }

  historyWindow.scrollTop = historyWindow.scrollHeight;
}

function clearLoreState() {
  state.lore = null;
  state.historyEntries = [];
  state.discoveredVillageIds = new Set();
  state.discoveredNpcIds = new Set();
  state.currentVillageId = null;
  state.adjacentNpcIds = new Set();
}

function initializePresenceState() {
  state.currentVillageId = currentVillageAtPlayer();
  state.adjacentNpcIds = currentAdjacentNpcIds();
}

function resetRuntimeState() {
  state.world = [];
  state.player = null;
  state.npcs = [];
  state.villages = [];
  state.collision = {
    tiles: {
      trees: [],
      plants: [],
      buildings: [],
    },
  };
  state.viewport = { width: 30, height: 22 };
  clearLoreState();
}

function isInsideVillage(village, x, y) {
  return (
    x >= village.bounds.left &&
    x <= village.bounds.right &&
    y >= village.bounds.top &&
    y <= village.bounds.bottom
  );
}

function currentVillageAtPlayer() {
  if (!state.player || !state.lore) {
    return null;
  }

  const village = state.lore.villages.find((candidate) =>
    isInsideVillage(candidate, state.player.x, state.player.y)
  );
  return village ? village.id : null;
}

function currentAdjacentNpcIds() {
  if (!state.player || !state.lore) {
    return new Set();
  }

  return new Set(
    state.lore.npcs
      .filter(
        (npc) =>
          Math.abs(npc.x - state.player.x) + Math.abs(npc.y - state.player.y) === 1
      )
      .map((npc) => npc.id)
  );
}

function processVillageDiscovery() {
  if (!state.lore) {
    return;
  }

  const villageId = currentVillageAtPlayer();
  if (!villageId) {
    state.currentVillageId = null;
    return;
  }

  if (villageId === state.currentVillageId) {
    return;
  }

  const village = state.lore.villages.find((candidate) => candidate.id === villageId);
  if (!village) {
    state.currentVillageId = villageId;
    return;
  }

  const firstVisit = !state.discoveredVillageIds.has(villageId);
  state.discoveredVillageIds.add(villageId);
  state.currentVillageId = villageId;
  appendHistoryEntry(
    createHistoryEntry(
      "village",
      village.name,
      firstVisit ? village.description : undefined,
      village.id
    )
  );
}

function processNpcDiscovery() {
  if (!state.lore) {
    return;
  }

  const adjacentIds = currentAdjacentNpcIds();
  for (const npcId of adjacentIds) {
    if (state.adjacentNpcIds.has(npcId)) {
      continue;
    }

    const npc = state.lore.npcs.find((candidate) => candidate.id === npcId);
    if (!npc) {
      continue;
    }

    const firstMeeting = !state.discoveredNpcIds.has(npcId);
    state.discoveredNpcIds.add(npcId);
    appendHistoryEntry(
      createHistoryEntry(
        "npc",
        npc.name,
        firstMeeting ? npc.description : undefined,
        npc.id
      )
    );
  }

  state.adjacentNpcIds = adjacentIds;
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

      const npc = state.npcs.find((candidate) => candidate.x === worldX && candidate.y === worldY);
      if (npc) {
        context.fillText(npc.tile, centerX, centerY + 2);
      }

      if (state.player.x === worldX && state.player.y === worldY) {
        context.fillText(state.player.tile, centerX, centerY + 2);
      }
    }
  }
}

async function generateMap() {
  setBusyFlag("map", true);
  updateStatus("Generating world...");

  try {
    const response = await fetch("/api/map/generate", { method: "POST" });
    if (!response.ok) {
      throw new Error(`Map generation failed with ${response.status}`);
    }

    const payload = await response.json();
    applyPayload({
      world: payload.world,
      player: payload.player,
      npcs: payload.npcs ?? [],
      villages: payload.villages ?? [],
      collision: payload.collision ?? state.collision,
      viewport: payload.viewport,
      lore: null,
      historyEntries: [],
      discoveredVillageIds: [],
      discoveredNpcIds: [],
      currentVillageId: null,
      adjacentNpcIds: [],
    });
    initializePresenceState();
    saveState();
    updatePlayerLabel();
    renderHistory();
    drawViewport();
    updateStatus("World ready. Use WASD to move.");
  } catch (error) {
    console.error(error);
    updateStatus("Could not generate the map.");
  } finally {
    setBusyFlag("map", false);
  }
}

async function generateLore() {
  if (!hasWorld()) {
    updateStatus("Generate a map before generating lore.");
    return;
  }

  setBusyFlag("lore", true);
  updateStatus("Consulting the GM...");

  try {
    const response = await fetch("/api/lore/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        world: state.world,
        npcs: state.npcs,
      }),
    });
    if (!response.ok) {
      throw new Error(`Lore generation failed with ${response.status}`);
    }

    state.lore = await response.json();
    state.historyEntries = [
      createHistoryEntry("world", "World Lore", state.lore.worldLore),
    ];
    state.discoveredVillageIds = new Set();
    state.discoveredNpcIds = new Set();
    initializePresenceState();
    renderHistory();
    saveState();
    updateStatus("Lore recorded. Explore the world.");
  } catch (error) {
    console.error(error);
    updateStatus("Could not generate lore.");
  } finally {
    setBusyFlag("lore", false);
  }
}

function resetGame() {
  if (storageAvailable()) {
    try {
      window.localStorage.clear();
    } catch (error) {
      console.warn("Could not clear browser storage.", error);
    }
  }

  resetRuntimeState();
  updatePlayerLabel();
  renderHistory();
  drawViewport();
  updateStatus("Ready to generate a world.");
  updateActionButtons();
}

function movePlayer(dx, dy) {
  if (!hasWorld()) {
    return;
  }

  const worldHeight = state.world.length;
  const worldWidth = state.world[0].length;
  const nextX = clamp(state.player.x + dx, 0, worldWidth - 1);
  const nextY = clamp(state.player.y + dy, 0, worldHeight - 1);

  if (
    (nextX !== state.player.x || nextY !== state.player.y) &&
    (collidesWithNpc(nextX, nextY) || collidesWithTile(nextX, nextY))
  ) {
    updateStatus("Blocked by obstacle.");
    return;
  }

  state.player.x = nextX;
  state.player.y = nextY;
  processVillageDiscovery();
  processNpcDiscovery();
  saveState();
  updatePlayerLabel();
  drawViewport();
  updateStatus("World ready. Use WASD to move.");
}

generateButton.addEventListener("click", () => {
  generateMap();
});

generateLoreButton.addEventListener("click", () => {
  generateLore();
});

resetButton.addEventListener("click", () => {
  resetGame();
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

if (restoreSavedState()) {
  initializePresenceState();
  updatePlayerLabel();
  renderHistory();
  drawViewport();
  updateStatus("Restored saved world. Use WASD to move.");
} else {
  updatePlayerLabel();
  renderHistory();
}

drawViewport();
updateActionButtons();
