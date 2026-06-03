(function () {
'use strict';

const TILE_W = 64;
const TILE_H = 32;
const GRID_SIZE = 20;

const TILE_SNOW = 0, TILE_PATH = 1, TILE_WATER = 2, TILE_TREE = 3, TILE_BUILD = 4, TILE_FENCE = 5;

const PENGUIN_FRAME_WIDTH  = 35;
const PENGUIN_FRAME_HEIGHT = 35;
const PENGUIN_FRAME_COUNT  = 2;
const PENGUIN_ANIM_SPEED   = 400; // ms per frame

const TILE_COLORS = {
    0: "#C8DADA",
    1: "#8B7355",
    2: "#4A8FAA",
    3: "#1E4520",
    4: "#2E2E2E",
    5: "#555555",
};

// ── SPRITE LOADER ─────────────────────────────────────────────────────────────
const SpriteLoader = {
    cache: {},

    load: function (path) {
        if (Object.prototype.hasOwnProperty.call(this.cache, path)) {
            return Promise.resolve(this.cache[path]);
        }
        return new Promise((resolve) => {
            const img = new Image();
            img.onload  = () => { this.cache[path] = img; resolve(img); };
            img.onerror = () => { this.cache[path] = null; resolve(null); };
            img.src = path;
        });
    },

    get: function (path) {
        return this.cache[path] || null;
    },
};

const TILE_SPRITE_NAMES = { 0: 'snow', 1: 'path', 2: 'water', 3: 'tree', 5: 'fence' };

async function loadAllSprites() {
    const tileLoads = Object.values(TILE_SPRITE_NAMES).map(
        name => SpriteLoader.load(`/static/tiles/${name}.png`)
    );
    const buildingLoads = Object.keys(buildingLayout).map(
        id => SpriteLoader.load(`/static/buildings/${id}.png`)
    );
    await Promise.all([...tileLoads, ...buildingLoads, SpriteLoader.load('/static/penguin.png')]);
}

const BUILDING_CFG = {
    hotel:         { color: "#C0392B", name: "PENGUIN HOTEL" },
    sea_lion_pit:  { color: "#2471A3", name: "SEA LION PIT" },
    club_soda:     { color: "#1E8449", name: "CLUB SODA" },
    cursed_temple: { color: "#7D3C98", name: "CURSED TEMPLE" },
    parkmusement:  { color: "#D4AC0D", name: "PARKMUSEMENT" },
    guillotine:    { color: "#566573", name: "GIL GUILLOTINE" },
    award_hall:    { color: "#D68910", name: "AWARD HALL" },
    bank:          { color: "#1A5276", name: "PENGUIN BANK" },
    barracks:      { color: "#922B21", name: "BARRACKS" },
    horny_jail:    { color: "#FF7FE5", name: "HORNY JAIL" },
    boutique:      { color: "#FF7FE5", name: "THE BOUTIQUE", noLevelBadge: true },
};

const JOB_ICONS = {
    sea_lion_pit: "🎣",
    club_soda: "🌿",
    parkmusement: "🎪",
    cursed_temple: "📿",
    guillotine: "💀",
};

let canvas, ctx, currentUser, openBuildingFn;
let _visitedTodaySet = new Set();
let cameraX = 0, cameraY = 50;
let zoomLevel = 1.0;
const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2.0;
const ZOOM_STEP = 0.1;
let _pinchDist = 0;
let grid = [];
let buildingLayout = {};
let buildingLevels = {};
let treeSeed = {};
let penguins = [];
let fontReady = false;
let _lastTime = 0;
let _time = 0;
let _popupEl = null;

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

// Returns world-space coordinates (no camera/zoom). Canvas transform handles the rest.
function gridToScreen(gx, gy) {
    return {
        x: (gx - gy) * (TILE_W / 2),
        y: (gx + gy) * (TILE_H / 2),
    };
}

// Converts screen pixel → grid cell (accounts for camera and zoom).
function screenToGrid(sx, sy) {
    const rx = (sx - cameraX) / zoomLevel;
    const ry = (sy - cameraY) / zoomLevel;
    const gx = Math.floor((rx / (TILE_W / 2) + ry / (TILE_H / 2)) / 2);
    const gy = Math.floor((ry / (TILE_H / 2) - rx / (TILE_W / 2)) / 2);
    return { x: gx, y: gy };
}

// Converts world-space point → screen pixel (used for click detection and popups).
function worldToScreen(wx, wy) {
    return { x: wx * zoomLevel + cameraX, y: wy * zoomLevel + cameraY };
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

function _placeholderDiamond(sx, sy, color) {
    ctx.beginPath();
    ctx.moveTo(sx, sy - TILE_H / 2);
    ctx.lineTo(sx + TILE_W / 2, sy);
    ctx.lineTo(sx, sy + TILE_H / 2);
    ctx.lineTo(sx - TILE_W / 2, sy);
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
}

function drawTile(sx, sy, color, tileType) {
    const spriteName = TILE_SPRITE_NAMES[tileType];
    if (spriteName) {
        const sprite = SpriteLoader.get(`/static/tiles/${spriteName}.png`);
        if (sprite) {
            ctx.drawImage(sprite, sx - TILE_W / 2, sy - TILE_H / 2, TILE_W, TILE_H);
            return;
        }
    }
    _placeholderDiamond(sx, sy, color);
}

function drawWaterTile(sx, sy, timeMs) {
    const sprite = SpriteLoader.get('/static/tiles/water.png');
    if (sprite) {
        ctx.drawImage(sprite, sx - TILE_W / 2, sy - TILE_H / 2, TILE_W, TILE_H);
        return;
    }
    _placeholderDiamond(sx, sy, "#4A8FAA");
    const shimmer = (Math.sin(timeMs * 0.002 + sx * 0.01) + 1) / 2;
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(sx, sy - TILE_H / 2);
    ctx.lineTo(sx + TILE_W / 2, sy);
    ctx.lineTo(sx, sy + TILE_H / 2);
    ctx.lineTo(sx - TILE_W / 2, sy);
    ctx.closePath();
    ctx.clip();
    ctx.fillStyle = `rgba(180,230,255,${0.15 + shimmer * 0.2})`;
    ctx.fill();
    ctx.restore();
}

function drawTree(sx, sy, seed) {
    const trunkH = 8 + (seed % 5);
    const treeH = 20 + (seed % 13);
    const trunkW = 6;

    const baseY = sy + TILE_H / 4;

    ctx.fillStyle = "#5D3A1A";
    ctx.fillRect(sx - trunkW / 2, baseY - trunkH, trunkW, trunkH);

    ctx.beginPath();
    ctx.moveTo(sx, baseY - trunkH - treeH);
    ctx.lineTo(sx + treeH * 0.45, baseY - trunkH);
    ctx.lineTo(sx - treeH * 0.45, baseY - trunkH);
    ctx.closePath();
    ctx.fillStyle = "#1E4520";
    ctx.fill();

    ctx.beginPath();
    const capH = treeH * 0.3;
    ctx.moveTo(sx, baseY - trunkH - treeH - capH * 0.4);
    ctx.lineTo(sx + capH * 0.5, baseY - trunkH - treeH + capH * 0.6);
    ctx.lineTo(sx - capH * 0.5, baseY - trunkH - treeH + capH * 0.6);
    ctx.closePath();
    ctx.fillStyle = "#D6EAF8";
    ctx.fill();
}

function drawFence(sx, sy) {
    ctx.strokeStyle = "#AAAAAA";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(sx - 12, sy);
    ctx.lineTo(sx + 12, sy);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(sx, sy - 12);
    ctx.lineTo(sx, sy + 12);
    ctx.stroke();
}

function drawBuilding(id, bdef, level) {
    const cfg = BUILDING_CFG[id];
    if (!cfg) return;

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

    // Sprite override: draw PNG if loaded, skip placeholder block
    const sprite = SpriteLoader.get(`/static/buildings/${id}.png`);
    if (sprite) {
        const anchorX = (lPt.x + bPt.x) / 2;
        const anchorY = Math.max(lPt.y, bPt.y);
        ctx.drawImage(sprite, anchorX - sprite.width / 2, anchorY - sprite.height, sprite.width, sprite.height);
    } else {
        const color = cfg.color;

        // Left face
        ctx.beginPath();
        ctx.moveTo(lPt.x, lPt.y);
        ctx.lineTo(bPt.x, bPt.y);
        ctx.lineTo(bPt.x, bPt.y - BOX_H);
        ctx.lineTo(lPt.x, lPt.y - BOX_H);
        ctx.closePath();
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = "#000000";
        ctx.lineWidth = 1;
        ctx.stroke();

        // Right face
        ctx.beginPath();
        ctx.moveTo(bPt.x, bPt.y);
        ctx.lineTo(rPt.x, rPt.y);
        ctx.lineTo(rPt.x, rPt.y - BOX_H);
        ctx.lineTo(bPt.x, bPt.y - BOX_H);
        ctx.closePath();
        ctx.fillStyle = darken(color, 40);
        ctx.fill();
        ctx.strokeStyle = "#000000";
        ctx.lineWidth = 1;
        ctx.stroke();

        // Top face
        ctx.beginPath();
        ctx.moveTo(tPt.x, tPt.y - BOX_H);
        ctx.lineTo(rPt.x, rPt.y - BOX_H);
        ctx.lineTo(bPt.x, bPt.y - BOX_H);
        ctx.lineTo(lPt.x, lPt.y - BOX_H);
        ctx.closePath();
        ctx.fillStyle = lighten(color, 50);
        ctx.fill();
        ctx.strokeStyle = "#000000";
        ctx.lineWidth = 1;
        ctx.stroke();
    }

    const faceCenterX = (tPt.x + rPt.x + bPt.x + lPt.x) / 4;
    const faceCenterY = (tPt.y + rPt.y + bPt.y + lPt.y) / 4 - BOX_H;

    if (fontReady) {
        ctx.save();
        ctx.shadowColor = "rgba(0,0,0,0.9)";
        ctx.shadowBlur = 3;
        ctx.fillStyle = "#FFFFFF";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.font = "7px 'Press Start 2P', monospace";

        const name = cfg.name;
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

        const lv = buildingLevels[id] !== undefined ? buildingLevels[id] : (level !== undefined ? level : 1);

        if (!cfg.noLevelBadge) {
            ctx.font = "10px 'Press Start 2P', monospace";
            const lvBorderColors = { 1: '#666666', 2: '#4a9eff', 3: '#FF8C00' };
            const badgeText   = lv >= 3 ? '★ MAX' : ('LV.' + lv);
            const badgeBorder = lvBorderColors[lv] || '#666666';
            const tw   = ctx.measureText(badgeText).width;
            const padX = 3, padY = 2;
            const bw   = tw + padX * 2;
            const bh   = 10 + padY * 2;
            const badgeY = faceCenterY - 22;
            const bx   = faceCenterX - bw / 2;
            const by   = badgeY - 5 - padY;

            ctx.shadowColor = 'transparent';
            ctx.shadowBlur  = 0;
            ctx.fillStyle   = '#1C1C1C';
            ctx.fillRect(bx, by, bw, bh);

            ctx.strokeStyle = badgeBorder;
            ctx.lineWidth   = 2;
            ctx.strokeRect(bx, by, bw, bh);

            if (lv >= 3) {
                const pulse = (Math.sin(_time / 200) + 1) / 2;
                ctx.shadowColor = '#FF8C00';
                ctx.shadowBlur  = 4 + pulse * 8;
            }
            ctx.fillStyle = '#ffffff';
            ctx.fillText(badgeText, faceCenterX, badgeY);
            ctx.shadowColor = 'transparent';
            ctx.shadowBlur  = 0;
        }

        ctx.restore();
    }
}

function drawPenguin(sx, sy, penguin) {
    const drawWidth  = TILE_W * 0.6;                              // ~38px world units
    const drawHeight = (PENGUIN_FRAME_HEIGHT / PENGUIN_FRAME_WIDTH) * drawWidth; // 1:1
    const drawX = sx - drawWidth / 2;
    const drawY = sy - drawHeight;                                // feet at tile centre

    // Pulsing ring for current user
    if (penguin.isCurrentUser) {
        const alpha = 0.5 + 0.5 * Math.sin(_time / 500);
        ctx.save();
        ctx.strokeStyle = `rgba(255,127,229,${alpha})`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.ellipse(sx, sy - drawHeight / 2, drawWidth / 2 + 4, drawHeight / 2 + 4, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
    }

    const sprite = SpriteLoader.get('/static/penguin.png');
    if (sprite) {
        // Frame 1: sx=0  Frame 2: sx=36  (35px wide + 1px gap)
        const frameX = penguin.animFrame * 36;
        ctx.save();
        ctx.imageSmoothingEnabled = false;
        if (!penguin.facingRight) {
            // Mirror around the sprite's centre x
            ctx.translate(sx * 2, 0);
            ctx.scale(-1, 1);
        }
        ctx.drawImage(
            sprite,
            frameX, 0, PENGUIN_FRAME_WIDTH, PENGUIN_FRAME_HEIGHT,
            drawX, drawY, drawWidth, drawHeight
        );
        ctx.restore();
    } else {
        // Fallback: simple circle
        ctx.beginPath();
        ctx.arc(sx, sy - drawHeight / 2, drawWidth / 2, 0, Math.PI * 2);
        ctx.fillStyle = penguin.body_color || '#1a1a1a';
        ctx.fill();
    }

    // Layer worn item sprites (body first so head renders on top)
    if (penguin.worn_items) {
        const DRAW_ORDER = ['body', 'feet', 'hand', 'head'];
        for (const area of DRAW_ORDER) {
            const itemId = penguin.worn_items[area];
            if (!itemId) continue;
            const spriteUrl = `/static/penguin_wearing/${area}/${itemId}.png`;
            const wornSprite = SpriteLoader.get(spriteUrl);
            if (!wornSprite) continue;
            ctx.save();
            ctx.imageSmoothingEnabled = false;
            if (!penguin.facingRight) {
                ctx.translate(sx * 2, 0);
                ctx.scale(-1, 1);
            }
            ctx.drawImage(wornSprite, drawX, drawY, drawWidth, drawHeight);
            ctx.restore();
        }
    }

    // Labels (name + title)
    if (fontReady) {
        const displayName = penguin.display_name || penguin.username;
        ctx.save();
        ctx.shadowColor = "rgba(0,0,0,0.9)";
        ctx.shadowBlur  = 3;
        ctx.textAlign   = "center";
        ctx.textBaseline = "middle";

        ctx.fillStyle = "#FFFFFF";
        ctx.font = "6px 'Press Start 2P', monospace";
        ctx.fillText(displayName, sx, drawY - 5);

        if (penguin.active_title) {
            ctx.fillStyle = "#A86EFF";
            ctx.font = "5px 'Press Start 2P', monospace";
            ctx.fillText(penguin.active_title, sx, drawY + 5);
        }

        ctx.restore();
    }

    // Job icon beside the sprite
    if (penguin.job && JOB_ICONS[penguin.job]) {
        ctx.font = "10px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(JOB_ICONS[penguin.job], sx + drawWidth / 2 + 6, sy - drawHeight / 2);
    }
}

function isWalkable(gx, gy) {
    if (gx < 0 || gx >= GRID_SIZE || gy < 0 || gy >= GRID_SIZE) return false;
    const t = grid[gy] && grid[gy][gx];
    return t === TILE_SNOW || t === TILE_PATH;
}

function getWalkableNeighbors(gx, gy) {
    const neighbors = [];
    for (const [dx, dy] of [[0,-1],[0,1],[-1,0],[1,0]]) {
        if (isWalkable(gx + dx, gy + dy)) neighbors.push({ x: gx + dx, y: gy + dy });
    }
    return neighbors;
}

function nearestWalkable(gx, gy) {
    if (isWalkable(gx, gy)) return { x: gx, y: gy };
    for (let r = 1; r < GRID_SIZE; r++) {
        for (let dx = -r; dx <= r; dx++) {
            for (let dy = -r; dy <= r; dy++) {
                if (Math.abs(dx) !== r && Math.abs(dy) !== r) continue;
                if (isWalkable(gx + dx, gy + dy)) return { x: gx + dx, y: gy + dy };
            }
        }
    }
    return { x: 0, y: 0 };
}

function randomWalkableTile() {
    const walkable = [];
    for (let y = 0; y < GRID_SIZE; y++) {
        for (let x = 0; x < GRID_SIZE; x++) {
            if (isWalkable(x, y)) walkable.push({ x, y });
        }
    }
    return walkable.length > 0 ? walkable[Math.floor(Math.random() * walkable.length)] : { x: 0, y: 0 };
}

function stepPenguin(penguin) {
    const neighbors = getWalkableNeighbors(penguin.gridX, penguin.gridY);
    if (neighbors.length === 0) return;

    let candidates = neighbors;
    if (penguin.working && penguin.homeX !== undefined) {
        // Stay within manhattan distance 4 of building home tile
        const nearby = neighbors.filter(n =>
            Math.abs(n.x - penguin.homeX) + Math.abs(n.y - penguin.homeY) <= 4
        );
        if (nearby.length > 0) candidates = nearby;
    }

    // 70% chance to prefer path tiles over snow
    const pathCandidates = candidates.filter(n => grid[n.y] && grid[n.y][n.x] === TILE_PATH);
    const target = (pathCandidates.length > 0 && Math.random() < 0.7)
        ? pathCandidates[Math.floor(Math.random() * pathCandidates.length)]
        : candidates[Math.floor(Math.random() * candidates.length)];

    penguin.targetGridX = target.x;
    penguin.targetGridY = target.y;
    penguin.progress = 0;

    if (target.x > penguin.gridX)      penguin.facingRight = true;
    else if (target.x < penguin.gridX) penguin.facingRight = false;
    // y-only movement: keep current facing
}

function updatePenguins(dt) {
    const now = performance.now();
    for (const p of penguins) {
        if (p.progress < 1) {
            p.progress = Math.min(1, p.progress + dt / 1000);
            p.isMoving = true;
            if (now - p.lastFrameTime > PENGUIN_ANIM_SPEED) {
                p.animFrame    = (p.animFrame + 1) % PENGUIN_FRAME_COUNT;
                p.lastFrameTime = now;
            }
        } else {
            p.gridX    = p.targetGridX;
            p.gridY    = p.targetGridY;
            p.isMoving = false;
            p.animFrame = 0;
            p.nextMoveIn -= dt;
            if (p.nextMoveIn <= 0) {
                stepPenguin(p);
                p.nextMoveIn = 2000 + Math.random() * 2000;
            }
        }
    }
}

function mergePenguins(incoming) {
    const existingMap = {};
    for (const p of penguins) {
        existingMap[p.username] = p;
    }

    const incomingNames = new Set();
    for (const p of incoming) {
        incomingNames.add(p.username);
        if (existingMap[p.username]) {
            const ep = existingMap[p.username];
            ep.job = p.job;
            ep.active_title = p.active_title;
            ep.level = p.level;
            ep.prestige = p.prestige;
            ep.working = !!p.job;
            ep.isCurrentUser = p.username === currentUser;
            ep.worn_items = p.worn_items || {};
        } else {
            let spawn;
            if (p.startGridX !== undefined) {
                // Working penguin — snap building home tile to nearest walkable
                spawn = nearestWalkable(p.startGridX, p.startGridY);
            } else {
                // Resting penguin — pick any walkable tile on the map
                spawn = randomWalkableTile();
            }
            const gx = spawn.x, gy = spawn.y;
            existingMap[p.username] = {
                username: p.username,
                job: p.job,
                active_title: p.active_title,
                level: p.level,
                prestige: p.prestige,
                isCurrentUser: p.username === currentUser,
                gridX: gx,
                gridY: gy,
                targetGridX: gx,
                targetGridY: gy,
                progress: 1,
                nextMoveIn: 2000 + Math.random() * 3000,
                homeX: p.homeX !== undefined ? p.homeX : gx,
                homeY: p.homeY !== undefined ? p.homeY : gy,
                working: !!p.job,
                animFrame: 0,
                lastFrameTime: performance.now(),
                facingRight: true,
                isMoving: false,
                worn_items: p.worn_items || {},
            };
        }
    }

    penguins = Object.values(existingMap).filter(p => incomingNames.has(p.username));
}

function loadPenguins() {
    fetch('/village/penguins')
        .then(r => r.json())
        .then(data => mergePenguins(data.penguins || []))
        .catch(() => {});
}

function resizeCanvas() {
    const parent = canvas.parentElement;
    canvas.width = parent.clientWidth;
    canvas.height = parent.clientHeight;
    initCamera();
}

function initCamera() {
    cameraX = canvas.width / 2;
    cameraY = 50;
}

function showPenguinPopup(penguin, sx, sy) {
    if (_popupEl && _popupEl.parentElement) {
        _popupEl.parentElement.removeChild(_popupEl);
    }

    const container = canvas.parentElement;
    const containerRect = container.getBoundingClientRect();
    const canvasRect = canvas.getBoundingClientRect();

    const el = document.createElement('div');
    el.style.cssText = [
        'position:absolute',
        'background:#1C1C1C',
        'border:2px solid #A86EFF',
        'padding:8px 10px',
        "font-family:'Press Start 2P',monospace",
        'font-size:7px',
        'color:#FFFFFF',
        'pointer-events:auto',
        'z-index:200',
        'line-height:1.8',
        'white-space:nowrap',
        'cursor:default',
    ].join(';');

    const jobIcon = penguin.job ? (JOB_ICONS[penguin.job] || '') : '';
    const jobName = penguin.job ? penguin.job.replace(/_/g, ' ').toUpperCase() : 'UNEMPLOYED';
    const isSelf  = penguin.username === currentUser;
    const visited = _visitedTodaySet.has(penguin.username);

    let visitBtnHtml = '';
    if (!isSelf) {
        if (visited) {
            visitBtnHtml = '<div style="margin-top:6px;color:#4aff6b;font-size:6px;">VISITED TODAY ✅</div>';
        } else {
            visitBtnHtml = '<button id="map-visit-btn" style="margin-top:6px;display:block;width:100%;'
                + "font-family:'Press Start 2P',monospace;font-size:6px;padding:4px 6px;"
                + 'background:#1C1C1C;color:#A86EFF;border:1px solid #A86EFF;cursor:pointer;" '
                + 'onmouseenter="this.style.background=\'#A86EFF\';this.style.color=\'#1C1C1C\'" '
                + 'onmouseleave="this.style.background=\'#1C1C1C\';this.style.color=\'#A86EFF\'" '
                + 'onclick="window._mapVisitIgloo && window._mapVisitIgloo(\'' + penguin.username + '\')">'
                + '🏠 VISIT IGLOO</button>';
        }
    }

    el.innerHTML = [
        '<div style="color:#FFFFFF">' + (penguin.display_name || penguin.username) + '</div>',
        penguin.active_title ? '<div style="color:#A86EFF">' + penguin.active_title + '</div>' : '',
        '<div style="color:#888">LV' + (penguin.level || 1) + ' · ' + jobIcon + ' ' + jobName + '</div>',
        visitBtnHtml,
    ].join('');

    const popupX = (canvasRect.left - containerRect.left) + sx - 70;
    const popupY = (canvasRect.top - containerRect.top) + sy - (isSelf ? 70 : 95);

    el.style.left = Math.max(0, popupX) + 'px';
    el.style.top  = Math.max(0, popupY) + 'px';

    container.appendChild(el);
    _popupEl = el;

    let _autoClose = setTimeout(() => {
        if (el.parentElement) el.parentElement.removeChild(el);
        if (_popupEl === el) _popupEl = null;
    }, 4000);

    el.addEventListener('mouseenter', () => clearTimeout(_autoClose));
    el.addEventListener('mouseleave', () => {
        _autoClose = setTimeout(() => {
            if (el.parentElement) el.parentElement.removeChild(el);
            if (_popupEl === el) _popupEl = null;
        }, 1500);
    });
}

function getBuildingAtTile(gx, gy) {
    for (const [id, bdef] of Object.entries(buildingLayout)) {
        if (
            gx >= bdef.gridX && gx < bdef.gridX + bdef.width &&
            gy >= bdef.gridY && gy < bdef.gridY + bdef.height
        ) {
            return id;
        }
    }
    return null;
}

function _pointInPoly(px, py, pts) {
    let inside = false;
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
        const xi = pts[i].x, yi = pts[i].y, xj = pts[j].x, yj = pts[j].y;
        if (((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi))
            inside = !inside;
    }
    return inside;
}

// Returns the building id whose rendered 3D block contains world-space point (wx, wy).
function getBuildingAtScreenPos(wx, wy) {
    const sorted = Object.entries(buildingLayout).sort(
        ([, a], [, b]) => (b.gridX + b.gridY) - (a.gridX + a.gridY)
    );
    for (const [id, bdef] of sorted) {
        const gs = gridToScreen;
        const gx = bdef.gridX, gy = bdef.gridY, gw = bdef.width, gh = bdef.height;
        const BOX_H = 32 + gw * 6;
        const tPt = { x: gs(gx,    gy   ).x, y: gs(gx,    gy   ).y - TILE_H / 2 };
        const rPt = { x: gs(gx+gw, gy   ).x, y: gs(gx+gw, gy   ).y - TILE_H / 2 };
        const bPt = { x: gs(gx+gw, gy+gh).x, y: gs(gx+gw, gy+gh).y - TILE_H / 2 };
        const lPt = { x: gs(gx,    gy+gh).x, y: gs(gx,    gy+gh).y - TILE_H / 2 };
        // Six-point outline enclosing top face + both visible walls
        const poly = [
            { x: tPt.x, y: tPt.y - BOX_H },
            { x: rPt.x, y: rPt.y - BOX_H },
            { x: rPt.x, y: rPt.y },
            { x: bPt.x, y: bPt.y },
            { x: lPt.x, y: lPt.y },
            { x: lPt.x, y: lPt.y - BOX_H },
        ];
        if (_pointInPoly(wx, wy, poly)) return id;
    }
    return null;
}

function attachEvents() {
    let isDragging = false;
    let _clickValid = false;
    let dragStartX = 0, dragStartY = 0;
    let camStartX = 0, camStartY = 0;
    let mouseMoveHandler = null;
    let mouseUpHandler = null;

    canvas.addEventListener('mousedown', function (e) {
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        camStartX = cameraX;
        camStartY = cameraY;
        isDragging = false;
        _clickValid = true;
        canvas.style.cursor = 'grabbing';

        mouseMoveHandler = function (me) {
            const dx = me.clientX - dragStartX;
            const dy = me.clientY - dragStartY;
            if (Math.abs(dx) > 4 || Math.abs(dy) > 4) {
                isDragging = true;
                _clickValid = false;
            }
            if (isDragging) {
                cameraX = camStartX + dx;
                cameraY = camStartY + dy;
            }
        };

        mouseUpHandler = function () {
            canvas.style.cursor = 'grab';
            document.removeEventListener('mousemove', mouseMoveHandler);
            document.removeEventListener('mouseup', mouseUpHandler);
        };

        document.addEventListener('mousemove', mouseMoveHandler);
        document.addEventListener('mouseup', mouseUpHandler);
    });

    canvas.addEventListener('click', function (e) {
        if (!_clickValid) return;

        const rect = canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;

        for (const p of penguins) {
            const interp = {
                x: p.gridX + (p.targetGridX - p.gridX) * p.progress,
                y: p.gridY + (p.targetGridY - p.gridY) * p.progress,
            };
            const wpos = gridToScreen(interp.x, interp.y);
            const spos = worldToScreen(wpos.x, wpos.y);
            const dist = Math.sqrt((sx - spos.x) ** 2 + (sy - spos.y) ** 2);
            if (dist <= 16) {
                showPenguinPopup(p, spos.x, spos.y);
                return;
            }
        }

        const g = screenToGrid(sx, sy);
        let bid = (g.x >= 0 && g.x < GRID_SIZE && g.y >= 0 && g.y < GRID_SIZE)
            ? getBuildingAtTile(g.x, g.y) : null;
        if (!bid) {
            const wx = (sx - cameraX) / zoomLevel;
            const wy = (sy - cameraY) / zoomLevel;
            bid = getBuildingAtScreenPos(wx, wy);
        }
        if (bid && openBuildingFn) openBuildingFn(bid);
    });

    let touchStartX = 0, touchStartY = 0;
    let touchCamX = 0, touchCamY = 0;
    let touchMoved = false;

    canvas.addEventListener('touchstart', function (e) {
        if (e.touches.length === 1) {
            touchStartX = e.touches[0].clientX;
            touchStartY = e.touches[0].clientY;
            touchCamX = cameraX;
            touchCamY = cameraY;
            touchMoved = false;
        }
    }, { passive: true });

    canvas.addEventListener('touchmove', function (e) {
        if (e.touches.length === 2) {
            e.preventDefault();
            const dx = e.touches[0].clientX - e.touches[1].clientX;
            const dy = e.touches[0].clientY - e.touches[1].clientY;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (_pinchDist > 0) {
                const delta = dist - _pinchDist;
                zoomLevel = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoomLevel + delta * 0.005));
            }
            _pinchDist = dist;
        } else if (e.touches.length === 1) {
            const dx = e.touches[0].clientX - touchStartX;
            const dy = e.touches[0].clientY - touchStartY;
            if (Math.abs(dx) > 4 || Math.abs(dy) > 4) {
                touchMoved = true;
                cameraX = touchCamX + dx;
                cameraY = touchCamY + dy;
            }
        }
    }, { passive: false });

    canvas.addEventListener('touchend', function (e) {
        _pinchDist = 0;
        if (!touchMoved && e.changedTouches.length === 1) {
            const rect = canvas.getBoundingClientRect();
            const sx = e.changedTouches[0].clientX - rect.left;
            const sy = e.changedTouches[0].clientY - rect.top;

            for (const p of penguins) {
                const interp = {
                    x: p.gridX + (p.targetGridX - p.gridX) * p.progress,
                    y: p.gridY + (p.targetGridY - p.gridY) * p.progress,
                };
                const wpos = gridToScreen(interp.x, interp.y);
                const spos = worldToScreen(wpos.x, wpos.y);
                const dist = Math.sqrt((sx - spos.x) ** 2 + (sy - spos.y) ** 2);
                if (dist <= 16) {
                    showPenguinPopup(p, spos.x, spos.y);
                    return;
                }
            }

            const g = screenToGrid(sx, sy);
            let bid = (g.x >= 0 && g.x < GRID_SIZE && g.y >= 0 && g.y < GRID_SIZE)
                ? getBuildingAtTile(g.x, g.y) : null;
            if (!bid) {
                const wx = (sx - cameraX) / zoomLevel;
                const wy = (sy - cameraY) / zoomLevel;
                bid = getBuildingAtScreenPos(wx, wy);
            }
            if (bid && openBuildingFn) openBuildingFn(bid);
        }
    });

    // Wheel zoom — zoom toward mouse position
    canvas.addEventListener('wheel', function (e) {
        e.preventDefault();
        const oldZoom = zoomLevel;
        if (e.deltaY < 0) {
            zoomLevel = Math.min(MAX_ZOOM, zoomLevel + ZOOM_STEP);
        } else {
            zoomLevel = Math.max(MIN_ZOOM, zoomLevel - ZOOM_STEP);
        }
        if (zoomLevel !== oldZoom) {
            const rect = canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            cameraX = mouseX - (mouseX - cameraX) * (zoomLevel / oldZoom);
            cameraY = mouseY - (mouseY - cameraY) * (zoomLevel / oldZoom);
        }
    }, { passive: false });

    // Double-click to reset zoom and re-center
    canvas.addEventListener('dblclick', function () {
        zoomLevel = 1.0;
        initCamera();
    });
}

function gameLoop(ts) {
    const dt = Math.min(ts - _lastTime, 100);
    _lastTime = ts;
    _time += dt;

    ctx.fillStyle = "#E8F0F0";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Apply pan + zoom transform for world rendering
    ctx.save();
    ctx.imageSmoothingEnabled = false;
    ctx.translate(cameraX, cameraY);
    ctx.scale(zoomLevel, zoomLevel);

    const margin = TILE_W * 2;
    for (let diag = 0; diag < 2 * GRID_SIZE - 1; diag++) {
        for (let xi = Math.max(0, diag - GRID_SIZE + 1); xi <= Math.min(diag, GRID_SIZE - 1); xi++) {
            const x = xi;
            const y = diag - xi;
            const pos = gridToScreen(x, y);

            // Cull in screen space
            const sx = pos.x * zoomLevel + cameraX;
            const sy = pos.y * zoomLevel + cameraY;
            if (sx < -margin || sx > canvas.width + margin ||
                sy < -TILE_H * 4 || sy > canvas.height + 80) continue;

            const tileType = (grid[y] && grid[y][x] !== undefined) ? grid[y][x] : TILE_SNOW;

            if (tileType === TILE_WATER) {
                drawWaterTile(pos.x, pos.y, _time);
            } else {
                drawTile(pos.x, pos.y, TILE_COLORS[tileType] || TILE_COLORS[0], tileType);
            }

            if (tileType === TILE_TREE) {
                const key = x + ',' + y;
                const seed = treeSeed[key] || 0;
                drawTree(pos.x, pos.y, seed);
            } else if (tileType === TILE_FENCE) {
                drawFence(pos.x, pos.y);
            }
        }
    }

    const sortedBuildings = Object.entries(buildingLayout).sort(([, a], [, b]) =>
        (a.gridX + a.gridY) - (b.gridX + b.gridY)
    );
    for (const [id, bdef] of sortedBuildings) {
        const level = buildingLevels[id] !== undefined ? buildingLevels[id] : 1;
        drawBuilding(id, bdef, level);
    }

    updatePenguins(dt);

    const sortedPenguins = penguins.slice().sort((a, b) => {
        const aSort = (a.gridX + (a.targetGridX - a.gridX) * a.progress) + (a.gridY + (a.targetGridY - a.gridY) * a.progress);
        const bSort = (b.gridX + (b.targetGridX - b.gridX) * b.progress) + (b.gridY + (b.targetGridY - b.gridY) * b.progress);
        return aSort - bSort;
    });

    for (const p of sortedPenguins) {
        const ix = p.gridX + (p.targetGridX - p.gridX) * p.progress;
        const iy = p.gridY + (p.targetGridY - p.gridY) * p.progress;
        const pos = gridToScreen(ix, iy);
        drawPenguin(pos.x, pos.y, p);
    }

    ctx.restore();

    // HUD (screen space, drawn on top)
    drawZoomIndicator();

    requestAnimationFrame(gameLoop);
}

function initEngine(canvasEl, username, openBuildingCallback) {
    canvas = canvasEl;
    ctx = canvas.getContext('2d');
    currentUser = username;
    openBuildingFn = openBuildingCallback;

    document.fonts.ready.then(function () { fontReady = true; });

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    fetch('/village/layout')
        .then(r => r.json())
        .then(data => {
            grid = data.grid || [];
            buildingLayout = data.buildings || {};
            buildingLevels = data.building_levels || {};

            treeSeed = {};
            for (let y = 0; y < GRID_SIZE; y++) {
                for (let x = 0; x < GRID_SIZE; x++) {
                    if (grid[y] && grid[y][x] === TILE_TREE) {
                        treeSeed[x + ',' + y] = Math.floor(Math.random() * 256);
                    }
                }
            }

            initCamera();
            _lastTime = performance.now();
            requestAnimationFrame(gameLoop);

            loadAllSprites();
            loadPenguins();
            setInterval(loadPenguins, 30000);
        })
        .catch(err => {
            console.error('Failed to load village layout:', err);
        });

    attachEvents();
}

function updateBuildingLevels(levels) {
    buildingLevels = Object.assign(buildingLevels, levels);
}

function resizeViewport() {
    if (!canvas) return;
    const parent = canvas.parentElement;
    canvas.width  = parent.clientWidth;
    canvas.height = parent.clientHeight;
}

function setVisitedToday(usernameList) {
    _visitedTodaySet = new Set(usernameList || []);
}

window.VillageMap = { init: initEngine, updateBuildingLevels, resize: resizeViewport, setVisitedToday };

})();
