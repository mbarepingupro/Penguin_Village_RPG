(function () {
'use strict';

const TILE_W = 64;
const TILE_H = 32;
const GRID_SIZE = 20;

const TILE_SNOW = 0, TILE_PATH = 1, TILE_WATER = 2, TILE_TREE = 3, TILE_BUILD = 4, TILE_FENCE = 5;

const TILE_COLORS = {
    0: "#C8DADA",
    1: "#8B7355",
    2: "#4A8FAA",
    3: "#1E4520",
    4: "#2E2E2E",
    5: "#555555",
};

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
};

const JOB_ICONS = {
    sea_lion_pit: "🎣",
    club_soda: "🌿",
    parkmusement: "🎪",
    cursed_temple: "📿",
    guillotine: "💀",
};

let canvas, ctx, currentUser, openBuildingFn;
let cameraX = 0, cameraY = 50;
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

function gridToScreen(gx, gy) {
    return {
        x: (gx - gy) * (TILE_W / 2) + cameraX,
        y: (gx + gy) * (TILE_H / 2) + cameraY,
    };
}

function screenToGrid(sx, sy) {
    const rx = sx - cameraX;
    const ry = sy - cameraY;
    const gx = Math.floor((rx / (TILE_W / 2) + ry / (TILE_H / 2)) / 2);
    const gy = Math.floor((ry / (TILE_H / 2) - rx / (TILE_W / 2)) / 2);
    return { x: gx, y: gy };
}

function drawTile(sx, sy, color) {
    ctx.beginPath();
    ctx.moveTo(sx, sy - TILE_H / 2);
    ctx.lineTo(sx + TILE_W / 2, sy);
    ctx.lineTo(sx, sy + TILE_H / 2);
    ctx.lineTo(sx - TILE_W / 2, sy);
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
}

function drawWaterTile(sx, sy, timeMs) {
    drawTile(sx, sy, "#4A8FAA");
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
    const color = cfg.color;

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

    const faceCenterX = (tPt.x + rPt.x + bPt.x + lPt.x) / 4;
    const faceCenterY = (tPt.y + rPt.y + bPt.y + lPt.y) / 4;

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

        ctx.font = "5px 'Press Start 2P', monospace";
        const lv = buildingLevels[id] !== undefined ? buildingLevels[id] : (level !== undefined ? level : 1);
        if (lv >= 5) {
            ctx.fillStyle = "#FF8C00";
            ctx.fillText("⭐MAX", faceCenterX, faceCenterY - 18);
        } else {
            ctx.fillStyle = "#A86EFF";
            ctx.fillText("LV" + lv, faceCenterX, faceCenterY - 18);
        }

        ctx.restore();
    }
}

function drawPenguinAt(sx, sy, penguin, pulse) {
    if (penguin.isCurrentUser) {
        ctx.save();
        ctx.beginPath();
        ctx.arc(sx, sy, 14 + pulse * 3, 0, Math.PI * 2);
        ctx.strokeStyle = "#FF7FE5";
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.restore();
    }

    ctx.beginPath();
    ctx.arc(sx, sy, 10, 0, Math.PI * 2);
    ctx.fillStyle = "#111111";
    ctx.fill();

    ctx.beginPath();
    ctx.arc(sx, sy + 1, 6, 0, Math.PI * 2);
    ctx.fillStyle = "#FFFFFF";
    ctx.fill();

    ctx.beginPath();
    ctx.arc(sx - 3, sy - 3, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = "#FFFFFF";
    ctx.fill();
    ctx.beginPath();
    ctx.arc(sx + 3, sy - 3, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = "#FFFFFF";
    ctx.fill();

    ctx.beginPath();
    ctx.arc(sx - 3, sy - 3, 1, 0, Math.PI * 2);
    ctx.fillStyle = "#000000";
    ctx.fill();
    ctx.beginPath();
    ctx.arc(sx + 3, sy - 3, 1, 0, Math.PI * 2);
    ctx.fillStyle = "#000000";
    ctx.fill();

    if (fontReady) {
        ctx.save();
        ctx.shadowColor = "rgba(0,0,0,0.9)";
        ctx.shadowBlur = 3;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";

        ctx.fillStyle = "#FFFFFF";
        ctx.font = "6px 'Press Start 2P', monospace";
        ctx.fillText(penguin.username, sx, sy - 26);

        if (penguin.active_title) {
            ctx.fillStyle = "#A86EFF";
            ctx.font = "5px 'Press Start 2P', monospace";
            ctx.fillText(penguin.active_title, sx, sy - 18);
        }

        ctx.restore();
    }

    if (penguin.job && JOB_ICONS[penguin.job]) {
        ctx.font = "10px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(JOB_ICONS[penguin.job], sx + 14, sy);
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

function pickNextTarget(penguin) {
    const radius = penguin.working ? 3 : 6;
    const hx = penguin.homeX;
    const hy = penguin.homeY;

    const pathTiles = [], snowTiles = [];
    for (let dx = -radius; dx <= radius; dx++) {
        for (let dy = -radius; dy <= radius; dy++) {
            const nx = hx + dx;
            const ny = hy + dy;
            if (!isWalkable(nx, ny)) continue;
            const t = grid[ny][nx];
            if (t === TILE_PATH) pathTiles.push({ x: nx, y: ny });
            else snowTiles.push({ x: nx, y: ny });
        }
    }

    // Prefer path tiles (penguins walk on roads), fall back to snow
    const pool = pathTiles.length > 0 ? pathTiles : snowTiles;
    if (pool.length === 0) return nearestWalkable(penguin.gridX, penguin.gridY);
    return pool[Math.floor(Math.random() * pool.length)];
}

function updatePenguins(dt) {
    for (const p of penguins) {
        if (p.progress < 1) {
            p.progress = Math.min(1, p.progress + dt / 900);
        } else {
            p.gridX = p.targetGridX;
            p.gridY = p.targetGridY;
            p.nextMoveIn -= dt;
            if (p.nextMoveIn <= 0) {
                const target = pickNextTarget(p);
                p.targetGridX = target.x;
                p.targetGridY = target.y;
                p.progress = 0;
                p.nextMoveIn = 2000 + Math.random() * 3000;
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
        } else {
            let gx = p.startGridX !== undefined ? p.startGridX : Math.floor(Math.random() * GRID_SIZE);
            let gy = p.startGridY !== undefined ? p.startGridY : Math.floor(Math.random() * GRID_SIZE);
            const safe = nearestWalkable(gx, gy);
            gx = safe.x; gy = safe.y;
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
        'padding:8px',
        "font-family:'Press Start 2P',monospace",
        'font-size:7px',
        'color:#FFFFFF',
        'pointer-events:none',
        'z-index:100',
        'line-height:1.6',
        'white-space:nowrap',
    ].join(';');

    const jobIcon = penguin.job ? (JOB_ICONS[penguin.job] || '') : '';
    const jobName = penguin.job ? penguin.job.replace(/_/g, ' ').toUpperCase() : 'UNEMPLOYED';

    el.innerHTML = [
        '<div>' + penguin.username + '</div>',
        penguin.active_title ? '<div style="color:#A86EFF">' + penguin.active_title + '</div>' : '',
        '<div>LV' + (penguin.level || 1) + ' · ' + jobIcon + ' ' + jobName + '</div>',
    ].join('');

    const popupX = (canvasRect.left - containerRect.left) + sx - 60;
    const popupY = (canvasRect.top - containerRect.top) + sy - 80;

    el.style.left = popupX + 'px';
    el.style.top = popupY + 'px';

    container.appendChild(el);
    _popupEl = el;

    setTimeout(() => {
        if (el.parentElement) el.parentElement.removeChild(el);
        if (_popupEl === el) _popupEl = null;
    }, 2500);
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
            const pos = gridToScreen(interp.x, interp.y);
            const dist = Math.sqrt((sx - pos.x) ** 2 + (sy - pos.y) ** 2);
            if (dist <= 16) {
                showPenguinPopup(p, pos.x, pos.y);
                return;
            }
        }

        const g = screenToGrid(sx, sy);
        if (g.x >= 0 && g.x < GRID_SIZE && g.y >= 0 && g.y < GRID_SIZE) {
            const bid = getBuildingAtTile(g.x, g.y);
            if (bid && openBuildingFn) {
                openBuildingFn(bid);
            }
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
        if (e.touches.length === 1) {
            const dx = e.touches[0].clientX - touchStartX;
            const dy = e.touches[0].clientY - touchStartY;
            if (Math.abs(dx) > 4 || Math.abs(dy) > 4) {
                touchMoved = true;
                cameraX = touchCamX + dx;
                cameraY = touchCamY + dy;
            }
        }
    }, { passive: true });

    canvas.addEventListener('touchend', function (e) {
        if (!touchMoved && e.changedTouches.length === 1) {
            const rect = canvas.getBoundingClientRect();
            const sx = e.changedTouches[0].clientX - rect.left;
            const sy = e.changedTouches[0].clientY - rect.top;

            for (const p of penguins) {
                const interp = {
                    x: p.gridX + (p.targetGridX - p.gridX) * p.progress,
                    y: p.gridY + (p.targetGridY - p.gridY) * p.progress,
                };
                const pos = gridToScreen(interp.x, interp.y);
                const dist = Math.sqrt((sx - pos.x) ** 2 + (sy - pos.y) ** 2);
                if (dist <= 16) {
                    showPenguinPopup(p, pos.x, pos.y);
                    return;
                }
            }

            const g = screenToGrid(sx, sy);
            if (g.x >= 0 && g.x < GRID_SIZE && g.y >= 0 && g.y < GRID_SIZE) {
                const bid = getBuildingAtTile(g.x, g.y);
                if (bid && openBuildingFn) {
                    openBuildingFn(bid);
                }
            }
        }
    });
}

function gameLoop(ts) {
    const dt = Math.min(ts - _lastTime, 100);
    _lastTime = ts;
    _time += dt;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    for (let diag = 0; diag < 2 * GRID_SIZE - 1; diag++) {
        for (let xi = Math.max(0, diag - GRID_SIZE + 1); xi <= Math.min(diag, GRID_SIZE - 1); xi++) {
            const x = xi;
            const y = diag - xi;
            const pos = gridToScreen(x, y);

            if (
                pos.x < -TILE_W * 2 || pos.x > canvas.width + TILE_W * 2 ||
                pos.y < -TILE_H * 4 || pos.y > canvas.height + 80
            ) continue;

            const tileType = (grid[y] && grid[y][x] !== undefined) ? grid[y][x] : TILE_SNOW;

            if (tileType === TILE_WATER) {
                drawWaterTile(pos.x, pos.y, _time);
            } else {
                drawTile(pos.x, pos.y, TILE_COLORS[tileType] || TILE_COLORS[0]);
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

    const pulse = (Math.sin(_time / 300) + 1) / 2;

    const sortedPenguins = penguins.slice().sort((a, b) => {
        const aSort = (a.gridX + (a.targetGridX - a.gridX) * a.progress) + (a.gridY + (a.targetGridY - a.gridY) * a.progress);
        const bSort = (b.gridX + (b.targetGridX - b.gridX) * b.progress) + (b.gridY + (b.targetGridY - b.gridY) * b.progress);
        return aSort - bSort;
    });

    for (const p of sortedPenguins) {
        const ix = p.gridX + (p.targetGridX - p.gridX) * p.progress;
        const iy = p.gridY + (p.targetGridY - p.gridY) * p.progress;
        const pos = gridToScreen(ix, iy);
        drawPenguinAt(pos.x, pos.y, p, pulse);
    }

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

window.VillageMap = { init: initEngine, updateBuildingLevels: updateBuildingLevels };

})();
