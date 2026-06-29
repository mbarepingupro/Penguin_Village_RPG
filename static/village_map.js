(function () {
'use strict';

const TILE_W = 64;
const TILE_H = 32;
const GRID_SIZE = 40;

const TILE_SNOW = 0, TILE_PATH = 1, TILE_WATER = 2, TILE_TREE = 3, TILE_BUILD = 4, TILE_FENCE = 5, TILE_EXPAND = 6;

// Maps visual area names (from worn_items API) to sprite folder names on disk
const _AREA_FOLDER = { head: 'hats', body: 'outfits', feet: 'footwear', hand: 'accessories' };

const SHAPE_CONFIG = {
    "normal": { frameWidth: 32, frameHeight: 40, stripFile: "penguin_normal.png", staticFile: "penguin_normal_static.png" },
    "tall":   { frameWidth: 32, frameHeight: 50, stripFile: "penguin_tall.png",   staticFile: "penguin_tall_static.png"   },
};
window.SHAPE_CONFIG = SHAPE_CONFIG;

const PENGUIN_FRAME_COUNT  = 2;
const PENGUIN_ANIM_SPEED   = 400; // ms per frame

const TILE_COLORS = {
    0: "#C8DADA",
    1: "#8B7355",
    6: "#1a1a25",
    2: "#4A8FAA",
    3: "#1E4520",
    4: "#252535",
    5: "#8888A8",
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

// ── PENGUIN RECOLORING — defined in /static/recolor.js, loaded before this file ──

async function loadPenguinSprites() {
    for (const [shape, cfg] of Object.entries(SHAPE_CONFIG)) {
        const stripLoaded  = await SpriteLoader.load(`/static/${cfg.stripFile}`);
        const staticLoaded = await SpriteLoader.load(`/static/${cfg.staticFile}`);
        if (shape === 'normal') {
            // Alias legacy filenames so old code paths still work
            if (!stripLoaded) {
                const legacy = await SpriteLoader.load('/static/penguin.png');
                SpriteLoader.cache[`/static/${cfg.stripFile}`] = legacy;
            }
            if (!staticLoaded) {
                const legacy = await SpriteLoader.load('/static/penguin_static.png');
                SpriteLoader.cache[`/static/${cfg.staticFile}`] = legacy;
            }
        }
    }
}

async function loadAllSprites() {
    const tileLoads     = Object.values(TILE_SPRITE_NAMES).map(name => SpriteLoader.load(`/static/tiles/${name}.png`));
    const buildingLoads = Object.keys(buildingLayout).map(id => SpriteLoader.load(`/static/buildings/${id}.png`));
    await Promise.all([...tileLoads, ...buildingLoads]);
    await loadPenguinSprites();
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
let _moveTarget    = null;  // { wx, wy, born }
let _invalidTarget = null;  // { wx, wy, born }

const EXPANSION_LABELS = [
    { gridX: 2,  gridY: 2,  text: ['NORTHERN', 'FRONTIER'], era: 'ERA 2' },
    { gridX: 26, gridY: 2,  text: ['FROZEN',   'PEAKS'    ], era: 'ERA 3' },
    { gridX: 2,  gridY: 26, text: ['SOUTHERN', 'SHORES'   ], era: 'ERA 2' },
    { gridX: 26, gridY: 26, text: ['THE',      'ABYSS'    ], era: 'ERA 4' },
];
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
let _highlightedBuilding = null;

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
    ctx.font = "17px 'Pixelify Sans', monospace";
    const tw = ctx.measureText(pct).width;
    const pad = 6, bw = tw + pad * 2, bh = 20;
    const bx = canvas.width - bw - 10, by = canvas.height - bh - 10;
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillRect(bx, by, bw, bh);
    ctx.fillStyle = '#B8B8D0';
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

function drawExpansionTile(sx, sy) {
    // Dark fill
    ctx.beginPath();
    ctx.moveTo(sx, sy - TILE_H / 2);
    ctx.lineTo(sx + TILE_W / 2, sy);
    ctx.lineTo(sx, sy + TILE_H / 2);
    ctx.lineTo(sx - TILE_W / 2, sy);
    ctx.closePath();
    ctx.fillStyle = '#1a1a25';
    ctx.fill();
    // Dashed border
    ctx.save();
    ctx.setLineDash([3, 4]);
    ctx.strokeStyle = '#3A3A50';
    ctx.lineWidth = 0.8;
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
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
        // Scale sprite to match the isometric footprint width; anchor bottom-center
        // to the raw (no TILE_H/2 offset) front corner so it sits on the tiles.
        const footprintWidth = rPt.x - lPt.x;
        const frontX = (lPt.x + rPt.x) / 2;
        // bPt is the front/bottom corner of the footprint diamond; sprite bottom sits here.
        const frontY = bPt.y;
        const spriteScale = footprintWidth / sprite.width;
        const drawWidth   = sprite.width  * spriteScale;
        const drawHeight  = sprite.height * spriteScale;
        const drawX = frontX - drawWidth  / 2;
        const drawY = frontY - drawHeight;
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(sprite, drawX, drawY, drawWidth, drawHeight);
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
        ctx.font = "14px 'Pixelify Sans', monospace";

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
            ctx.font = "14px 'Pixelify Sans', monospace";
            const lvBorderColors = { 1: '#8888A8', 2: '#4a9eff', 3: '#FF8C00' };
            const badgeText   = lv >= 3 ? '★ MAX' : ('LV.' + lv);
            const badgeBorder = lvBorderColors[lv] || '#8888A8';
            const tw   = ctx.measureText(badgeText).width;
            const padX = 3, padY = 2;
            const bw   = tw + padX * 2;
            const bh   = 10 + padY * 2;
            const badgeY = faceCenterY - 22;
            const bx   = faceCenterX - bw / 2;
            const by   = badgeY - 5 - padY;

            ctx.shadowColor = 'transparent';
            ctx.shadowBlur  = 0;
            ctx.fillStyle   = '#181820';
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

    // Tutorial building highlight
    if (_highlightedBuilding === id) {
        const pulse = (Math.sin(_time / 300) + 1) / 2;
        const glow  = Math.floor(160 + pulse * 95);

        ctx.save();
        ctx.beginPath();
        ctx.moveTo(tPt.x, tPt.y - BOX_H);
        ctx.lineTo(rPt.x, rPt.y - BOX_H);
        ctx.lineTo(rPt.x, rPt.y);
        ctx.lineTo(bPt.x, bPt.y);
        ctx.lineTo(lPt.x, lPt.y);
        ctx.lineTo(lPt.x, lPt.y - BOX_H);
        ctx.closePath();
        ctx.strokeStyle = `rgb(255,${glow},0)`;
        ctx.lineWidth   = 3 + pulse * 2;
        ctx.shadowColor = `rgba(255,140,0,${0.4 + pulse * 0.4})`;
        ctx.shadowBlur  = 12 + pulse * 12;
        ctx.stroke();
        ctx.restore();

        // Bouncing arrow above building
        const arrowX = faceCenterX;
        const arrowY = faceCenterY - 30 - Math.abs(Math.sin(_time / 400)) * 8;
        ctx.save();
        ctx.font       = "27px sans-serif";
        ctx.textAlign  = "center";
        ctx.textBaseline = "bottom";
        ctx.shadowColor = "rgba(0,0,0,0.8)";
        ctx.shadowBlur  = 4;
        ctx.fillText("▼", arrowX, arrowY);
        ctx.restore();
    }
}

function _drawPenguinSprite(sx, sy, penguin, drawX, drawY, drawWidth, drawHeight) {
    const shape     = penguin.penguin_shape || 'normal';
    const cfg       = SHAPE_CONFIG[shape] || SHAPE_CONFIG['normal'];
    const bodyColor = penguin.penguin_color || '#1a1a1a';
    const baseSprite = SpriteLoader.get(`/static/${cfg.stripFile}`)
                    || SpriteLoader.get('/static/penguin.png');
    if (baseSprite) {
        const spriteKey = `penguin_${shape}`;
        const recolored = getRecoloredSprite(spriteKey, baseSprite, bodyColor);
        const frameX    = penguin.animFrame * cfg.frameWidth;
        ctx.save();
        ctx.imageSmoothingEnabled = false;
        if (!penguin.facingRight) {
            ctx.translate(sx * 2, 0);
            ctx.scale(-1, 1);
        }
        ctx.drawImage(
            recolored,
            frameX, 0, cfg.frameWidth, cfg.frameHeight,
            drawX, drawY, drawWidth, drawHeight
        );
        ctx.restore();
    } else {
        ctx.beginPath();
        ctx.arc(sx, sy - drawHeight / 2, drawWidth / 2, 0, Math.PI * 2);
        ctx.fillStyle = bodyColor;
        ctx.fill();
    }
}

function drawPenguin(sx, sy, penguin, isBehind) {
    const shape  = penguin.penguin_shape || 'normal';
    const cfg    = SHAPE_CONFIG[shape] || SHAPE_CONFIG['normal'];
    const drawWidth  = TILE_W * 0.6;
    const drawHeight = (cfg.frameHeight / cfg.frameWidth) * drawWidth;
    const drawX = sx - drawWidth / 2;
    const drawY = sy - drawHeight;

    if (isBehind) {
        // Draw as a semi-transparent dark silhouette
        const supportsFilter = typeof ctx.filter !== 'undefined';
        ctx.save();
        ctx.globalAlpha = 0.35;
        ctx.imageSmoothingEnabled = false;
        if (supportsFilter) ctx.filter = 'brightness(0.2) saturate(0)';
        _drawPenguinSprite(sx, sy, penguin, drawX, drawY, drawWidth, drawHeight);
        // Layer worn items in the same silhouette pass
        if (penguin.worn_items) {
            const shape2 = penguin.penguin_shape || 'normal';
            const cfg2   = SHAPE_CONFIG[shape2] || SHAPE_CONFIG['normal'];
            const frameX2 = (penguin.animFrame || 0) * cfg2.frameWidth;
            for (const area of ['body', 'feet', 'hand', 'head']) {
                const itemId = penguin.worn_items[area];
                if (!itemId) continue;
                const folder = _AREA_FOLDER[area] || area;
                const wornSprite = SpriteLoader.get(`/static/penguin_wearing/${shape2}/${folder}/${itemId}.png`)
                                || SpriteLoader.get(`/static/penguin_wearing/${folder}/${itemId}.png`);
                if (!wornSprite) continue;
                ctx.drawImage(wornSprite, frameX2, 0, cfg2.frameWidth, cfg2.frameHeight, drawX, drawY, drawWidth, drawHeight);
            }
        }
        if (supportsFilter) ctx.filter = 'none';
        ctx.restore();

        // 📍 indicator above the occluding building for the current player only
        if (penguin.isCurrentUser && fontReady) {
            ctx.save();
            ctx.font = '20px serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'bottom';
            ctx.fillText('📍', sx, drawY - 6);
            ctx.restore();
        }
        return;
    }

    // ── Normal rendering ─────────────────────────────────────────────────────

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

    _drawPenguinSprite(sx, sy, penguin, drawX, drawY, drawWidth, drawHeight);

    // Layer worn item sprites using the current animation frame
    if (penguin.worn_items) {
        const shape = penguin.penguin_shape || 'normal';
        const cfg   = SHAPE_CONFIG[shape] || SHAPE_CONFIG['normal'];
        const frameX = (penguin.animFrame || 0) * cfg.frameWidth;
        const DRAW_ORDER = ['body', 'feet', 'hand', 'head'];
        for (const area of DRAW_ORDER) {
            const itemId = penguin.worn_items[area];
            if (!itemId) continue;
            const folder    = _AREA_FOLDER[area] || area;
            const shapedUrl = `/static/penguin_wearing/${shape}/${folder}/${itemId}.png`;
            const legacyUrl = `/static/penguin_wearing/${folder}/${itemId}.png`;
            if (!SpriteLoader.get(shapedUrl) && !SpriteLoader.get(legacyUrl)) {
                SpriteLoader.load(shapedUrl).then(img => { if (!img) SpriteLoader.load(legacyUrl); });
            }
            const wornSprite = SpriteLoader.get(shapedUrl) || SpriteLoader.get(legacyUrl);
            if (!wornSprite) continue;
            ctx.save();
            ctx.imageSmoothingEnabled = false;
            if (!penguin.facingRight) {
                ctx.translate(sx * 2, 0);
                ctx.scale(-1, 1);
            }
            ctx.drawImage(wornSprite, frameX, 0, cfg.frameWidth, cfg.frameHeight, drawX, drawY, drawWidth, drawHeight);
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

        ctx.font = "14px 'Pixelify Sans', monospace";
        ctx.fillStyle = "#FFFFFF";
        ctx.fillText(displayName, sx, drawY - 5);

        if (penguin.active_title) {
            ctx.font = "14px 'Pixelify Sans', monospace";
            ctx.fillStyle = "#FF8C00";
            ctx.fillText(penguin.active_title, sx, drawY + 5);
        }

        ctx.restore();
    }

    // Job icon beside the sprite
    if (penguin.job && JOB_ICONS[penguin.job]) {
        ctx.font = "17px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(JOB_ICONS[penguin.job], sx + drawWidth / 2 + 6, sy - drawHeight / 2);
    }
}

function isPenguinBehindBuilding(penguinX, penguinY) {
    for (const [, bdef] of Object.entries(buildingLayout)) {
        const bLeft   = bdef.gridX;
        const bRight  = bdef.gridX + bdef.width;
        const bTop    = bdef.gridY;
        const bBottom = bdef.gridY + bdef.height;
        // Penguin is visually occluded when its X falls within the building's column range
        // and its Y is closer to the back (smaller) than the building's front edge.
        if (penguinX >= bLeft  - 0.5 && penguinX <= bRight  + 0.5 &&
            penguinY >= bTop   - 1   && penguinY  <  bBottom - 0.5) {
            return true;
        }
    }
    return false;
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

// BFS pathfinding — returns array of {x,y} steps (not including start), or null if unreachable
function findPath(sx, sy, ex, ey) {
    if (!isWalkable(ex, ey)) return null;
    if (sx === ex && sy === ey) return [];
    const queue = [{ x: sx, y: sy, path: [] }];
    const visited = new Set();
    visited.add(sx + ',' + sy);
    const dirs = [[0,-1],[0,1],[-1,0],[1,0]];
    while (queue.length > 0) {
        const cur = queue.shift();
        for (const [dx, dy] of dirs) {
            const nx = cur.x + dx, ny = cur.y + dy;
            const key = nx + ',' + ny;
            if (!visited.has(key) && isWalkable(nx, ny)) {
                visited.add(key);
                const newPath = cur.path.concat([{ x: nx, y: ny }]);
                if (nx === ex && ny === ey) return newPath;
                queue.push({ x: nx, y: ny, path: newPath });
                if (visited.size > 1200) return null; // safety limit
            }
        }
    }
    return null;
}

function processMovementQueue(penguin) {
    if (!penguin.movementQueue || penguin.movementQueue.length === 0) {
        penguin.isPlayerControlled = false;
        // Resume auto-wander after 5 s pause
        setTimeout(function() {
            if (!penguin.isPlayerControlled) penguin.canAutoWander = true;
        }, 5000);
        return;
    }
    const next = penguin.movementQueue.shift();
    if (next.x > penguin.gridX) penguin.facingRight = true;
    else if (next.x < penguin.gridX) penguin.facingRight = false;
    penguin.targetGridX = next.x;
    penguin.targetGridY = next.y;
    penguin.progress    = 0;
    penguin.isMoving    = true;
    // onArrival fires when progress reaches 1 in updatePenguins
    penguin.onArrival = function() { processMovementQueue(penguin); };
}

function movePlayerTo(targetX, targetY) {
    const player = penguins.find(function(p) { return p.isCurrentUser; });
    if (!player) return;
    const sx = Math.round(player.gridX), sy = Math.round(player.gridY);
    if (!isWalkable(targetX, targetY)) {
        const wpos = gridToScreen(targetX, targetY);
        _invalidTarget = { wx: wpos.x, wy: wpos.y, born: performance.now() };
        if (window.GameSounds) GameSounds.moveBlocked();
        return;
    }
    const path = findPath(sx, sy, targetX, targetY);
    if (!path || path.length === 0) {
        const wpos = gridToScreen(targetX, targetY);
        _invalidTarget = { wx: wpos.x, wy: wpos.y, born: performance.now() };
        if (window.GameSounds) GameSounds.moveBlocked();
        return;
    }
    if (window.GameSounds) GameSounds.moveClick();
    player.movementQueue    = path;
    player.isPlayerControlled = true;
    player.canAutoWander    = false;
    const wpos = gridToScreen(targetX, targetY);
    _moveTarget = { wx: wpos.x, wy: wpos.y, born: performance.now() };
    processMovementQueue(player);
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
            // Player-controlled movement is twice as fast (500ms/tile vs 1000ms/tile)
            const speed = p.isPlayerControlled ? 500 : 1000;
            p.progress = Math.min(1, p.progress + dt / speed);
            p.isMoving = true;
            if (now - p.lastFrameTime > PENGUIN_ANIM_SPEED) {
                p.animFrame    = (p.animFrame + 1) % PENGUIN_FRAME_COUNT;
                p.lastFrameTime = now;
            }
        } else {
            const prevX = p.gridX, prevY = p.gridY;
            p.gridX    = p.targetGridX;
            p.gridY    = p.targetGridY;
            p.isMoving = false;
            p.animFrame = 0;
            // Footstep sound when current player arrives at a new tile
            if (p.isCurrentUser && window.GameSounds && (p.gridX !== prevX || p.gridY !== prevY)) {
                GameSounds.footstep();
            }
            if (p.onArrival) {
                const cb = p.onArrival;
                p.onArrival = null;
                cb();
                continue; // skip auto-wander this frame while following a path
            }
            if (!p.isPlayerControlled && (p.canAutoWander !== false)) {
                p.nextMoveIn -= dt;
                if (p.nextMoveIn <= 0) {
                    stepPenguin(p);
                    p.nextMoveIn = 2000 + Math.random() * 2000;
                }
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
            ep.job           = p.job;
            ep.active_title  = p.active_title;
            ep.level         = p.level;
            ep.prestige      = p.prestige;
            ep.working       = !!p.job;
            ep.isCurrentUser = p.username === currentUser;
            ep.worn_items    = p.worn_items || {};
            ep.penguin_shape = p.penguin_shape || 'normal';
            ep.penguin_color = p.penguin_color || '#1a1a1a';
            ep.display_name  = p.display_name  || p.username;
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
                username:      p.username,
                display_name:  p.display_name  || p.username,
                penguin_shape: p.penguin_shape || 'normal',
                penguin_color: p.penguin_color || '#1a1a1a',
                job:           p.job,
                active_title:  p.active_title,
                level:         p.level,
                prestige:      p.prestige,
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
                canAutoWander: true,
                isPlayerControlled: false,
                movementQueue: null,
                onArrival: null,
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
        'background:#181820',
        'border:2px solid #A86EFF',
        'padding:8px 10px',
        "font-family:'Pixelify Sans',monospace",
        'font-size:12px',
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
            visitBtnHtml = '<div style="margin-top:6px;color:#4aff6b;font-size:10px;">VISITED TODAY ✅</div>';
        } else {
            visitBtnHtml = '<button id="map-visit-btn" style="margin-top:6px;display:block;width:100%;'
                + "font-family:'Pixelify Sans',monospace;font-size:10px;padding:4px 6px;"
                + 'background:#181820;color:#A86EFF;border:1px solid #A86EFF;cursor:pointer;" '
                + 'onmouseenter="this.style.background=\'#A86EFF\';this.style.color=\'#181820\'" '
                + 'onmouseleave="this.style.background=\'#181820\';this.style.color=\'#A86EFF\'" '
                + 'onclick="window._mapVisitIgloo && window._mapVisitIgloo(\'' + penguin.username + '\')">'
                + '🏠 VISIT IGLOO</button>';
        }
    }

    el.innerHTML = [
        '<div style="color:#FFFFFF">' + (penguin.display_name || penguin.username) + '</div>',
        penguin.active_title ? '<div style="color:#FF8C00">' + penguin.active_title + '</div>' : '',
        '<div style="color:#B8B8D0">LV' + (penguin.level || 1) + ' · ' + jobIcon + ' ' + jobName + '</div>',
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

    // iOS Safari touch-to-click shim
    let _touchStartX = null, _touchStartY = null;
    canvas.addEventListener('touchstart', function(e) {
        if (e.touches.length === 1) {
            _touchStartX = e.touches[0].clientX;
            _touchStartY = e.touches[0].clientY;
        }
    }, { passive: true });
    canvas.addEventListener('touchend', function(e) {
        if (_touchStartX === null) return;
        const t = e.changedTouches[0];
        if (Math.abs(t.clientX - _touchStartX) < 12 && Math.abs(t.clientY - _touchStartY) < 12) {
            const synth = { clientX: t.clientX, clientY: t.clientY };
            _clickValid = true;
            canvas.dispatchEvent(Object.assign(new MouseEvent('click', { bubbles: false }), synth));
        }
        _touchStartX = null; _touchStartY = null;
    }, { passive: false });

    canvas.addEventListener('click', function (e) {
        if (!_clickValid) return;

        const rect = canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left;
        const sy = e.clientY - rect.top;

        // 1. Penguin click (highest priority)
        for (const p of penguins) {
            const interp = {
                x: p.gridX + (p.targetGridX - p.gridX) * p.progress,
                y: p.gridY + (p.targetGridY - p.gridY) * p.progress,
            };
            const wpos = gridToScreen(interp.x, interp.y);
            const spos = worldToScreen(wpos.x, wpos.y);
            const dist = Math.sqrt((sx - spos.x) ** 2 + (sy - spos.y) ** 2);
            if (dist <= 16) {
                if (window.GameSounds) GameSounds.uiClick();
                showPenguinPopup(p, spos.x, spos.y);
                return;
            }
        }

        // 2. Building click
        const g = screenToGrid(sx, sy);
        let bid = (g.x >= 0 && g.x < GRID_SIZE && g.y >= 0 && g.y < GRID_SIZE)
            ? getBuildingAtTile(g.x, g.y) : null;
        if (!bid) {
            const wx = (sx - cameraX) / zoomLevel;
            const wy = (sy - cameraY) / zoomLevel;
            bid = getBuildingAtScreenPos(wx, wy);
        }
        if (bid && openBuildingFn) { if (window.GameSounds) GameSounds.buildingClick(); openBuildingFn(bid); return; }

        // 3. Click-to-move — move the player's penguin to the clicked tile
        if (g.x >= 0 && g.x < GRID_SIZE && g.y >= 0 && g.y < GRID_SIZE) {
            movePlayerTo(g.x, g.y);
        }
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
                    if (window.GameSounds) GameSounds.uiClick();
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
            if (bid && openBuildingFn) { if (window.GameSounds) GameSounds.buildingClick(); openBuildingFn(bid); }
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
            if (window.GameSounds) GameSounds.mapZoom();
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

    // ── Phase 1: Ground tiles (always flat — draw first) ─────────────────────
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

            if (tileType === TILE_EXPAND) {
                drawExpansionTile(pos.x, pos.y);
            } else if (tileType === TILE_WATER) {
                drawWaterTile(pos.x, pos.y, _time);
            } else {
                drawTile(pos.x, pos.y, TILE_COLORS[tileType] || TILE_COLORS[0], tileType);
            }

            if (tileType === TILE_FENCE) {
                drawFence(pos.x, pos.y);
            }
            // Trees drawn in Phase 2 for correct depth ordering with buildings and penguins
        }
    }

    // Expansion zone labels (drawn in world space while transform is still active)
    if (fontReady) {
        ctx.save();
        ctx.textAlign = 'center';
        for (const lbl of EXPANSION_LABELS) {
            const lpos = gridToScreen(lbl.gridX, lbl.gridY);
            // Cull
            const lsx = lpos.x * zoomLevel + cameraX;
            const lsy = lpos.y * zoomLevel + cameraY;
            if (lsx < -200 || lsx > canvas.width + 200 || lsy < -100 || lsy > canvas.height + 100) continue;
            ctx.font = `${Math.max(7, Math.floor(9 * zoomLevel))}px 'Pixelify Sans', monospace`;
            ctx.fillStyle = '#3A3A50';
            lbl.text.forEach((line, i) => {
                ctx.fillText(line, lpos.x, lpos.y + (i - lbl.text.length / 2 + 0.5) * 11 * zoomLevel);
            });
            ctx.font = `${Math.max(6, Math.floor(7 * zoomLevel))}px 'Pixelify Sans', monospace`;
            ctx.fillStyle = '#6040A0';
            ctx.fillText(lbl.era, lpos.x, lpos.y + (lbl.text.length / 2 + 0.5) * 11 * zoomLevel + 3 * zoomLevel);
        }
        ctx.restore();
    }

    updatePenguins(dt);

    // ── Phase 2: Upright objects sorted back-to-front (painter's algorithm) ──
    const uprightObjects = [];

    // Trees — sort key is their single grid cell
    for (let y = 0; y < GRID_SIZE; y++) {
        for (let x = 0; x < GRID_SIZE; x++) {
            if (grid[y] && grid[y][x] === TILE_TREE) {
                uprightObjects.push({ type: 'tree', gridX: x, gridY: y, sortKey: x + y });
            }
        }
    }

    // Buildings — use front corner (bottom-right) for depth so they cover objects behind them
    for (const [id, bdef] of Object.entries(buildingLayout)) {
        const level = buildingLevels[id] !== undefined ? buildingLevels[id] : 1;
        uprightObjects.push({
            type: 'building', id, bdef, level,
            sortKey: (bdef.gridX + bdef.width - 1) + (bdef.gridY + bdef.height - 1),
        });
    }

    // Penguins — use interpolated position for smooth depth during movement
    for (const p of penguins) {
        const ix = p.gridX + (p.targetGridX - p.gridX) * p.progress;
        const iy = p.gridY + (p.targetGridY - p.gridY) * p.progress;
        uprightObjects.push({ type: 'penguin', data: p, ix, iy, sortKey: ix + iy });
    }

    // Sort: lower sortKey = further from viewer = drawn first
    uprightObjects.sort((a, b) => a.sortKey - b.sortKey);

    for (const obj of uprightObjects) {
        if (obj.type === 'tree') {
            const pos = gridToScreen(obj.gridX, obj.gridY);
            const seed = treeSeed[obj.gridX + ',' + obj.gridY] || 0;
            drawTree(pos.x, pos.y, seed);
        } else if (obj.type === 'building') {
            drawBuilding(obj.id, obj.bdef, obj.level);
        } else {
            const pos = gridToScreen(obj.ix, obj.iy);
            const isBehind = isPenguinBehindBuilding(obj.ix, obj.iy);
            drawPenguin(pos.x, pos.y, obj.data, isBehind);
        }
    }

    // Move-target and invalid-target overlays (world space, before ctx.restore)
    const now2 = performance.now();
    if (_moveTarget) {
        const elapsed = now2 - _moveTarget.born;
        if (elapsed < 1400) {
            const alpha = 1 - elapsed / 1400;
            const pulse = 1 + 0.25 * Math.sin(elapsed / 120);
            ctx.save();
            ctx.globalAlpha = alpha * 0.7;
            ctx.fillStyle = '#4aff6b';
            ctx.beginPath();
            ctx.arc(_moveTarget.wx, _moveTarget.wy, 6 * pulse, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
        } else {
            _moveTarget = null;
        }
    }
    if (_invalidTarget) {
        const elapsed = now2 - _invalidTarget.born;
        if (elapsed < 500) {
            const alpha = 1 - elapsed / 500;
            ctx.save();
            ctx.globalAlpha = alpha * 0.8;
            ctx.strokeStyle = '#ff4444';
            ctx.lineWidth = 2;
            const r = 7;
            ctx.beginPath();
            ctx.moveTo(_invalidTarget.wx - r, _invalidTarget.wy - r);
            ctx.lineTo(_invalidTarget.wx + r, _invalidTarget.wy + r);
            ctx.moveTo(_invalidTarget.wx + r, _invalidTarget.wy - r);
            ctx.lineTo(_invalidTarget.wx - r, _invalidTarget.wy + r);
            ctx.stroke();
            ctx.restore();
        } else {
            _invalidTarget = null;
        }
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

function highlightBuilding(buildingId) { _highlightedBuilding = buildingId; }
function clearBuildingHighlight() { _highlightedBuilding = null; }

function updatePlayerWornItems(wornItems) {
    const player = penguins.find(function(p) { return p.isCurrentUser; });
    if (player) player.worn_items = wornItems || {};
}

window.VillageMap = { init: initEngine, updateBuildingLevels, resize: resizeViewport, setVisitedToday, highlightBuilding, clearBuildingHighlight, updatePlayerWornItems };

})();
