var OverworldMap = {
    canvas: null,
    ctx: null,
    areas: {},
    hoveredArea: null,
    _animFrame: null,
    _initialized: false,
    AREA_WIDTH: 160,
    AREA_HEIGHT: 80,
    GRID_COLS: 3,
    GRID_ROWS: 3,

    init: function(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        this.ctx.imageSmoothingEnabled = false;
        this.loadAreas();
        this.setupEvents();
        if (this._animFrame) cancelAnimationFrame(this._animFrame);
        this._loop();
    },

    _loop: function() {
        this.render();
        this._animFrame = requestAnimationFrame(() => this._loop());
    },

    loadAreas: async function() {
        try {
            const res = await fetch('/world/areas');
            const data = await res.json();
            this.areas = data.areas;
        } catch(e) {}
    },

    areaToScreen: function(col, row) {
        const centerX = this.canvas.width / 2;
        const centerY = this.canvas.height * 0.4;
        const x = (col - row) * (this.AREA_WIDTH / 2) + centerX;
        const y = (col + row) * (this.AREA_HEIGHT / 2) + centerY;
        return { x, y };
    },

    screenToArea: function(screenX, screenY) {
        const centerX = this.canvas.width / 2;
        const centerY = this.canvas.height * 0.4;
        const sx = screenX - centerX;
        const sy = screenY - centerY;
        const col = Math.round((sx / (this.AREA_WIDTH / 2) + sy / (this.AREA_HEIGHT / 2)) / 2);
        const row = Math.round((sy / (this.AREA_HEIGHT / 2) - sx / (this.AREA_WIDTH / 2)) / 2);
        return { col, row };
    },

    getAreaAt: function(row, col) {
        for (const [id, area] of Object.entries(this.areas)) {
            if (area.grid_position.row === row && area.grid_position.col === col) {
                return Object.assign({ id }, area);
            }
        }
        return null;
    },

    render: function() {
        const ctx = this.ctx;
        if (!ctx || !this.canvas || !this.canvas.width || !this.canvas.height) return;
        ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        ctx.fillStyle = '#0a0a12';
        ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

        // Loading state
        if (!this.areas || Object.keys(this.areas).length === 0) {
            ctx.font = '12px Silkscreen, monospace';
            ctx.fillStyle = '#8888A8';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('LOADING WORLD MAP...', this.canvas.width / 2, this.canvas.height / 2);
            return;
        }

        // Star field
        const now = performance.now();
        for (let i = 0; i < 80; i++) {
            const sx = (i * 137 + 11) % this.canvas.width;
            const sy = (i * 97  + 31) % (this.canvas.height * 0.9);
            const pulse = 0.15 + 0.25 * Math.abs(Math.sin(now / 2000 + i));
            ctx.globalAlpha = pulse;
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(sx, sy, 1, 1);
        }
        ctx.globalAlpha = 1;

        this.drawGridLines();

        for (let row = 0; row < this.GRID_ROWS; row++) {
            for (let col = 0; col < this.GRID_COLS; col++) {
                const area = this.getAreaAt(row, col);
                if (area) {
                    const isHovered = this.hoveredArea &&
                        this.hoveredArea.row === row && this.hoveredArea.col === col;
                    this.drawArea(area, col, row, isHovered);
                }
            }
        }

        ctx.font = '14px Silkscreen, monospace';
        ctx.textAlign = 'center';
        ctx.fillStyle = '#A86EFF';
        ctx.globalAlpha = 1;
        ctx.fillText('WORLD MAP', this.canvas.width / 2, 30);
    },

    drawGridLines: function() {
        const ctx = this.ctx;
        ctx.strokeStyle = '#1e1e30';
        ctx.lineWidth = 1;
        for (let row = 0; row < this.GRID_ROWS; row++) {
            for (let col = 0; col < this.GRID_COLS; col++) {
                const pos = this.areaToScreen(col, row);
                if (col < this.GRID_COLS - 1) {
                    const rp = this.areaToScreen(col + 1, row);
                    ctx.beginPath();
                    ctx.moveTo(pos.x + this.AREA_WIDTH / 4, pos.y);
                    ctx.lineTo(rp.x - this.AREA_WIDTH / 4, rp.y);
                    ctx.stroke();
                }
                if (row < this.GRID_ROWS - 1) {
                    const bp = this.areaToScreen(col, row + 1);
                    ctx.beginPath();
                    ctx.moveTo(pos.x, pos.y + this.AREA_HEIGHT / 4);
                    ctx.lineTo(bp.x, bp.y - this.AREA_HEIGHT / 4);
                    ctx.stroke();
                }
            }
        }
    },

    drawArea: function(area, col, row, isHovered) {
        const ctx = this.ctx;
        const pos = this.areaToScreen(col, row);
        const hoverOff = isHovered ? -14 : 0;
        const drawY = pos.y + hoverOff;
        const w = this.AREA_WIDTH;
        const h = this.AREA_HEIGHT;
        const isActive = area.status === 'active';
        const isLocked = area.status === 'locked';

        ctx.save();

        // Top face
        ctx.beginPath();
        ctx.moveTo(pos.x,         drawY - h / 2);
        ctx.lineTo(pos.x + w / 2, drawY);
        ctx.lineTo(pos.x,         drawY + h / 2);
        ctx.lineTo(pos.x - w / 2, drawY);
        ctx.closePath();
        ctx.fillStyle = isActive ? area.color + '28' : '#12121e';
        ctx.fill();

        ctx.setLineDash(isLocked ? [5, 5] : []);
        if (isHovered) {
            ctx.strokeStyle = isActive ? area.color : '#A86EFF';
            ctx.lineWidth = 3;
            ctx.shadowColor = isActive ? area.color : '#A86EFF';
            ctx.shadowBlur = 20;
        } else if (isActive) {
            ctx.strokeStyle = area.color;
            ctx.lineWidth = 2;
        } else {
            ctx.strokeStyle = '#3A3A50';
            ctx.lineWidth = 1;
        }
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.shadowBlur = 0;

        // 3D depth
        const depth = isHovered ? 10 : 5;
        ctx.beginPath();
        ctx.moveTo(pos.x - w / 2, drawY);
        ctx.lineTo(pos.x - w / 2, drawY + depth);
        ctx.lineTo(pos.x,         drawY + h / 2 + depth);
        ctx.lineTo(pos.x,         drawY + h / 2);
        ctx.closePath();
        ctx.fillStyle = isActive ? area.color + '18' : '#0e0e18';
        ctx.fill();

        ctx.beginPath();
        ctx.moveTo(pos.x + w / 2, drawY);
        ctx.lineTo(pos.x + w / 2, drawY + depth);
        ctx.lineTo(pos.x,         drawY + h / 2 + depth);
        ctx.lineTo(pos.x,         drawY + h / 2);
        ctx.closePath();
        ctx.fillStyle = isActive ? area.color + '0c' : '#0a0a14';
        ctx.fill();

        // Icon
        ctx.font = isHovered ? '26px serif' : '20px serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.globalAlpha = isLocked ? 0.4 : 1;
        ctx.fillText(area.icon, pos.x, drawY - 10);
        ctx.globalAlpha = 1;

        // Name
        ctx.font = '9px Silkscreen, monospace';
        ctx.fillStyle = isActive ? '#FFFFFF' : '#6868A0';
        ctx.textBaseline = 'alphabetic';
        ctx.fillText(area.name.toUpperCase(), pos.x, drawY + 14);

        // Era
        ctx.font = '8px Silkscreen, monospace';
        ctx.fillStyle = isActive ? area.color : '#3A3A50';
        ctx.fillText(area.era.toUpperCase(), pos.x, drawY + 27);

        // Lock icon
        if (isLocked) {
            ctx.font = '12px serif';
            ctx.globalAlpha = 0.65;
            ctx.fillText('🔒', pos.x + w / 3 - 4, drawY - h / 3 + 4);
            ctx.globalAlpha = 1;
        }

        // Pulse ring for active area
        if (isActive) {
            const pulse = 0.35 + 0.65 * Math.abs(Math.sin(performance.now() / 900));
            const r = parseInt(area.color.slice(1, 3), 16);
            const g = parseInt(area.color.slice(3, 5), 16);
            const b = parseInt(area.color.slice(5, 7), 16);
            ctx.strokeStyle = `rgba(${r},${g},${b},${pulse * 0.55})`;
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(pos.x,             drawY - h / 2 - 6);
            ctx.lineTo(pos.x + w / 2 + 6, drawY);
            ctx.lineTo(pos.x,             drawY + h / 2 + 6);
            ctx.lineTo(pos.x - w / 2 - 6, drawY);
            ctx.closePath();
            ctx.stroke();
        }

        ctx.restore();
    },

    setupEvents: function() {
        this.canvas.addEventListener('mousemove', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const scaleX = this.canvas.width / rect.width;
            const scaleY = this.canvas.height / rect.height;
            const mx = (e.clientX - rect.left) * scaleX;
            const my = (e.clientY - rect.top) * scaleY;
            const gp = this.screenToArea(mx, my);
            if (gp.col >= 0 && gp.col < this.GRID_COLS &&
                gp.row >= 0 && gp.row < this.GRID_ROWS) {
                const prev = this.hoveredArea;
                if (!prev || prev.col !== gp.col || prev.row !== gp.row) {
                    this._playHoverSound();
                }
                this.hoveredArea = gp;
                this.canvas.style.cursor = 'pointer';
            } else {
                this.hoveredArea = null;
                this.canvas.style.cursor = 'default';
            }
        });

        this.canvas.addEventListener('mouseleave', () => {
            this.hoveredArea = null;
        });

        this.canvas.addEventListener('click', (e) => {
            if (!this.hoveredArea) return;
            const area = this.getAreaAt(this.hoveredArea.row, this.hoveredArea.col);
            if (!area) return;
            if (area.status === 'active') {
                this._playConfirmSound();
                this.hide();
                const mapPanel = document.getElementById('panel-map');
                if (mapPanel) mapPanel.style.display = '';
            } else {
                this._playLockedSound();
                this.showLockedTooltip(area, e.clientX, e.clientY);
            }
        });

        this.canvas.addEventListener('touchend', (e) => {
            e.preventDefault();
            const touch = e.changedTouches[0];
            const rect = this.canvas.getBoundingClientRect();
            const scaleX = this.canvas.width / rect.width;
            const scaleY = this.canvas.height / rect.height;
            const mx = (touch.clientX - rect.left) * scaleX;
            const my = (touch.clientY - rect.top) * scaleY;
            const gp = this.screenToArea(mx, my);
            if (gp.col >= 0 && gp.col < this.GRID_COLS &&
                gp.row >= 0 && gp.row < this.GRID_ROWS) {
                const area = this.getAreaAt(gp.row, gp.col);
                if (!area) return;
                if (area.status === 'active') {
                    this._playConfirmSound();
                    this.hide();
                    const mapPanel = document.getElementById('panel-map');
                    if (mapPanel) mapPanel.style.display = '';
                } else {
                    this._playLockedSound();
                    const cx = window.innerWidth / 2;
                    const cy = window.innerHeight / 2;
                    this.showLockedTooltip(area, cx, cy);
                }
            }
        }, { passive: false });
    },

    showLockedTooltip: function(area, x, y) {
        const existing = document.getElementById('overworld-tooltip');
        if (existing) existing.remove();
        const tooltip = document.createElement('div');
        tooltip.id = 'overworld-tooltip';
        tooltip.style.cssText =
            'position:fixed;' +
            'left:' + Math.min(x + 12, window.innerWidth - 260) + 'px;' +
            'top:' + Math.max(y - 80, 10) + 'px;' +
            'background:#1C1C2E;border:2px solid #A86EFF;padding:12px 14px;' +
            'z-index:95000;max-width:240px;font-family:Silkscreen,monospace;' +
            'pointer-events:none;';
        tooltip.innerHTML =
            '<div style="color:#fff;font-size:11px;margin-bottom:5px;">' + area.icon + ' ' + area.name + '</div>' +
            '<div style="color:#B8B8D0;font-size:9px;margin-bottom:7px;line-height:1.8;">' + area.description + '</div>' +
            '<div style="color:#A86EFF;font-size:9px;">🔒 ' + (area.unlock_hint || 'Locked') + '</div>' +
            '<div style="color:#3A3A50;font-size:8px;margin-top:5px;">' + area.era + '</div>';
        document.body.appendChild(tooltip);
        setTimeout(() => { if (tooltip.parentNode) tooltip.remove(); }, 3000);
    },

    _playHoverSound: function() {
        if (window.GameSounds) GameSounds.overworldHover();
    },

    _playConfirmSound: function() {
        if (window.GameSounds) GameSounds.overworldEnter();
    },

    _playOpenSound: function() {
        if (window.GameSounds) GameSounds.overworldOpen();
    },

    _playLockedSound: function() {
        if (window.GameSounds) GameSounds.overworldLocked();
    },

    show: function() {
        const existing = document.getElementById('overworld-tooltip');
        if (existing) existing.remove();
        const panel = document.getElementById('panel-overworld');
        if (panel) panel.style.display = 'flex';
        const canvas = document.getElementById('overworld-canvas');
        if (!canvas) return;
        setTimeout(() => {
            const parent = canvas.parentElement;
            // Use clientWidth/clientHeight which reflect actual rendered size
            const w = parent.clientWidth  || parent.offsetWidth  || window.innerWidth  * 0.65;
            const h = parent.clientHeight || parent.offsetHeight || window.innerHeight * 0.75;
            canvas.width  = Math.max(w, 400);
            canvas.height = Math.max(h, 300);
            if (canvas.width < 500) {
                this.AREA_WIDTH  = 100;
                this.AREA_HEIGHT = 50;
            } else {
                this.AREA_WIDTH  = 160;
                this.AREA_HEIGHT = 80;
            }
            if (!this._initialized) {
                this.init('overworld-canvas');
                this._initialized = true;
            } else {
                // Re-assign canvas/ctx in case they changed
                this.canvas = canvas;
                this.ctx = canvas.getContext('2d');
                if (!this._animFrame) this._loop();
            }
            this._playOpenSound();
        }, 80);
    },

    hide: function() {
        const existing = document.getElementById('overworld-tooltip');
        if (existing) existing.remove();
        const panel = document.getElementById('panel-overworld');
        if (panel) panel.style.display = 'none';
        if (this._animFrame) { cancelAnimationFrame(this._animFrame); this._animFrame = null; }
    }
};
