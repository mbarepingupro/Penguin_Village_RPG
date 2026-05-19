(function () {
'use strict';

// ── CONSTANTS ────────────────────────────────────────────────────────────────
const TILE_W = 64;
const TILE_H = 32;
const GRID_SIZE = 20;

const TILE_COLORS = {
    0: "#C8DADA",
    1: "#8B7355",
    2: "#4A8FAA",
    3: "#1E4520",
    4: "#2E2E2E",
    5: "#555555",
};

const TILE_NAMES = {
    0: "SNOW",
    1: "PATH",
    2: "WATER",
    3: "TREE",
    4: "BUILDING",
    5: "FENCE",
};

const MIN_ZOOM = 0.5, MAX_ZOOM = 2.0, ZOOM_STEP = 0.1;

const BUILDING_DEFS = {
    hotel:         { name: "PENGUIN HOTEL",      color: "#C0392B", width: 3, height: 3 },
    sea_lion_pit:  { name: "ASH'S SEA LION PIT", color: "#2471A3", width: 3, height: 3 },
    club_soda:     { name: "CLUB SODA",          color: "#1E8449", width: 3, height: 2 },
    cursed_temple: { name: "CURSED TEMPLE",      color: "#7D3C98", width: 3, height: 3 },
    parkmusement:  { name: "PARKMUSEMENT",       color: "#D4AC0D", width: 3, height: 3 },
    guillotine:    { name: "GIL GUILLOTINE",     color: "#566573", width: 3, height: 2 },
    award_hall:    { name: "AWARD HALL",         color: "#D68910", width: 3, height: 3 },
    bank:          { name: "PENGUIN BANK",       color: "#1A5276", width: 3, height: 2 },
    barracks:      { name: "PENGUIN BARRACKS",   color: "#922B21", width: 3, height: 3 },
    horny_jail:    { name: "HORNY JAIL",         color: "#FF7FE5", width: 2, height: 2 },
};

const BUILDING_KEYS = Object.keys(BUILDING_DEFS);

// ── STATE ────────────────────────────────────────────────────────────────────
let grid = [];
let buildings = {};
let selectedTool = 0;
let buildingMode = false;
let selectedBuilding = null;
let showPaths = false;
let hoverGrid = null;
let isPainting = false;
let isDirty = false;
let camX, camY;
let zoomLevel = 1.0;
let canvas, ctx;
let fontReady = false;
let flashTimeout = null;

// ── COORDINATE MATH ──────────────────────────────────────────────────────────
// Returns world-space coordinates. The canvas transform (translate+scale) maps
// these to screen pixels, so drawing functions need no camera/zoom adjustments.
function gridToScreen(gx, gy) {
    return {
        x: (gx - gy) * (TILE_W / 2),
        y: (gx + gy) * (TILE_H / 2),
    };
}

function screenToGrid(sx, sy) {
    const rx = (sx - camX) / zoomLevel;
    const ry = (sy - camY) / zoomLevel;
    const gx = Math.floor((rx / (TILE_W / 2) + ry / (TILE_H / 2)) / 2);
    const gy = Math.floor((ry / (TILE_H / 2) - rx / (TILE_W / 2)) / 2);
    return { x: gx, y: gy };
}

function initCamera() {
    camX = canvas.width / 2;
    // Center the grid vertically. Grid spans world-y −16 to 624 (height 640 px
    // at zoom 1). Grid center = (GRID_SIZE-1) * TILE_H/2 = 19*16 = 304.
    camY = canvas.height / 2 - (GRID_SIZE - 1) * (TILE_H / 2);
}

function resetView() {
    zoomLevel = 1.0;
    initCamera();
}

function drawZoomIndicator() {
    const pct = Math.round(zoomLevel * 100) + '%';
    ctx.save();
    ctx.font = "8px 'Press Start 2P', monospace";
    const tw = ctx.measureText(pct).width;
    const pad = 6, bw = tw + pad * 2, bh = 20;
    const bx = canvas.width - bw - 10, by = canvas.height - bh - 10;
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(bx, by, bw, bh);
    ctx.fillStyle = '#888888';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(pct, bx + pad, by + bh / 2);
    ctx.restore();
}

function inBounds(x, y) {
    return x >= 0 && x < GRID_SIZE && y >= 0 && y < GRID_SIZE;
}

// ── COLOR HELPERS ────────────────────────────────────────────────────────────
function hexToRgb(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return { r, g, b };
}

function toHex(r, g, b) {
    return '#' + [r, g, b].map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('');
}

function lighten(hex, amt) {
    const { r, g, b } = hexToRgb(hex);
    return toHex(r + amt, g + amt, b + amt);
}

function darken(hex, amt) {
    const { r, g, b } = hexToRgb(hex);
    return toHex(r - amt, g - amt, b - amt);
}

// ── GRID INIT ────────────────────────────────────────────────────────────────
function initGrid() {
    grid = [];
    for (let y = 0; y < GRID_SIZE; y++) {
        grid.push(new Array(GRID_SIZE).fill(0));
    }
}

// ── BUILDING OCCUPANCY MAP ───────────────────────────────────────────────────
// Returns a Set of "x,y" strings for all tiles occupied by placed buildings
function getBuildingTileSet() {
    const s = new Set();
    for (const key of Object.keys(buildings)) {
        const b = buildings[key];
        for (let dy = 0; dy < b.height; dy++) {
            for (let dx = 0; dx < b.width; dx++) {
                s.add((b.gridX + dx) + ',' + (b.gridY + dy));
            }
        }
    }
    return s;
}

// Returns building key occupying tile (x,y) or null
function getBuildingAtTile(tx, ty) {
    for (const key of Object.keys(buildings)) {
        const b = buildings[key];
        if (tx >= b.gridX && tx < b.gridX + b.width &&
            ty >= b.gridY && ty < b.gridY + b.height) {
            return key;
        }
    }
    return null;
}

// ── DRAWING ──────────────────────────────────────────────────────────────────
function drawDiamondPath(sx, sy) {
    ctx.beginPath();
    ctx.moveTo(sx, sy - TILE_H / 2);
    ctx.lineTo(sx + TILE_W / 2, sy);
    ctx.lineTo(sx, sy + TILE_H / 2);
    ctx.lineTo(sx - TILE_W / 2, sy);
    ctx.closePath();
}

function drawTile(sx, sy, color, outlineColor, isHover) {
    drawDiamondPath(sx, sy);
    ctx.fillStyle = color;
    ctx.fill();

    if (isHover) {
        ctx.strokeStyle = "#FF7FE5";
        ctx.lineWidth = 2;
        ctx.stroke();
    } else {
        ctx.strokeStyle = outlineColor || "rgba(0,0,0,0.3)";
        ctx.lineWidth = 1;
        ctx.stroke();
    }
}

function drawBuilding(key, bdef) {
    const def = BUILDING_DEFS[key];
    if (!def) return;

    const gx = bdef.gridX;
    const gy = bdef.gridY;
    const gw = bdef.width;
    const gh = bdef.height;

    const gs = gridToScreen;

    const tPt = { x: gs(gx,      gy     ).x, y: gs(gx,      gy     ).y - TILE_H / 2 };
    const rPt = { x: gs(gx + gw, gy     ).x, y: gs(gx + gw, gy     ).y - TILE_H / 2 };
    const bPt = { x: gs(gx + gw, gy + gh).x, y: gs(gx + gw, gy + gh).y - TILE_H / 2 };
    const lPt = { x: gs(gx,      gy + gh).x, y: gs(gx,      gy + gh).y - TILE_H / 2 };

    const BOX_H = 32 + bdef.width * 6;
    const color = def.color;

    // Left face
    ctx.beginPath();
    ctx.moveTo(lPt.x, lPt.y + BOX_H);
    ctx.lineTo(bPt.x, bPt.y + BOX_H);
    ctx.lineTo(bPt.x, bPt.y);
    ctx.lineTo(lPt.x, lPt.y);
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = "#000000";
    ctx.lineWidth = 1;
    ctx.stroke();

    // Right face
    ctx.beginPath();
    ctx.moveTo(bPt.x, bPt.y + BOX_H);
    ctx.lineTo(rPt.x, rPt.y + BOX_H);
    ctx.lineTo(rPt.x, rPt.y);
    ctx.lineTo(bPt.x, bPt.y);
    ctx.closePath();
    ctx.fillStyle = darken(color, 40);
    ctx.fill();
    ctx.strokeStyle = "#000000";
    ctx.lineWidth = 1;
    ctx.stroke();

    // Top face
    ctx.beginPath();
    ctx.moveTo(tPt.x, tPt.y);
    ctx.lineTo(rPt.x, rPt.y);
    ctx.lineTo(bPt.x, bPt.y);
    ctx.lineTo(lPt.x, lPt.y);
    ctx.closePath();
    ctx.fillStyle = lighten(color, 50);
    ctx.fill();
    ctx.strokeStyle = "#000000";
    ctx.lineWidth = 1;
    ctx.stroke();

    // Label on top face
    if (fontReady) {
        const faceCenterX = (tPt.x + rPt.x + bPt.x + lPt.x) / 4;
        const faceCenterY = (tPt.y + rPt.y + bPt.y + lPt.y) / 4;

        ctx.save();
        ctx.shadowColor = "rgba(0,0,0,0.9)";
        ctx.shadowBlur = 3;
        ctx.fillStyle = "#FFFFFF";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.font = "7px 'Press Start 2P', monospace";

        const name = def.name;
        if (name.length > 10) {
            const mid = Math.ceil(name.length / 2);
            let splitIdx = name.lastIndexOf(' ', mid);
            if (splitIdx === -1) splitIdx = mid;
            const line1 = name.slice(0, splitIdx).trim();
            const line2 = name.slice(splitIdx).trim();
            ctx.fillText(line1, faceCenterX, faceCenterY - 5);
            ctx.fillText(line2, faceCenterX, faceCenterY + 5);
        } else {
            ctx.fillText(name, faceCenterX, faceCenterY);
        }
        ctx.restore();
    }
}

function drawBuildingFootprintPreview(key, gx, gy) {
    const def = BUILDING_DEFS[key];
    if (!def) return;

    for (let dy = 0; dy < def.height; dy++) {
        for (let dx = 0; dx < def.width; dx++) {
            const tx = gx + dx;
            const ty = gy + dy;
            if (!inBounds(tx, ty)) continue;
            const { x: sx, y: sy } = gridToScreen(tx, ty);
            // Fill with building color at 40% opacity
            drawDiamondPath(sx, sy);
            const { r, g, b } = hexToRgb(def.color);
            ctx.fillStyle = `rgba(${r},${g},${b},0.4)`;
            ctx.fill();
            ctx.strokeStyle = "#FF7FE5";
            ctx.lineWidth = 2;
            ctx.stroke();
        }
    }
}

// ── RENDER LOOP ───────────────────────────────────────────────────────────────
function render() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#1C1C1C";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Apply pan + zoom — all drawing below uses world-space coordinates
    ctx.save();
    ctx.translate(camX, camY);
    ctx.scale(zoomLevel, zoomLevel);

    const buildingTileSet = getBuildingTileSet();

    // Determine building footprint preview position (building mode)
    let previewGX = null, previewGY = null;
    if (buildingMode && selectedBuilding && hoverGrid) {
        previewGX = hoverGrid.x;
        previewGY = hoverGrid.y;
    }

    // Track which buildings have been drawn this frame
    const drawnBuildings = new Set();

    // Painter's algorithm: front-to-back diagonal order
    for (let diag = 0; diag <= 38; diag++) {
        const xiMin = Math.max(0, diag - 19);
        const xiMax = Math.min(diag, 19);
        for (let xi = xiMin; xi <= xiMax; xi++) {
            const x = xi;
            const y = diag - xi;
            if (!inBounds(x, y)) continue;

            const tileType = grid[y][x];
            const { x: sx, y: sy } = gridToScreen(x, y);

            const isHover = !buildingMode && hoverGrid && hoverGrid.x === x && hoverGrid.y === y;
            const isBuildingTile = buildingTileSet.has(x + ',' + y);

            // Draw base tile
            const tileColor = TILE_COLORS[tileType] || TILE_COLORS[0];
            drawTile(sx, sy, tileColor, "rgba(0,0,0,0.3)", isHover && !isBuildingTile);

            // Path preview overlay
            if (showPaths && !isBuildingTile) {
                const walkable = (tileType === 0 || tileType === 1);
                drawDiamondPath(sx, sy);
                ctx.fillStyle = walkable ? "rgba(74,255,107,0.25)" : "rgba(255,68,68,0.2)";
                ctx.fill();
            }

            // Draw building if this is the origin tile
            if (isBuildingTile) {
                const bKey = getBuildingAtTile(x, y);
                if (bKey && !drawnBuildings.has(bKey)) {
                    const bdef = buildings[bKey];
                    if (bdef.gridX === x && bdef.gridY === y) {
                        drawnBuildings.add(bKey);
                        drawBuilding(bKey, bdef);
                    }
                }
            }
        }
    }

    // Building footprint preview on top
    if (previewGX !== null) {
        drawBuildingFootprintPreview(selectedBuilding, previewGX, previewGY);
    }

    ctx.restore();

    // Screen-space overlay (not affected by zoom)
    drawZoomIndicator();

    requestAnimationFrame(render);
}

// ── FLOOD FILL ────────────────────────────────────────────────────────────────
function floodFill(startX, startY, targetType, fillType) {
    if (targetType === fillType) return;
    const stack = [{ x: startX, y: startY }];
    const visited = new Set();
    const buildingTileSet = getBuildingTileSet();
    let count = 0;

    while (stack.length > 0 && count < 400) {
        const { x, y } = stack.pop();
        if (!inBounds(x, y)) continue;
        const key = x + ',' + y;
        if (visited.has(key)) continue;
        if (grid[y][x] !== targetType) continue;
        if (buildingTileSet.has(key)) continue;

        visited.add(key);
        grid[y][x] = fillType;
        count++;

        stack.push({ x: x + 1, y });
        stack.push({ x: x - 1, y });
        stack.push({ x, y: y + 1 });
        stack.push({ x, y: y - 1 });
    }
}

// ── PAINT TILE ────────────────────────────────────────────────────────────────
function paintTile(gx, gy) {
    if (!inBounds(gx, gy)) return;
    // Skip tiles occupied by a building
    const buildingTileSet = getBuildingTileSet();
    if (buildingTileSet.has(gx + ',' + gy)) return;

    const paintType = (selectedTool === 'eraser') ? 0 : (typeof selectedTool === 'number' ? selectedTool : 0);

    if (selectedTool === 'fill') {
        const targetType = grid[gy][gx];
        floodFill(gx, gy, targetType, paintType);
    } else {
        grid[gy][gx] = paintType;
    }

    setDirty(true);
    updateInfoPanel();
}

// ── BUILDING PLACEMENT ────────────────────────────────────────────────────────
function placeBuilding(key, gx, gy) {
    const def = BUILDING_DEFS[key];
    if (!def) return;

    // Check bounds
    for (let dy = 0; dy < def.height; dy++) {
        for (let dx = 0; dx < def.width; dx++) {
            if (!inBounds(gx + dx, gy + dy)) return;
        }
    }

    // Remove old placement if repositioning
    if (buildings[key]) {
        removeBuilding(key, false);
    }

    // Set footprint tiles to type 4
    for (let dy = 0; dy < def.height; dy++) {
        for (let dx = 0; dx < def.width; dx++) {
            grid[gy + dy][gx + dx] = 4;
        }
    }

    buildings[key] = { gridX: gx, gridY: gy, width: def.width, height: def.height };
    setDirty(true);
    updateInfoPanel();
    rebuildBuildingsList();
}

function removeBuilding(key, markDirty = true) {
    const b = buildings[key];
    if (!b) return;

    // Reset footprint tiles to snow
    for (let dy = 0; dy < b.height; dy++) {
        for (let dx = 0; dx < b.width; dx++) {
            const tx = b.gridX + dx;
            const ty = b.gridY + dy;
            if (inBounds(tx, ty)) {
                grid[ty][tx] = 0;
            }
        }
    }

    delete buildings[key];
    if (markDirty) {
        setDirty(true);
        updateInfoPanel();
        rebuildBuildingsList();
    }
}

// ── INFO PANEL ────────────────────────────────────────────────────────────────
function updateInfoPanel() {
    let walkable = 0, path = 0, trees = 0, water = 0;
    const buildingTileSet = getBuildingTileSet();

    for (let y = 0; y < GRID_SIZE; y++) {
        for (let x = 0; x < GRID_SIZE; x++) {
            const t = grid[y][x];
            if (t === 0) walkable++;
            else if (t === 1) path++;
            else if (t === 3) trees++;
            else if (t === 2) water++;
        }
    }

    const bCount = Object.keys(buildings).length;
    const statsEl = document.getElementById('info-stats');
    const allPlacedEl = document.getElementById('info-all-placed');

    statsEl.textContent = `WALKABLE: ${walkable} | PATH: ${path} | TREES: ${trees} | WATER: ${water} | BUILDINGS: ${bCount}/10`;

    if (bCount >= 10) {
        allPlacedEl.style.display = 'inline';
    } else {
        allPlacedEl.style.display = 'none';
    }
}

// ── DIRTY STATE ──────────────────────────────────────────────────────────────
function setDirty(val) {
    isDirty = val;
    const saveBtn = document.getElementById('btn-save');
    if (val) {
        saveBtn.classList.add('dirty');
    } else {
        saveBtn.classList.remove('dirty');
    }
}

// ── FLASH MESSAGE ─────────────────────────────────────────────────────────────
function showFlash(msg, isError) {
    const el = document.getElementById('flash-msg');
    el.textContent = msg;
    el.classList.remove('error', 'visible');
    if (isError) el.classList.add('error');
    // Force reflow
    void el.offsetWidth;
    el.classList.add('visible');
    if (flashTimeout) clearTimeout(flashTimeout);
    flashTimeout = setTimeout(() => {
        el.classList.remove('visible');
    }, 2000);
}

// ── SAVE / LOAD ───────────────────────────────────────────────────────────────
async function saveLayout() {
    try {
        const resp = await fetch('/village/layout/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ grid, buildings }),
        });
        const data = await resp.json();
        if (data.status === 'success') {
            setDirty(false);
            showFlash('SAVED ✅', false);
        } else {
            showFlash('SAVE FAILED ❌', true);
        }
    } catch (e) {
        showFlash('SAVE FAILED ❌', true);
    }
}

async function loadLayout() {
    if (isDirty) {
        if (!confirm('You have unsaved changes. Load anyway?')) return;
    }
    try {
        const resp = await fetch('/village/layout');
        if (!resp.ok) throw new Error('fetch failed');
        const data = await resp.json();
        applyLayout(data);
        setDirty(false);
        updateInfoPanel();
        rebuildBuildingsList();
    } catch (e) {
        showFlash('LOAD FAILED', true);
    }
}

function applyLayout(data) {
    // Apply grid
    if (data.grid && Array.isArray(data.grid)) {
        grid = [];
        for (let y = 0; y < GRID_SIZE; y++) {
            if (data.grid[y] && Array.isArray(data.grid[y])) {
                grid.push(data.grid[y].slice(0, GRID_SIZE).map(Number));
                // Pad if needed
                while (grid[y].length < GRID_SIZE) grid[y].push(0);
            } else {
                grid.push(new Array(GRID_SIZE).fill(0));
            }
        }
        while (grid.length < GRID_SIZE) grid.push(new Array(GRID_SIZE).fill(0));
    } else {
        initGrid();
    }

    // Apply buildings
    buildings = {};
    if (data.buildings && typeof data.buildings === 'object') {
        for (const key of BUILDING_KEYS) {
            if (data.buildings[key]) {
                const b = data.buildings[key];
                if (typeof b.gridX === 'number' && typeof b.gridY === 'number') {
                    buildings[key] = {
                        gridX: b.gridX,
                        gridY: b.gridY,
                        width:  b.width  || BUILDING_DEFS[key].width,
                        height: b.height || BUILDING_DEFS[key].height,
                    };
                }
            }
        }
    }
}

function resetLayout() {
    if (!confirm('Reset to all snow? This cannot be undone.')) return;
    initGrid();
    buildings = {};
    selectedBuilding = null;
    setDirty(true);
    updateInfoPanel();
    rebuildBuildingsList();
}

// ── BUILDINGS SIDEBAR ─────────────────────────────────────────────────────────
function rebuildBuildingsList() {
    const list = document.getElementById('buildings-list');
    list.innerHTML = '';

    for (const key of BUILDING_KEYS) {
        const def = BUILDING_DEFS[key];
        const isPlaced = !!buildings[key];
        const isSelected = selectedBuilding === key;

        const item = document.createElement('div');
        item.className = 'building-item' + (isSelected ? ' selected' : '');
        item.dataset.key = key;

        const metaRow = document.createElement('div');
        metaRow.className = 'building-item-meta';

        const dot = document.createElement('span');
        dot.className = 'building-color-dot';
        dot.style.background = def.color;

        const nameEl = document.createElement('div');
        nameEl.className = 'building-item-name';
        nameEl.textContent = def.name;

        const sizeEl = document.createElement('div');
        sizeEl.className = 'building-item-size';
        sizeEl.textContent = def.width + '\xd7' + def.height;

        metaRow.appendChild(dot);
        metaRow.appendChild(sizeEl);

        if (isPlaced) {
            const placedLbl = document.createElement('span');
            placedLbl.className = 'building-placed-label';
            placedLbl.textContent = '(PLACED)';
            metaRow.appendChild(placedLbl);
        }

        item.appendChild(nameEl);
        item.appendChild(metaRow);

        item.addEventListener('click', function () {
            selectedBuilding = key;
            rebuildBuildingsList();
        });

        list.appendChild(item);
    }
}

// ── TOOLBAR SETUP ─────────────────────────────────────────────────────────────
function setupToolbar() {
    // Tile buttons
    for (let i = 0; i <= 5; i++) {
        const btn = document.getElementById('btn-tile-' + i);
        if (!btn) continue;
        btn.addEventListener('click', function () {
            if (buildingMode) {
                // Exit building mode first
                setBuildingMode(false);
            }
            selectedTool = i;
            updateToolbarActive();
        });
    }

    // Fill / Eraser
    document.getElementById('btn-tool-fill').addEventListener('click', function () {
        if (buildingMode) setBuildingMode(false);
        selectedTool = 'fill';
        updateToolbarActive();
    });

    document.getElementById('btn-tool-eraser').addEventListener('click', function () {
        if (buildingMode) setBuildingMode(false);
        selectedTool = 'eraser';
        updateToolbarActive();
    });

    // Buildings toggle
    document.getElementById('btn-buildings-toggle').addEventListener('click', function () {
        setBuildingMode(!buildingMode);
    });

    // Show paths
    document.getElementById('btn-show-paths').addEventListener('click', function () {
        showPaths = !showPaths;
        this.classList.toggle('active', showPaths);
    });

    // Load / Save / Reset layout
    document.getElementById('btn-load').addEventListener('click', loadLayout);
    document.getElementById('btn-save').addEventListener('click', saveLayout);
    document.getElementById('btn-reset').addEventListener('click', resetLayout);

    // Reset view
    document.getElementById('btn-reset-view').addEventListener('click', resetView);
}

function setBuildingMode(val) {
    buildingMode = val;
    const toggleBtn = document.getElementById('btn-buildings-toggle');
    const sidebar = document.getElementById('buildings-sidebar');
    const cvs = document.getElementById('editor-canvas');

    toggleBtn.classList.toggle('active', val);
    if (val) {
        sidebar.classList.add('visible');
        cvs.classList.add('building-mode');
        // Default select first unplaced building, or first building
        if (!selectedBuilding) {
            selectedBuilding = BUILDING_KEYS.find(k => !buildings[k]) || BUILDING_KEYS[0];
            rebuildBuildingsList();
        }
    } else {
        sidebar.classList.remove('visible');
        cvs.classList.remove('building-mode');
    }
    updateToolbarActive();
}

function updateToolbarActive() {
    // Tile buttons
    for (let i = 0; i <= 5; i++) {
        const btn = document.getElementById('btn-tile-' + i);
        if (btn) btn.classList.toggle('active', !buildingMode && selectedTool === i);
    }
    document.getElementById('btn-tool-fill').classList.toggle('active', !buildingMode && selectedTool === 'fill');
    document.getElementById('btn-tool-eraser').classList.toggle('active', !buildingMode && selectedTool === 'eraser');
}

// ── CANVAS INTERACTION ────────────────────────────────────────────────────────
function getCanvasPos(e) {
    const rect = canvas.getBoundingClientRect();
    // canvas might be CSS-scaled; map to actual pixel coords
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    return {
        x: (e.clientX - rect.left) * scaleX,
        y: (e.clientY - rect.top) * scaleY,
    };
}

function setupCanvas() {
    canvas = document.getElementById('editor-canvas');
    ctx = canvas.getContext('2d');

    function resizeCanvas() {
        const wrapper = document.getElementById('canvas-wrapper');
        const oldWidth = canvas.width;
        const oldHeight = canvas.height;
        canvas.width = wrapper.clientWidth;
        canvas.height = wrapper.clientHeight;
        // Keep the view centred when the canvas is resized
        if (oldWidth && oldHeight) {
            camX += (canvas.width - oldWidth) / 2;
            camY += (canvas.height - oldHeight) / 2;
        }
    }

    resizeCanvas();
    initCamera();
    window.addEventListener('resize', resizeCanvas);

    // Mouse move — update hover, coord display
    canvas.addEventListener('mousemove', function (e) {
        const { x, y } = getCanvasPos(e);
        const g = screenToGrid(x, y);
        if (inBounds(g.x, g.y)) {
            hoverGrid = g;
            document.getElementById('coord-display').textContent = '[' + g.x + ', ' + g.y + ']';
        } else {
            hoverGrid = null;
            document.getElementById('coord-display').textContent = '[-, -]';
        }

        // Drag paint
        if (isPainting && !buildingMode && hoverGrid) {
            paintTile(hoverGrid.x, hoverGrid.y);
        }
    });

    canvas.addEventListener('mouseleave', function () {
        hoverGrid = null;
        document.getElementById('coord-display').textContent = '[-, -]';
        isPainting = false;
    });

    canvas.addEventListener('mousedown', function (e) {
        if (e.button !== 0) return; // left click only
        e.preventDefault();

        if (!hoverGrid) return;
        const { x: gx, y: gy } = hoverGrid;

        if (buildingMode) {
            if (selectedBuilding) {
                placeBuilding(selectedBuilding, gx, gy);
            }
        } else {
            isPainting = true;
            paintTile(gx, gy);
        }
    });

    canvas.addEventListener('mouseup', function (e) {
        if (e.button === 0) isPainting = false;
    });

    canvas.addEventListener('contextmenu', function (e) {
        e.preventDefault();
        if (!hoverGrid) return;
        const { x: gx, y: gy } = hoverGrid;

        if (buildingMode) {
            const key = getBuildingAtTile(gx, gy);
            if (key) {
                removeBuilding(key);
            }
        }
    });

    // Middle-mouse pan
    let panStart = null;
    let camStartX, camStartY;

    canvas.addEventListener('mousedown', function (e) {
        if (e.button === 1) {
            e.preventDefault();
            panStart = { x: e.clientX, y: e.clientY };
            camStartX = camX;
            camStartY = camY;
        }
    });

    canvas.addEventListener('mousemove', function (e) {
        if (panStart && e.buttons & 4) {
            camX = camStartX + (e.clientX - panStart.x);
            camY = camStartY + (e.clientY - panStart.y);
        }
    });

    canvas.addEventListener('mouseup', function (e) {
        if (e.button === 1) panStart = null;
    });

    // Mouse wheel zoom toward cursor
    canvas.addEventListener('wheel', function (e) {
        e.preventDefault();
        const { x: mx, y: my } = getCanvasPos(e);
        const oldZoom = zoomLevel;
        if (e.deltaY < 0) {
            zoomLevel = Math.min(MAX_ZOOM, zoomLevel + ZOOM_STEP);
        } else {
            zoomLevel = Math.max(MIN_ZOOM, zoomLevel - ZOOM_STEP);
        }
        if (zoomLevel !== oldZoom) {
            camX = mx - (mx - camX) * (zoomLevel / oldZoom);
            camY = my - (my - camY) * (zoomLevel / oldZoom);
        }
    }, { passive: false });

    // Keyboard shortcut: R = reset view
    document.addEventListener('keydown', function (e) {
        if ((e.key === 'r' || e.key === 'R') &&
            e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
            resetView();
        }
    });
}

// ── FONT LOADING ──────────────────────────────────────────────────────────────
function loadFont() {
    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(() => { fontReady = true; });
    } else {
        // Fallback: assume ready after short delay
        setTimeout(() => { fontReady = true; }, 500);
    }
}

// ── BEFOREUNLOAD ──────────────────────────────────────────────────────────────
function setupBeforeUnload() {
    window.addEventListener('beforeunload', function (e) {
        if (isDirty) {
            e.preventDefault();
            e.returnValue = 'You have unsaved changes.';
            return e.returnValue;
        }
    });
}

// ── INIT ──────────────────────────────────────────────────────────────────────
async function init() {
    initGrid();
    setupCanvas();
    setupToolbar();
    setupBeforeUnload();
    loadFont();

    // Try to load existing layout
    try {
        const resp = await fetch('/village/layout');
        if (resp.ok) {
            const data = await resp.json();
            applyLayout(data);
        }
    } catch (e) {
        // Start with blank grid
    }

    updateInfoPanel();
    rebuildBuildingsList();
    updateToolbarActive();

    // Start render loop
    requestAnimationFrame(render);
}

// ── EXPORTS ───────────────────────────────────────────────────────────────────
window.EditorMain = { init };

})();
