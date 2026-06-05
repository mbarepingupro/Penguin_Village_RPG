'use strict';
const IglooRenderer = (function () {
    const TW = 48, TH = 24, WALL_H = 60, BOX_H = 16;

    const FLOOR_COLORS = {
        ice: '#b8d8e8', wood: '#8B7355', stone: '#888888',
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

    let _canvas, _ctx, _data = null;
    let _editMode = false, _pendingItem = null;
    let _hoverCell = null, _selectedId = null;

    const pub = {
        onCellClick: null,
        onFurnitureSelect: null,
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

    function _drawWalls(s, wallType) {
        const wc  = WALL_COLORS[wallType] || WALL_COLORS.snow;
        const ox  = _ox(s), oy = _oy(s);
        const border = 'rgba(0,0,0,0.2)';

        // Right wall (gy=0 axis → goes right)
        _poly(_ctx, [
            { x: ox,           y: oy - TH / 2         },
            { x: ox + s*TW/2,  y: oy + (s-1)*TH/2     },
            { x: ox + s*TW/2,  y: oy + (s-1)*TH/2 - WALL_H },
            { x: ox,           y: oy - TH / 2 - WALL_H },
        ], _shade(wc, 15), border);

        // Left wall (gx=0 axis → goes left)
        _poly(_ctx, [
            { x: ox,           y: oy - TH / 2         },
            { x: ox - s*TW/2,  y: oy + (s-1)*TH/2     },
            { x: ox - s*TW/2,  y: oy + (s-1)*TH/2 - WALL_H },
            { x: ox,           y: oy - TH / 2 - WALL_H },
        ], _shade(wc, -20), border);

        // Top ridge line
        _ctx.strokeStyle = _shade(wc, 50);
        _ctx.lineWidth = 2;
        _ctx.beginPath();
        _ctx.moveTo(ox - s*TW/2, oy + (s-1)*TH/2 - WALL_H);
        _ctx.lineTo(ox,          oy - TH/2 - WALL_H);
        _ctx.lineTo(ox + s*TW/2, oy + (s-1)*TH/2 - WALL_H);
        _ctx.stroke();
    }

    function _drawFloor(s, floorType) {
        const fc = FLOOR_COLORS[floorType] || FLOOR_COLORS.ice;
        const fd = _shade(fc, -12);
        for (let gx = 0; gx < s; gx++) {
            for (let gy = 0; gy < s; gy++) {
                const c = _tc(gx, gy, s);
                const color = (gx + gy) % 2 === 0 ? fc : fd;
                _ctx.beginPath();
                _ctx.moveTo(c.x,         c.y - TH / 2);
                _ctx.lineTo(c.x + TW / 2, c.y         );
                _ctx.lineTo(c.x,         c.y + TH / 2);
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

        const fp   = _footprint(item.grid_x, item.grid_y, w, h, s);
        const topF = fp.map(p => ({ x: p.x, y: p.y - BOX_H }));

        // Right face
        _poly(_ctx,
            [topF[0], topF[1], fp[1], fp[0]],
            _shade(base, 20), border, 0.5
        );
        // Left face
        _poly(_ctx,
            [topF[3], topF[2], fp[2], fp[3]],
            _shade(base, -15), border, 0.5
        );
        // Top face
        _poly(_ctx, topF, _shade(base, 35), border, sel ? 2 : 0.5);

        // Emoji
        const cx = (topF[0].x + topF[1].x + topF[2].x + topF[3].x) / 4;
        const cy = (topF[0].y + topF[1].y + topF[2].y + topF[3].y) / 4;
        const fs = Math.max(10, Math.min(18, TW * Math.min(w, h) * 0.35));
        _ctx.font = `${fs}px sans-serif`;
        _ctx.textAlign = 'center';
        _ctx.textBaseline = 'middle';
        _ctx.fillText(emoji, cx, cy);

        // Special item: golden border
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

        const pts   = _footprint(gx, gy, pw, ph, s);
        const fill  = occupied ? 'rgba(255,68,68,0.30)' : 'rgba(74,255,107,0.30)';
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

    function _render() {
        if (!_canvas || !_ctx || !_data) return;
        const s = _data.room_size || 6;
        _canvas.width  = s * TW;
        _canvas.height = WALL_H + s * TH;
        _ctx.clearRect(0, 0, _canvas.width, _canvas.height);

        _drawWalls(s, _data.wall_type  || 'snow');
        _drawFloor(s, _data.floor_type || 'ice');

        const sorted = [...(_data.furniture || [])].sort(
            (a, b) => (a.grid_x + a.grid_y) - (b.grid_x + b.grid_y)
        );
        for (const item of sorted) _drawItem(item, s);

        if (_editMode) _drawHover(s);
    }

    function _onMouseMove(e) {
        if (!_data) return;
        const rect = _canvas.getBoundingClientRect();
        const s = _data.room_size || 6;
        _hoverCell = _s2g(e.clientX - rect.left, e.clientY - rect.top, s);
        _render();
    }

    function _onMouseLeave() {
        _hoverCell = null;
        _render();
    }

    function _onClick(e) {
        if (!_editMode || !_data) return;
        const rect = _canvas.getBoundingClientRect();
        const s = _data.room_size || 6;
        const g = _s2g(e.clientX - rect.left, e.clientY - rect.top, s);

        if (_pendingItem) {
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

    // Client-side furniture def cache (set by init)
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
            _render();
        },

        updateData(data) {
            _data = data;
            _render();
        },

        setEditMode(on) {
            _editMode   = on;
            _pendingItem = null;
            _selectedId  = null;
            _canvas.style.cursor = on ? 'crosshair' : 'default';
            _render();
        },

        startPlacing(itemId, itemDef) {
            _pendingItem = { item_id: itemId, ...itemDef };
            _canvas.style.cursor = 'crosshair';
        },

        cancelPlacing() {
            _pendingItem = null;
            _selectedId  = null;
            _canvas.style.cursor = _editMode ? 'crosshair' : 'default';
            _render();
        },

        selectFurniture(id) {
            _selectedId = id;
            _render();
        },

        get pendingItem() { return _pendingItem; },
        get selectedId()  { return _selectedId;  },

        FLOOR_COLORS,
        WALL_COLORS,
    });

    return pub;
})();
