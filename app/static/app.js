const rootElement = document.documentElement;
const canvas = document.getElementById("map-canvas");
const context = canvas.getContext("2d");
const viewportStage = canvas.parentElement;
const heroEyebrow = document.getElementById("hero-eyebrow");
const heroIntro = document.getElementById("hero-intro");
const generateButton = document.getElementById("generate-button");
const generateLoreButton = document.getElementById("generate-lore-button");
const resetButton = document.getElementById("reset-button");
const languageLabel = document.getElementById("language-label");
const languageButtons = Array.from(document.querySelectorAll("[data-language]"));
const statusLabel = document.getElementById("status");
const historyTitle = document.getElementById("history-title");
const historySubtitle = document.getElementById("history-subtitle");
const viewportTitle = document.getElementById("viewport-title");
const viewportSubtitle = document.getElementById("viewport-subtitle");
const playerPosition = document.getElementById("player-position");
const chatEyebrow = document.getElementById("chat-eyebrow");
const historyWindow = document.getElementById("history-window");
const chatTitle = document.getElementById("chat-title");
const chatDescription = document.getElementById("chat-description");
const chatWindow = document.getElementById("chat-window");
const chatForm = document.getElementById("chat-form");
const chatInputLabel = document.getElementById("chat-input-label");
const chatInput = document.getElementById("chat-input");
const chatSendButton = document.getElementById("chat-send-button");
const STORAGE_KEY = "ollama-rpg2:map-state:v3";
const LANGUAGE_STORAGE_KEY = "ollama-rpg2:language";
const MAX_CHAT_MESSAGES = 12;
const BASE_EMOJI_FONT_SIZE = 30;
const BASE_TILE_GAP = 4;
const MAP_ASPECT_RATIO = 30 / 22;
const DEFAULT_LANGUAGE = "en";

const translations = {
  en: {
    heroEyebrow: "World Seedling",
    languageLabel: "Language",
    heroIntro: "Generate a 128x128 world, uncover lore as you explore a 30x22 viewport, move with WSAD and press E to chat with nearby NPCs.",
    generateMap: "Generate Map",
    generateLore: "Generate Lore",
    reset: "Reset",
    historyTitle: "History",
    historySubtitle: "World lore and discoveries",
    viewportTitle: "Viewport",
    viewportSubtitle: "30 x 22 tiles",
    playerUnknown: "Player: -, -",
    playerPosition: "Player: {x}, {y}",
    chatEyebrow: "Village Voices",
    chatNoConversation: "No conversation",
    chatWalkPrompt: "Walk next to an NPC, generate lore, then press E to talk.",
    chatEmpty: "No NPC selected.",
    chatStarter: "Say hello to start the conversation.",
    chatInputLabel: "Your line",
    chatInputPlaceholder: "Type what you want to say, then press Enter.",
    sendLine: "Send line",
    youLabel: "You",
    historyEmptyLore: "Generate lore to begin your chronicle.",
    historyEmptyMap: "Generate a map, then generate lore to begin your chronicle.",
    worldLoreTitle: "World Lore",
    viewportEmpty: "Generate a map to begin.",
    canvasLabel: "Generated map viewport",
    statusReady: "Ready to generate a world.",
    statusGeneratingWorld: "Generating world...",
    statusWorldReady: "World ready. Use WASD to move.",
    statusMapFailed: "Could not generate the map.",
    statusGenerateMapFirst: "Generate a map before generating lore.",
    statusConsultingGm: "Consulting the GM...",
    statusLoreRecorded: "Lore recorded. Explore the world.",
    statusLoreFailed: "Could not generate lore.",
    statusBlocked: "Blocked by obstacle.",
    statusPressE: "Press E next to an NPC to start a conversation.",
    statusGenerateLoreFirst: "Generate lore before talking to NPCs.",
    statusListening: "Listening to {name}...",
    statusReply: "{name} replies.",
    statusNpcUnavailable: "Could not reach this NPC right now.",
    statusMoveToNpc: "Move next to an NPC to talk.",
    statusSpeaking: "Speaking with {name}.",
    statusRestored: "Restored saved world. Use WASD to move.",
  },
  de: {
    heroEyebrow: "Weltkeim",
    languageLabel: "Sprache",
    heroIntro: "Erzeuge eine 128x128-Welt, entdecke Lore beim Erkunden des 30x22-Viewports, bewege dich mit WSAD und druecke E, um mit nahen NPCs zu sprechen.",
    generateMap: "Karte erzeugen",
    generateLore: "Lore erzeugen",
    reset: "Zuruecksetzen",
    historyTitle: "Chronik",
    historySubtitle: "Welt-Lore und Entdeckungen",
    viewportTitle: "Ausschnitt",
    viewportSubtitle: "30 x 22 Felder",
    playerUnknown: "Spieler: -, -",
    playerPosition: "Spieler: {x}, {y}",
    chatEyebrow: "Stimmen des Dorfs",
    chatNoConversation: "Kein Gespraech",
    chatWalkPrompt: "Geh neben einen NPC, erzeuge Lore und druecke dann E, um zu sprechen.",
    chatEmpty: "Kein NPC ausgewaehlt.",
    chatStarter: "Sag hallo, um das Gespraech zu beginnen.",
    chatInputLabel: "Deine Zeile",
    chatInputPlaceholder: "Schreibe, was du sagen willst, und druecke dann Enter.",
    sendLine: "Zeile senden",
    youLabel: "Du",
    historyEmptyLore: "Erzeuge Lore, um deine Chronik zu beginnen.",
    historyEmptyMap: "Erzeuge zuerst eine Karte und dann Lore, um deine Chronik zu beginnen.",
    worldLoreTitle: "Welt-Lore",
    viewportEmpty: "Erzeuge eine Karte, um zu beginnen.",
    canvasLabel: "Generierter Kartenausschnitt",
    statusReady: "Bereit, eine Welt zu erzeugen.",
    statusGeneratingWorld: "Welt wird erzeugt...",
    statusWorldReady: "Welt bereit. Bewege dich mit WASD.",
    statusMapFailed: "Die Karte konnte nicht erzeugt werden.",
    statusGenerateMapFirst: "Erzeuge eine Karte, bevor du Lore erzeugst.",
    statusConsultingGm: "Der Spielleiter wird befragt...",
    statusLoreRecorded: "Lore gespeichert. Erkunde die Welt.",
    statusLoreFailed: "Lore konnte nicht erzeugt werden.",
    statusBlocked: "Ein Hindernis versperrt den Weg.",
    statusPressE: "Druecke E neben einem NPC, um ein Gespraech zu beginnen.",
    statusGenerateLoreFirst: "Erzeuge Lore, bevor du mit NPCs sprichst.",
    statusListening: "{name} hoert zu...",
    statusReply: "{name} antwortet.",
    statusNpcUnavailable: "Dieser NPC ist gerade nicht erreichbar.",
    statusMoveToNpc: "Geh neben einen NPC, um zu sprechen.",
    statusSpeaking: "Du sprichst mit {name}.",
    statusRestored: "Gespeicherte Welt wiederhergestellt. Bewege dich mit WASD.",
  },
};

const state = {
  language: DEFAULT_LANGUAGE,
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
  activeNpcId: null,
  chatDraft: "",
  npcChats: {},
  focusTarget: "map",
  busy: {
    map: false,
    lore: false,
    chat: false,
  },
  status: {
    key: "statusReady",
    params: {},
  },
};

let resizeFrame = null;

function isValidLanguage(value) {
  return Object.prototype.hasOwnProperty.call(translations, value);
}

function t(key, params = {}) {
  const template = translations[state.language]?.[key] ?? translations[DEFAULT_LANGUAGE][key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name) => `${params[name] ?? ""}`);
}

function setStatus(key, params = {}) {
  state.status = { key, params };
  statusLabel.textContent = t(key, params);
}

function loadSavedLanguage() {
  if (!storageAvailable()) {
    return DEFAULT_LANGUAGE;
  }

  try {
    const value = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return isValidLanguage(value) ? value : DEFAULT_LANGUAGE;
  } catch (error) {
    console.warn("Could not read saved language.", error);
    return DEFAULT_LANGUAGE;
  }
}

function saveLanguagePreference() {
  if (!storageAvailable()) {
    return;
  }

  try {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, state.language);
  } catch (error) {
    console.warn("Could not save language.", error);
  }
}

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

function isValidTranscriptEntry(entry) {
  return (
    Array.isArray(entry) &&
    entry.length === 2 &&
    ["u", "n"].includes(entry[0]) &&
    typeof entry[1] === "string"
  );
}

function isValidNpcChats(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }

  return Object.entries(value).every(
    ([npcId, transcript]) =>
      typeof npcId === "string" &&
      Array.isArray(transcript) &&
      transcript.every((entry) => isValidTranscriptEntry(entry))
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
    isStringArray(payload.adjacentNpcIds) &&
    (payload.activeNpcId === null || typeof payload.activeNpcId === "string") &&
    typeof payload.chatDraft === "string" &&
    isValidNpcChats(payload.npcChats) &&
    (payload.language === undefined || isValidLanguage(payload.language))
  );
}

function applyPayload(payload) {
  state.language = isValidLanguage(payload.language) ? payload.language : state.language;
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
  state.activeNpcId = payload.activeNpcId ?? null;
  state.chatDraft = payload.chatDraft ?? "";
  state.npcChats = payload.npcChats ?? {};
}

function snapshotState() {
  return {
    language: state.language,
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
    activeNpcId: state.activeNpcId,
    chatDraft: state.chatDraft,
    npcChats: state.npcChats,
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
  chatSendButton.disabled = state.busy.chat || !state.activeNpcId || !state.lore;
  chatInput.disabled = state.busy.chat || !state.activeNpcId || !state.lore;
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

function updatePlayerLabel() {
  if (!state.player) {
    playerPosition.textContent = t("playerUnknown");
    return;
  }

  playerPosition.textContent = t("playerPosition", {
    x: state.player.x,
    y: state.player.y,
  });
}

function renderStaticText() {
  rootElement.lang = state.language;
  heroEyebrow.textContent = t("heroEyebrow");
  heroIntro.textContent = t("heroIntro");
  languageLabel.textContent = t("languageLabel");
  generateButton.textContent = t("generateMap");
  generateLoreButton.textContent = t("generateLore");
  resetButton.textContent = t("reset");
  historyTitle.textContent = t("historyTitle");
  historySubtitle.textContent = t("historySubtitle");
  viewportTitle.textContent = t("viewportTitle");
  viewportSubtitle.textContent = t("viewportSubtitle");
  chatEyebrow.textContent = t("chatEyebrow");
  chatInputLabel.textContent = t("chatInputLabel");
  chatInput.placeholder = t("chatInputPlaceholder");
  chatSendButton.textContent = t("sendLine");
  canvas.setAttribute("aria-label", t("canvasLabel"));

  for (const button of languageButtons) {
    const active = button.dataset.language === state.language;
    button.setAttribute("aria-pressed", active ? "true" : "false");
  }

  setStatus(state.status.key, state.status.params);
}

function setLanguage(language) {
  if (!isValidLanguage(language) || language === state.language) {
    return;
  }

  state.language = language;
  saveLanguagePreference();
  saveState();
  renderStaticText();
  updatePlayerLabel();
  renderHistory();
  renderChatPanel();
  drawViewport();
}

function isTypingTarget(target) {
  return target === chatInput || target?.closest?.("#chat-form");
}

function getLoreNpcById(npcId) {
  if (!state.lore || !npcId) {
    return null;
  }

  return state.lore.npcs.find((npc) => npc.id === npcId) ?? null;
}

function trimTranscript(transcript) {
  return transcript
    .filter((entry) => isValidTranscriptEntry(entry) && entry[1].trim())
    .map(([speaker, text]) => [speaker, text.trim()])
    .slice(-MAX_CHAT_MESSAGES);
}

function getNpcTranscript(npcId) {
  if (!npcId) {
    return [];
  }

  return trimTranscript(state.npcChats[npcId] ?? []);
}

function setNpcTranscript(npcId, transcript) {
  if (!npcId) {
    return;
  }

  state.npcChats[npcId] = trimTranscript(transcript);
}

function appendNpcTranscriptEntry(npcId, speaker, text) {
  if (!npcId || !text.trim()) {
    return;
  }

  const transcript = getNpcTranscript(npcId);
  transcript.push([speaker, text.trim()]);
  setNpcTranscript(npcId, transcript);
}

function setMapFocus() {
  state.focusTarget = "map";
  canvas.focus();
}

function setChatFocus() {
  state.focusTarget = "chat";
  chatInput.focus();
}

function clearChatDraftAndFocusMap() {
  state.chatDraft = "";
  chatInput.value = "";
  saveState();
  setMapFocus();
}

function renderChatPanel() {
  const npc = getLoreNpcById(state.activeNpcId);
  chatWindow.replaceChildren();

  if (!npc) {
    chatTitle.textContent = t("chatNoConversation");
    chatDescription.textContent = t("chatWalkPrompt");
    chatInput.value = state.chatDraft;
    const empty = document.createElement("p");
    empty.className = "chat-empty";
    empty.textContent = t("chatEmpty");
    chatWindow.append(empty);
    updateActionButtons();
    return;
  }

  chatTitle.textContent = npc.name;
  chatDescription.textContent = npc.description;
  chatInput.value = state.chatDraft;

  const transcript = getNpcTranscript(npc.id);
  if (transcript.length === 0) {
    const empty = document.createElement("p");
    empty.className = "chat-empty";
    empty.textContent = t("chatStarter");
    chatWindow.append(empty);
  } else {
    for (const [speaker, text] of transcript) {
      const line = document.createElement("p");
      line.className = "chat-message";
      const label = document.createElement("strong");
      label.textContent = `${speaker === "u" ? t("youLabel") : npc.name}: `;
      line.append(label, document.createTextNode(text));
      chatWindow.append(line);
    }
  }

  chatWindow.scrollTop = chatWindow.scrollHeight;
  updateActionButtons();
}

function clearActiveChat() {
  state.activeNpcId = null;
  state.chatDraft = "";
  renderChatPanel();
}

function reconcileChatState() {
  if (!state.lore || !state.activeNpcId) {
    state.activeNpcId = null;
    state.chatDraft = "";
    return;
  }

  const activeNpc = getLoreNpcById(state.activeNpcId);
  if (!activeNpc || !state.adjacentNpcIds.has(state.activeNpcId)) {
    state.activeNpcId = null;
    state.chatDraft = "";
  }
}

function chooseAdjacentNpc() {
  if (!state.lore || !state.player) {
    return null;
  }

  const priorities = {
    "0,-1": 0,
    "1,0": 1,
    "0,1": 2,
    "-1,0": 3,
  };

  const candidates = state.lore.npcs
    .filter((npc) => Math.abs(npc.x - state.player.x) + Math.abs(npc.y - state.player.y) === 1)
    .map((npc) => ({
      npc,
      priority: priorities[`${npc.x - state.player.x},${npc.y - state.player.y}`] ?? 99,
    }))
    .sort((left, right) => left.priority - right.priority || left.npc.id.localeCompare(right.npc.id));

  return candidates[0]?.npc ?? null;
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

function getViewportMetrics() {
  const stageRect = viewportStage.getBoundingClientRect();
  const availableWidth = Math.max(stageRect.width, 1);
  const availableHeight = Math.max(stageRect.height, 1);

  let displayWidth = availableWidth;
  let displayHeight = displayWidth / MAP_ASPECT_RATIO;

  if (displayHeight > availableHeight) {
    displayHeight = availableHeight;
    displayWidth = displayHeight * MAP_ASPECT_RATIO;
  }

  if (displayWidth <= 0 || displayHeight <= 0) {
    displayWidth = state.viewport.width * (BASE_EMOJI_FONT_SIZE + BASE_TILE_GAP) - BASE_TILE_GAP;
    displayHeight = state.viewport.height * (BASE_EMOJI_FONT_SIZE + BASE_TILE_GAP) - BASE_TILE_GAP;
  }

  const widthScale = displayWidth / (
    state.viewport.width * (BASE_EMOJI_FONT_SIZE + BASE_TILE_GAP) - BASE_TILE_GAP
  );
  const heightScale = displayHeight / (
    state.viewport.height * (BASE_EMOJI_FONT_SIZE + BASE_TILE_GAP) - BASE_TILE_GAP
  );
  const scale = Math.max(Math.min(widthScale, heightScale), 0.3);
  const tileGap = BASE_TILE_GAP * scale;
  const tileSize = BASE_EMOJI_FONT_SIZE * scale;
  const tileStep = tileSize + tileGap;
  const devicePixelRatio = window.devicePixelRatio || 1;
  const canvasWidth = Math.max(Math.round(displayWidth * devicePixelRatio), 1);
  const canvasHeight = Math.max(Math.round(displayHeight * devicePixelRatio), 1);

  return {
    canvasHeight,
    canvasWidth,
    devicePixelRatio,
    displayHeight,
    displayWidth,
    tileGap,
    tileSize,
    tileStep,
  };
}

function resizeCanvas() {
  const metrics = getViewportMetrics();

  canvas.style.width = `${metrics.displayWidth}px`;
  canvas.style.height = `${metrics.displayHeight}px`;

  if (canvas.width !== metrics.canvasWidth || canvas.height !== metrics.canvasHeight) {
    canvas.width = metrics.canvasWidth;
    canvas.height = metrics.canvasHeight;
  }

  context.setTransform(
    metrics.devicePixelRatio,
    0,
    0,
    metrics.devicePixelRatio,
    0,
    0
  );

  return metrics;
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
      ? t("historyEmptyLore")
      : t("historyEmptyMap");
    historyWindow.append(empty);
    return;
  }

  for (const entry of state.historyEntries) {
    const article = document.createElement("article");
    article.className = "history-entry";

    const title = document.createElement("h3");
    title.textContent = entry.type === "world" ? t("worldLoreTitle") : entry.title;
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
  state.activeNpcId = null;
  state.chatDraft = "";
  state.npcChats = {};
}

function initializePresenceState() {
  state.currentVillageId = currentVillageAtPlayer();
  state.adjacentNpcIds = currentAdjacentNpcIds();
  reconcileChatState();
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
  state.focusTarget = "map";
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
  const metrics = resizeCanvas();
  context.clearRect(0, 0, metrics.displayWidth, metrics.displayHeight);

  if (!hasWorld()) {
    context.fillStyle = "#f7f7ec";
    context.fillRect(0, 0, metrics.displayWidth, metrics.displayHeight);
    context.fillStyle = "#5f8f33";
    context.font = `${Math.max(18, metrics.tileSize * 0.8)}px Trebuchet MS`;
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(
      t("viewportEmpty"),
      metrics.displayWidth / 2,
      metrics.displayHeight / 2
    );
    return;
  }

  const camera = cameraOrigin();

  context.fillStyle = "#f7f7ec";
  context.fillRect(0, 0, metrics.displayWidth, metrics.displayHeight);
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.font = `${metrics.tileSize}px 'Apple Color Emoji', 'Segoe UI Emoji', sans-serif`;

  for (let row = 0; row < state.viewport.height; row += 1) {
    for (let col = 0; col < state.viewport.width; col += 1) {
      const worldX = camera.left + col;
      const worldY = camera.top + row;
      const tile = state.world[worldY][worldX];
      const centerX = col * metrics.tileStep + metrics.tileSize / 2;
      const centerY = row * metrics.tileStep + metrics.tileSize / 2;

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

function scheduleViewportDraw() {
  if (resizeFrame !== null) {
    window.cancelAnimationFrame(resizeFrame);
  }

  resizeFrame = window.requestAnimationFrame(() => {
    resizeFrame = null;
    drawViewport();
  });
}

async function generateMap() {
  setBusyFlag("map", true);
  setStatus("statusGeneratingWorld");

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
    renderChatPanel();
    drawViewport();
    setStatus("statusWorldReady");
    setMapFocus();
  } catch (error) {
    console.error(error);
    setStatus("statusMapFailed");
  } finally {
    setBusyFlag("map", false);
  }
}

async function generateLore() {
  if (!hasWorld()) {
    setStatus("statusGenerateMapFirst");
    return;
  }

  setBusyFlag("lore", true);
  setStatus("statusConsultingGm");

  try {
    const response = await fetch("/api/lore/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        world: state.world,
        npcs: state.npcs,
        language: state.language,
      }),
    });
    if (!response.ok) {
      throw new Error(`Lore generation failed with ${response.status}`);
    }

    state.lore = await response.json();
    state.historyEntries = [
      createHistoryEntry("world", t("worldLoreTitle"), state.lore.worldLore),
    ];
    state.discoveredVillageIds = new Set();
    state.discoveredNpcIds = new Set();
    state.activeNpcId = null;
    state.chatDraft = "";
    state.npcChats = {};
    initializePresenceState();
    renderHistory();
    renderChatPanel();
    saveState();
    setStatus("statusLoreRecorded");
  } catch (error) {
    console.error(error);
    setStatus("statusLoreFailed");
  } finally {
    setBusyFlag("lore", false);
  }
}

function resetGame() {
  if (storageAvailable()) {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch (error) {
      console.warn("Could not clear browser storage.", error);
    }
  }

  resetRuntimeState();
  saveLanguagePreference();
  updatePlayerLabel();
  renderHistory();
  renderChatPanel();
  drawViewport();
  setStatus("statusReady");
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
    setStatus("statusBlocked");
    return;
  }

  state.player.x = nextX;
  state.player.y = nextY;
  processVillageDiscovery();
  processNpcDiscovery();
  reconcileChatState();
  saveState();
  updatePlayerLabel();
  renderChatPanel();
  drawViewport();
  setStatus("statusWorldReady");
}

async function sendChatLine() {
  const npc = getLoreNpcById(state.activeNpcId);
  const playerLine = chatInput.value.trim();
  let shouldRestoreChatFocus = false;

  if (!npc) {
    setStatus("statusPressE");
    return;
  }

  if (!state.lore) {
    setStatus("statusGenerateLoreFirst");
    return;
  }

  if (!playerLine) {
    return;
  }

  setBusyFlag("chat", true);
  state.chatDraft = "";
  chatInput.value = "";
  appendNpcTranscriptEntry(npc.id, "u", playerLine);
  renderChatPanel();
  saveState();
  setStatus("statusListening", { name: npc.name });

  try {
    const response = await fetch("/api/npc/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        npcId: npc.id,
        playerLine,
        worldLore: state.lore.worldLore,
        npc: {
          id: npc.id,
          name: npc.name,
          description: npc.description,
        },
        transcript: getNpcTranscript(npc.id),
        language: state.language,
      }),
    });
    if (!response.ok) {
      throw new Error(`NPC chat failed with ${response.status}`);
    }

    const payload = await response.json();
    appendNpcTranscriptEntry(npc.id, "n", payload.reply ?? "");
    renderChatPanel();
    saveState();
    setStatus("statusReply", { name: npc.name });
    shouldRestoreChatFocus = true;
  } catch (error) {
    console.error(error);
    setStatus("statusNpcUnavailable");
  } finally {
    setBusyFlag("chat", false);
    if (shouldRestoreChatFocus && state.activeNpcId) {
      setChatFocus();
    }
  }
}

function openAdjacentNpcChat() {
  if (!state.lore) {
    setStatus("statusGenerateLoreFirst");
    return;
  }

  const npc = chooseAdjacentNpc();
  if (!npc) {
    setStatus("statusMoveToNpc");
    return;
  }

  state.activeNpcId = npc.id;
  renderChatPanel();
  saveState();
  setChatFocus();
  setStatus("statusSpeaking", { name: npc.name });
}

generateButton.addEventListener("click", () => {
  generateMap();
});

for (const button of languageButtons) {
  button.addEventListener("click", () => {
    setLanguage(button.dataset.language ?? DEFAULT_LANGUAGE);
  });
}

generateLoreButton.addEventListener("click", () => {
  generateLore();
});

resetButton.addEventListener("click", () => {
  resetGame();
});

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendChatLine();
});

chatInput.addEventListener("input", () => {
  state.chatDraft = chatInput.value;
  saveState();
});

chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    event.preventDefault();
    clearChatDraftAndFocusMap();
    return;
  }

  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendChatLine();
  }
});

window.addEventListener("keydown", (event) => {
  if (isTypingTarget(event.target)) {
    return;
  }

  const key = event.key.toLowerCase();
  if (["w", "a", "s", "d", "e"].includes(key)) {
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
  } else if (key === "e") {
    openAdjacentNpcChat();
  }
});

window.addEventListener("resize", () => {
  scheduleViewportDraw();
});

state.language = loadSavedLanguage();
renderStaticText();

if (restoreSavedState()) {
  saveLanguagePreference();
  renderStaticText();
  initializePresenceState();
  updatePlayerLabel();
  renderHistory();
  renderChatPanel();
  drawViewport();
  setStatus("statusRestored");
  setMapFocus();
} else {
  updatePlayerLabel();
  renderHistory();
  renderChatPanel();
}

drawViewport();
updateActionButtons();
