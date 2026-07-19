'use strict';
const IglooRenderer = (function () {
    const TW = 48, TH = 24, WALL_H = 60, BOX_H = 16;

    const FLOOR_COLORS = {
        ice: '#b8d8e8', wood: '#8B7355', stone: '#B8B8D0',
        carpet: '#8B2252', marble: '#e8e8e8', dark: '#3a2a1a',
    };
    const WALL_COLORS = {
        snow: '#dce8f0', wood: '#a0784a', brick: '#8B4513',
        crystal: '#88c8e8', dark_stone: '#4a4a4a',
    };
    const FUR_COLORS = { furniture: '#7a5c3c', decor: '#3c6a5a', special: '#7a6c1c' };
    const FUR_EMOJI = {
        small_table: '🪑', wooden_chair: '🪑', rug_small: '🟫', candle: '🕯️',
        bookshelf: '📚', potted_plant: '🌿', bed: '🛏️', fireplace: '🔥',
        fish_tank: '🐠', painting: '🖼️', lamp: '💡', desk: '✏️',
        wardrobe: '👗', rug_large: '🟫', throne: '👑', grand_piano: '🎹',
        fountain: '⛲', trophy_case: '🏆', crystal_chandelier: '💎',
        mayors_portrait: '🎭', golden_fish: '🐟', combat_banner: '⚔️',
    };

    // ── FURNITURE SPRITES ──────────────────────────────────────────────────
    // Mirrors village_map.js's SpriteLoader (same cache-by-full-URL-string
    // shape), kept as its own private copy here since this file's IIFE has
    // no shared scope with village_map.js's. Adds explicit in-flight
    // tracking (village_map.js doesn't need this -- its loads are either
    // fired once at init or already de-duped by its per-frame animation
    // loop) because _render() here is called on-demand from mouse events,
    // which can re-invoke _drawItem() for the same item many times before
    // a first load attempt resolves.
    const FurnitureSprites = {
        cache: {},
        pending: {},
        load: function (path) {
            if (Object.prototype.hasOwnProperty.call(this.cache, path)) {
                return Promise.resolve(this.cache[path]);
            }
            if (this.pending[path]) return this.pending[path];
            const p = new Promise((resolve) => {
                const img = new Image();
                img.onload  = () => { this.cache[path] = img;  delete this.pending[path]; resolve(img); };
                img.onerror = () => { this.cache[path] = null; delete this.pending[path]; resolve(null); };
                img.src = path;
            });
            this.pending[path] = p;
            return p;
        },
        get: function (path) {
            return this.cache[path] || null;
        },
    };

    // Cache-busting: appends ?v=<content hash> so the URL changes
    // automatically whenever the underlying file changes (see app.py's
    // _static_asset_versions, injected as the ASSET_VERSIONS global on the
    // same page this script loads into). relPath is the path relative to
    // /static/, e.g. "igloo_furniture/small_table.png". Falls back to the
    // bare unversioned URL when relPath has no known hash -- expected for
    // every item_id that has no PNG yet, since callers already treat a
    // failed/absent load as a normal fallback state, not an error.
    function _versionedAsset(relPath) {
        const v = (typeof ASSET_VERSIONS !== 'undefined' && ASSET_VERSIONS[relPath]) || null;
        return `/static/${relPath}` + (v ? `?v=${v}` : '');
    }

    let _canvas, _ctx, _data = null;
    let _editMode = false, _pendingItem = null;
    let _hoverCell = null, _selectedId = null;
    // Paint mode state
    let _paintMode = null;  // null | 'floor' | 'wall'
    let _paintBrush = null; // selected type id
    let _hoverWall = null;  // { side: 'left'|'right', index }

    const pub = {
        onCellClick: null,
        onFurnitureSelect: null,
        onPaintCell: null,  // (gx, gy, type)
        onWallClick: null,  // (side, index, type)
    };

    function _ox(s) { return s * TW / 2; }
    function _oy(s) { return WALL_H + TH / 2; }

    function _tc(gx, gy, s) {
        return { x: _ox(s) + (gx - gy) * (TW / 2), y: _oy(s) + (gx + gy) * (TH / 2) };
    }

    function _s2g(sx, sy, s) {
        const rx = sx - _ox(s), ry = sy - _oy(s);
        return { gx: Math.floor((2 * ry / TH + 2 * rx / TW) / 2), gy: Math.floor((2 * ry / TH - 2 * rx / TW) / 2) };
    }

    function _footprint(gx, gy, w, h, s) {
        const top    = _tc(gx,       gy,       s);
        const right  = _tc(gx + w - 1, gy,     s);
        const bottom = _tc(gx + w - 1, gy + h - 1, s);
        const left   = _tc(gx,       gy + h - 1, s);
        return [
            { x: top.x,           y: top.y    - TH / 2 },
            { x: right.x + TW / 2, y: right.y          },
            { x: bottom.x,        y: bottom.y + TH / 2 },
            { x: left.x  - TW / 2, y: left.y           },
        ];
    }

    function _poly(ctx, pts, fill, stroke, lw) {
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
        ctx.closePath();
        if (fill)   { ctx.fillStyle   = fill;   ctx.fill();   }
        if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lw || 1; ctx.stroke(); }
    }

    function _shade(hex, amt) {
        const r = parseInt(hex.slice(1, 3), 16);
        const g = parseInt(hex.slice(3, 5), 16);
        const b = parseInt(hex.slice(5, 7), 16);
        const clamp = v => Math.min(255, Math.max(0, v + amt));
        return `rgb(${clamp(r)},${clamp(g)},${clamp(b)})`;
    }

    function _overlaps(ax, ay, aw, ah, bx, by, bw, bh) {
        return ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by;
    }

    // Wall segment screen coords for a given side and index
    function _wallSegPts(side, idx, s) {
        const ox = _ox(s), oy = _oy(s);
        if (side === 'right') {
            const x0 = ox + idx * TW / 2,       y0 = oy - TH / 2 + idx * TH / 2;
            const x1 = ox + (idx + 1) * TW / 2, y1 = oy - TH / 2 + (idx + 1) * TH / 2;
            return [
                { x: x0, y: y0 - WALL_H }, { x: x1, y: y1 - WALL_H },
                { x: x1, y: y1 },          { x: x0, y: y0 },
            ];
        } else {
            const x0 = ox - idx * TW / 2,       y0 = oy - TH / 2 + idx * TH / 2;
            const x1 = ox - (idx + 1) * TW / 2, y1 = oy - TH / 2 + (idx + 1) * TH / 2;
            return [
                { x: x0, y: y0 - WALL_H }, { x: x1, y: y1 - WALL_H },
                { x: x1, y: y1 },          { x: x0, y: y0 },
            ];
        }
    }

    function _drawWalls(s, wallType, wallCells) {
        wallCells = wallCells || {};
        const ox  = _ox(s), oy = _oy(s);
        const border = 'rgba(0,0,0,0.2)';

        // Right wall — per-segment (gx axis, gy=0 side)
        for (let i = 0; i < s; i++) {
            const wt = wallCells[`right_${i}`] || wallType;
            const wc = WALL_COLORS[wt] || WALL_COLORS.snow;
            _poly(_ctx, _wallSegPts('right', i, s), _shade(wc, 15), border);
        }

        // Left wall — per-segment (gy axis, gx=0 side)
        for (let j = 0; j < s; j++) {
            const wt = wallCells[`left_${j}`] || wallType;
            const wc = WALL_COLORS[wt] || WALL_COLORS.snow;
            _poly(_ctx, _wallSegPts('left', j, s), _shade(wc, -20), border);
        }

        // Top ridge line
        _ctx.strokeStyle = _shade(WALL_COLORS[wallType] || WALL_COLORS.snow, 50);
        _ctx.lineWidth = 2;
        _ctx.beginPath();
        _ctx.moveTo(ox - s * TW / 2, oy + (s - 1) * TH / 2 - WALL_H);
        _ctx.lineTo(ox,              oy - TH / 2 - WALL_H);
        _ctx.lineTo(ox + s * TW / 2, oy + (s - 1) * TH / 2 - WALL_H);
        _ctx.stroke();
    }

    function _drawFloor(s, floorType, floorCells) {
        floorCells = floorCells || {};
        for (let gx = 0; gx < s; gx++) {
            for (let gy = 0; gy < s; gy++) {
                const cellType = floorCells[`${gx},${gy}`] || floorType;
                const fc = FLOOR_COLORS[cellType] || FLOOR_COLORS.ice;
                const fd = _shade(fc, -12);
                const c  = _tc(gx, gy, s);
                const color = (gx + gy) % 2 === 0 ? fc : fd;
                _ctx.beginPath();
                _ctx.moveTo(c.x,          c.y - TH / 2);
                _ctx.lineTo(c.x + TW / 2, c.y         );
                _ctx.lineTo(c.x,          c.y + TH / 2);
                _ctx.lineTo(c.x - TW / 2, c.y         );
                _ctx.closePath();
                _ctx.fillStyle = color;
                _ctx.fill();
                _ctx.strokeStyle = 'rgba(0,0,0,0.07)';
                _ctx.lineWidth = 0.5;
                _ctx.stroke();
            }
        }
    }

    function _drawItem(item, s) {
        const defn = IGLOO_FURNITURE_CLIENT[item.item_id] || {};
        const w = item.width || 1, h = item.height || 1;
        const cat   = defn.category || 'furniture';
        const base  = FUR_COLORS[cat] || FUR_COLORS.furniture;
        const emoji = FUR_EMOJI[item.item_id] || '📦';
        const sel   = item.id === _selectedId;
        const border = sel ? '#FF7FE5' : 'rgba(0,0,0,0.35)';
        const rotation = ((item.rotation || 0) % 360 + 360) % 360;

        const fp   = _footprint(item.grid_x, item.grid_y, w, h, s);
        const topF = fp.map(p => ({ x: p.x, y: p.y - BOX_H }));

        // Sprite override: draw PNG if loaded for this item_id, replacing
        // the colored box + emoji entirely (same override pattern as
        // village_map.js's drawBuilding()). Falls back silently to the
        // existing box+emoji rendering below when no art exists yet for
        // this item_id -- the expected state for most items today, not an
        // error. Kicks off a load on first encounter (in-flight-guarded, so
        // repeated renders before it resolves don't re-request it) and
        // re-renders once it resolves either way, so a newly-loaded sprite
        // appears without needing another user interaction to trigger it.
        const spritePath = _versionedAsset(`igloo_furniture/${item.item_id}.png`);
        const sprite = FurnitureSprites.get(spritePath);
        if (sprite === null && !(spritePath in FurnitureSprites.cache) && !FurnitureSprites.pending[spritePath]) {
            FurnitureSprites.load(spritePath).then(() => _render());
        }

        if (sprite) {
            // Anchor bottom-center on the same ground-level front corner
            // the box shape's base sits on (fp[2]); scale so the sprite's
            // width matches the item's grid footprint width in pixels
            // (width * TW), height scales proportionally, extending upward
            // from that anchor.
            const targetWidth = w * TW;
            const spriteScale = targetWidth / sprite.width;
            const drawWidth   = sprite.width  * spriteScale;
            const drawHeight  = sprite.height * spriteScale;
            const frontX = (fp[1].x + fp[3].x) / 2;
            const frontY = fp[2].y;

            _ctx.save();
            _ctx.translate(frontX, frontY - drawHeight / 2);
            _ctx.rotate(rotation * Math.PI / 180);
            _ctx.imageSmoothingEnabled = false;
            _ctx.drawImage(sprite, -drawWidth / 2, -drawHeight / 2, drawWidth, drawHeight);
            _ctx.restore();

            if (sel) {
                _poly(_ctx, fp, null, border, 2);
            }
        } else {
            _poly(_ctx, [topF[0], topF[1], fp[1], fp[0]], _shade(base, 20), border, 0.5);
            _poly(_ctx, [topF[3], topF[2], fp[2], fp[3]], _shade(base, -15), border, 0.5);
            _poly(_ctx, topF, _shade(base, 35), border, sel ? 2 : 0.5);

            const cx = (topF[0].x + topF[1].x + topF[2].x + topF[3].x) / 4;
            const cy = (topF[0].y + topF[1].y + topF[2].y + topF[3].y) / 4;
            const fs = Math.max(10, Math.min(18, TW * Math.min(w, h) * 0.35));
            _ctx.save();
            _ctx.translate(cx, cy);
            _ctx.rotate(rotation * Math.PI / 180);
            _ctx.font = `${fs}px sans-serif`;
            _ctx.textAlign = 'center';
            _ctx.textBaseline = 'middle';
            _ctx.fillText(emoji, 0, 0);
            _ctx.restore();
        }

        if (cat === 'special') {
            _ctx.strokeStyle = '#FFD700';
            _ctx.lineWidth = 2;
            _ctx.beginPath();
            _ctx.moveTo(topF[0].x, topF[0].y);
            topF.slice(1).forEach(p => _ctx.lineTo(p.x, p.y));
            _ctx.closePath();
            _ctx.stroke();
        }
    }

    function _drawHover(s) {
        if (!_hoverCell) return;
        const { gx, gy } = _hoverCell;
        const pw = _pendingItem ? (_pendingItem.width  || 1) : 1;
        const ph = _pendingItem ? (_pendingItem.height || 1) : 1;
        if (gx < 0 || gy < 0 || gx + pw > s || gy + ph > s) return;

        const occupied = _data && _data.furniture && _data.furniture.some(f =>
            _overlaps(gx, gy, pw, ph, f.grid_x, f.grid_y, f.width || 1, f.height || 1)
        );

        const pts    = _footprint(gx, gy, pw, ph, s);
        const fill   = occupied ? 'rgba(255,68,68,0.30)' : 'rgba(74,255,107,0.30)';
        const stroke = occupied ? '#ff4444' : '#4aff6b';
        _poly(_ctx, pts, fill, stroke, 1.5);

        if (_pendingItem) {
            const cx = (pts[0].x + pts[1].x + pts[2].x + pts[3].x) / 4;
            const cy = (pts[0].y + pts[1].y + pts[2].y + pts[3].y) / 4;
            _ctx.save();
            _ctx.globalAlpha = 0.65;
            _ctx.font = '18px sans-serif';
            _ctx.textAlign = 'center';
            _ctx.textBaseline = 'middle';
            _ctx.fillText(FUR_EMOJI[_pendingItem.item_id] || '📦', cx, cy);
            _ctx.restore();
        }
    }

    // Highlight hovered floor cell in paint mode
    function _drawPaintHover(s) {
        if (_paintMode === 'floor' && _hoverCell) {
            const { gx, gy } = _hoverCell;
            if (gx >= 0 && gy >= 0 && gx < s && gy < s) {
                const pts = _footprint(gx, gy, 1, 1, s);
                _poly(_ctx, pts, 'rgba(74,255,107,0.35)', '#4aff6b', 1.5);
            }
        }
        if (_paintMode === 'wall' && _hoverWall) {
            const { side, index } = _hoverWall;
            _poly(_ctx, _wallSegPts(side, index, s), 'rgba(74,255,107,0.35)', '#4aff6b', 2);
        }
    }

    // Hit-test which wall segment (if any) was clicked
    function _hitTestWall(sx, sy, s) {
        const ox = _ox(s), oy = _oy(s);
        // Right wall: sx >= ox
        if (sx >= ox) {
            const i = Math.floor((sx - ox) / (TW / 2));
            if (i >= 0 && i < s) {
                const y0 = oy - TH / 2 + i * TH / 2;
                const y1 = oy - TH / 2 + (i + 1) * TH / 2;
                if (sy >= y0 - WALL_H && sy <= y1) return { side: 'right', index: i };
            }
        }
        // Left wall: sx <= ox
        if (sx <= ox) {
            const j = Math.floor((ox - sx) / (TW / 2));
            if (j >= 0 && j < s) {
                const y0 = oy - TH / 2 + j * TH / 2;
                const y1 = oy - TH / 2 + (j + 1) * TH / 2;
                if (sy >= y0 - WALL_H && sy <= y1) return { side: 'left', index: j };
            }
        }
        return null;
    }

    function _render() {
        if (!_canvas || !_ctx || !_data) return;
        const s = _data.room_size || 6;
        _canvas.width  = s * TW;
        _canvas.height = WALL_H + s * TH;
        _ctx.clearRect(0, 0, _canvas.width, _canvas.height);

        _drawWalls(s, _data.wall_type  || 'snow', _data.wall_cells  || {});
        _drawFloor(s, _data.floor_type || 'ice',  _data.floor_cells || {});

        const sorted = [...(_data.furniture || [])].sort(
            (a, b) => (a.grid_x + a.grid_y) - (b.grid_x + b.grid_y)
        );
        for (const item of sorted) _drawItem(item, s);

        if (_paintMode) {
            _drawPaintHover(s);
        } else if (_editMode) {
            _drawHover(s);
        }
    }

    function _onMouseMove(e) {
        if (!_data) return;
        const rect = _canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left, sy = e.clientY - rect.top;
        const s = _data.room_size || 6;
        if (_paintMode === 'wall') {
            _hoverWall = _hitTestWall(sx, sy, s);
            _hoverCell = null;
        } else {
            _hoverCell = _s2g(sx, sy, s);
            _hoverWall = null;
        }
        _render();
    }

    function _onMouseLeave() {
        _hoverCell = null;
        _hoverWall = null;
        _render();
    }

    function _onClick(e) {
        if (!_data) return;
        const rect = _canvas.getBoundingClientRect();
        const sx = e.clientX - rect.left, sy = e.clientY - rect.top;
        const s = _data.room_size || 6;

        // Paint mode — floor
        if (_paintMode === 'floor') {
            const g = _s2g(sx, sy, s);
            if (g.gx >= 0 && g.gy >= 0 && g.gx < s && g.gy < s) {
                if (pub.onPaintCell) pub.onPaintCell(g.gx, g.gy, _paintBrush);
            }
            return;
        }

        // Paint mode — wall
        if (_paintMode === 'wall') {
            const hit = _hitTestWall(sx, sy, s);
            if (hit && pub.onWallClick) pub.onWallClick(hit.side, hit.index, _paintBrush);
            return;
        }

        if (!_editMode) return;
        const g = _s2g(sx, sy, s);

        if (_pendingItem) {
            if (window.GameSounds) GameSounds.furniturePlace();
            if (pub.onCellClick) pub.onCellClick(g.gx, g.gy);
        } else {
            const sorted = [...(_data.furniture || [])].sort(
                (a, b) => (b.grid_x + b.grid_y) - (a.grid_x + a.grid_y)
            );
            let hit = null;
            for (const f of sorted) {
                if (_overlaps(g.gx, g.gy, 1, 1, f.grid_x, f.grid_y, f.width || 1, f.height || 1)) {
                    hit = f; break;
                }
            }
            _selectedId = hit ? hit.id : null;
            if (pub.onFurnitureSelect) pub.onFurnitureSelect(_selectedId);
            _render();
        }
    }

    let IGLOO_FURNITURE_CLIENT = {};

    Object.assign(pub, {
        init(canvasId, furnitureDefs) {
            _canvas = document.getElementById(canvasId);
            if (!_canvas) return;
            _ctx = _canvas.getContext('2d');
            IGLOO_FURNITURE_CLIENT = furnitureDefs || {};
            _canvas.addEventListener('mousemove', _onMouseMove);
            _canvas.addEventListener('mouseleave', _onMouseLeave);
            _canvas.addEventListener('click', _onClick);
        },

        load(data) {
            _data        = data;
            _selectedId  = null;
            _pendingItem = null;
            _hoverCell   = null;
            _hoverWall   = null;
            _render();
        },

        updateData(data) {
            _data = data;
            _render();
        },

        setEditMode(on) {
            _editMode    = on;
            _pendingItem = null;
            _selectedId  = null;
            if (!on) { _paintMode = null; _paintBrush = null; }
            _canvas.style.cursor = (on || _paintMode) ? 'crosshair' : 'default';
            _render();
        },

        // Enter/exit paint mode. mode = 'floor' | 'wall' | null
        setPaintMode(mode, brushType) {
            _paintMode  = mode;
            _paintBrush = brushType || null;
            _pendingItem = null;
            _hoverWall   = null;
            _canvas.style.cursor = mode ? 'crosshair' : (_editMode ? 'crosshair' : 'default');
            _render();
        },

        setPaintBrush(brushType) {
            _paintBrush = brushType;
        },

        startPlacing(itemId, itemDef) {
            _paintMode   = null;
            _pendingItem = { item_id: itemId, ...itemDef };
            _canvas.style.cursor = 'crosshair';
        },

        cancelPlacing() {
            _pendingItem = null;
            _selectedId  = null;
            _canvas.style.cursor = (_editMode || _paintMode) ? 'crosshair' : 'default';
            _render();
        },

        selectFurniture(id) {
            _selectedId = id;
            _render();
        },

        get pendingItem() { return _pendingItem; },
        get selectedId()  { return _selectedId;  },
        get paintMode()   { return _paintMode;   },

        FLOOR_COLORS,
        WALL_COLORS,
    });

    return pub;
})();
