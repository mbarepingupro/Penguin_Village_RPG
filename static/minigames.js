// ─── Mini-Game System ──────────────────────────────────────────────────────

var MiniGameManager = {
  _overlay: null,
  _canvas: null,
  _ctx: null,
  _score: 0,
  _timeLeft: 0,
  _timer: null,
  _activeGame: null,
  _onComplete: null,

  _createOverlay: function() {
    var existing = document.getElementById('minigame-overlay');
    if (existing) existing.parentNode.removeChild(existing);

    var overlay = document.createElement('div');
    overlay.id = 'minigame-overlay';
    overlay.style.cssText = [
      'position:fixed;top:0;left:0;width:100%;height:100%;',
      'background:rgba(0,0,0,0.93);z-index:9000;',
      'display:flex;flex-direction:column;align-items:center;',
      'justify-content:flex-start;padding-top:16px;box-sizing:border-box;',
    ].join('');

    var hud = document.createElement('div');
    hud.id = 'mg-hud';
    hud.style.cssText = 'display:flex;gap:16px;align-items:center;margin-bottom:10px;font-family:monospace;font-size:15px;flex-wrap:wrap;justify-content:center;';
    hud.innerHTML =
      '<span id="mg-title" style="color:#4aff6b;font-size:17px;font-weight:bold;"></span>' +
      '<span id="mg-score" style="color:#FFD700;">SCORE: 0</span>' +
      '<span id="mg-timer" style="color:#FF6B6B;">TIME: 15</span>' +
      '<button onclick="MiniGameManager.close()" style="background:#2a2a3a;color:#B8B8D0;border:1px solid #555;padding:3px 10px;cursor:pointer;font-family:monospace;font-size:13px;">✕ QUIT</button>';

    var cw = Math.min(window.innerWidth - 24, 500);
    var ch = Math.min(window.innerHeight - 130, 380);

    var canvas = document.createElement('canvas');
    canvas.id = 'mg-canvas';
    canvas.width = cw;
    canvas.height = ch;
    canvas.style.cssText = 'display:block;background:#111;border:2px solid #2a2a4a;touch-action:none;';

    var inst = document.createElement('div');
    inst.id = 'mg-instruction';
    inst.style.cssText = 'color:#8888A8;font-size:12px;margin-top:7px;text-align:center;max-width:500px;padding:0 10px;';

    overlay.appendChild(hud);
    overlay.appendChild(canvas);
    overlay.appendChild(inst);
    document.body.appendChild(overlay);

    this._overlay = overlay;
    this._canvas = canvas;
    this._ctx = canvas.getContext('2d');
  },

  startGame: function(buildingId, onComplete) {
    this._createOverlay();
    this._score = 0;
    this._onComplete = onComplete;
    if (window.GameSounds) GameSounds.minigameStart();

    var titles = {
      sea_lion_pit:  '🎣 FISH CATCH',
      club_soda:     '🌿 HERB GARDEN',
      parkmusement:  '🎪 JUGGLE MASTER',
      cursed_temple: '🔮 RUNE MEMORY',
      guillotine:    '💀 WHACK-A-TARGET',
    };
    var insts = {
      sea_lion_pit:  'Click fish to catch them! Avoid puffer fish! Golden fish = jackpot!',
      club_soda:     'Click herbs when fully RIPE (green glow)! Sprouts score less.',
      parkmusement:  'Click when the ball is inside the green zone! Build combos!',
      cursed_temple: 'Watch the rune sequence, then repeat it in order!',
      guillotine:    'Whack monsters & elites! Never hit a penguin!',
    };
    document.getElementById('mg-title').textContent = titles[buildingId] || 'MINI-GAME';
    document.getElementById('mg-instruction').textContent = insts[buildingId] || '';
    this._updateHUD();

    switch (buildingId) {
      case 'sea_lion_pit':  this._activeGame = FishCatchGame;    break;
      case 'club_soda':     this._activeGame = HerbGardenGame;   break;
      case 'parkmusement':  this._activeGame = JuggleMasterGame; break;
      case 'cursed_temple': this._activeGame = RuneMemoryGame;   break;
      case 'guillotine':    this._activeGame = ExecutionerGame;  break;
      default:              this._activeGame = FishCatchGame;
    }

    this._activeGame.init(this._canvas, this._ctx);
    this._startTimer(this._activeGame.duration || 15);
  },

  _startTimer: function(seconds) {
    var self = this;
    self._timeLeft = seconds;
    self._updateHUD();
    self._timer = setInterval(function() {
      self._timeLeft--;
      self._updateHUD();
      if (self._timeLeft <= 0) {
        clearInterval(self._timer);
        self._timer = null;
        self._endGame();
      }
    }, 1000);
  },

  addScore: function(pts) {
    this._score = Math.max(0, this._score + pts);
    this._updateHUD();
  },

  _updateHUD: function() {
    var scoreEl = document.getElementById('mg-score');
    var timerEl = document.getElementById('mg-timer');
    if (scoreEl) scoreEl.textContent = 'SCORE: ' + this._score;
    if (timerEl) {
      timerEl.textContent = 'TIME: ' + this._timeLeft;
      timerEl.style.color = this._timeLeft <= 5 ? '#FF2222' : '#FF6B6B';
    }
  },

  _endGame: function() {
    if (this._activeGame && this._activeGame.stop) this._activeGame.stop();
    var self = this;
    setTimeout(function() { self._showResults(); }, 100);
  },

  _showResults: function() {
    var self = this;
    var finalScore = Math.min(100, this._score);
    if (window.GameSounds) GameSounds.minigameComplete();

    var canvas = this._canvas;
    if (!canvas) return;
    var ctx = canvas.getContext('2d');

    ctx.fillStyle = 'rgba(0,0,0,0.88)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.textAlign = 'center';

    ctx.fillStyle = '#4aff6b';
    ctx.font = 'bold 26px monospace';
    ctx.fillText('GAME OVER!', canvas.width / 2, canvas.height / 2 - 50);

    ctx.fillStyle = '#FFD700';
    ctx.font = 'bold 20px monospace';
    ctx.fillText('Final Score: ' + finalScore, canvas.width / 2, canvas.height / 2 - 10);

    var grade, gradeColor;
    if (finalScore >= 80) { grade = 'S'; gradeColor = '#FFD700'; }
    else if (finalScore >= 60) { grade = 'A'; gradeColor = '#4aff6b'; }
    else if (finalScore >= 40) { grade = 'B'; gradeColor = '#4aafff'; }
    else if (finalScore >= 20) { grade = 'C'; gradeColor = '#FF8C00'; }
    else { grade = 'D'; gradeColor = '#B8B8D0'; }

    ctx.fillStyle = gradeColor;
    ctx.font = 'bold 44px monospace';
    ctx.fillText(grade, canvas.width / 2, canvas.height / 2 + 45);

    ctx.textAlign = 'left';

    setTimeout(function() {
      if (!document.getElementById('minigame-overlay')) return;
      var btn = document.createElement('button');
      btn.textContent = '✓ COLLECT REWARDS';
      btn.style.cssText = [
        'background:#4aff6b;color:#000;border:none;',
        'padding:12px 28px;font-size:15px;font-family:monospace;',
        'cursor:pointer;border-radius:4px;font-weight:bold;margin-top:12px;',
      ].join('');
      btn.onclick = function() {
        var ovEl = document.getElementById('minigame-overlay');
        if (ovEl) ovEl.parentNode.removeChild(ovEl);
        self._overlay = null;
        self._canvas = null;
        self._ctx = null;
        if (self._onComplete) self._onComplete(finalScore);
      };
      var ov = document.getElementById('minigame-overlay');
      if (ov) ov.appendChild(btn);
    }, 700);
  },

  close: function() {
    if (this._timer) { clearInterval(this._timer); this._timer = null; }
    if (this._activeGame && this._activeGame.stop) this._activeGame.stop();
    var ov = document.getElementById('minigame-overlay');
    if (ov) ov.parentNode.removeChild(ov);
    this._overlay = null;
    this._canvas = null;
    this._ctx = null;
  },
};

// ─── Fish Catch (Sea Lion Pit) ─────────────────────────────────────────────

var FishCatchGame = {
  duration: 15,
  _canvas: null,
  _ctx: null,
  _fish: [],
  _running: false,
  _spawnTimer: null,
  _animFrame: null,

  init: function(canvas, ctx) {
    this._canvas = canvas;
    this._ctx = ctx;
    this._fish = [];
    this._running = true;
    this._spawnFish();
    var self = this;
    this._spawnTimer = setInterval(function() { self._spawnFish(); }, 1100);
    canvas.onclick = null;
    canvas.ontouchend = null;
    var handler = this._handleClick.bind(this);
    canvas.onclick = handler;
    canvas.ontouchend = function(e) { e.preventDefault(); handler(e.changedTouches[0]); };
    this._render();
  },

  _spawnFish: function() {
    if (!this._running) return;
    var typePool = ['common','common','common','big','big','golden','puffer'];
    var type = typePool[Math.floor(Math.random() * typePool.length)];
    var cfgs = {
      common: { emoji:'🐟', size:28, speed:85,  pts: 2,  color:'#4aafff' },
      big:    { emoji:'🐠', size:38, speed:60,  pts: 5,  color:'#FF8C00' },
      golden: { emoji:'⭐', size:32, speed:110, pts:15,  color:'#FFD700' },
      puffer: { emoji:'🐡', size:34, speed:70,  pts:-5,  color:'#ff6b6b' },
    };
    var c = cfgs[type];
    this._fish.push({
      x: -55, y: 45 + Math.random() * (this._canvas.height - 90),
      speed: c.speed, size: c.size, pts: c.pts, emoji: c.emoji,
      hit: false, alpha: 1, riseSpd: 0,
    });
  },

  _clientXY: function(e, canvas) {
    var rect = canvas.getBoundingClientRect();
    var sx = canvas.width / rect.width;
    var sy = canvas.height / rect.height;
    return {
      x: ((e.clientX !== undefined ? e.clientX : e.pageX) - rect.left) * sx,
      y: ((e.clientY !== undefined ? e.clientY : e.pageY) - rect.top) * sy,
    };
  },

  _handleClick: function(e) {
    if (!this._running) return;
    var p = this._clientXY(e, this._canvas);
    for (var i = this._fish.length - 1; i >= 0; i--) {
      var f = this._fish[i];
      if (f.hit) continue;
      var dx = p.x - f.x, dy = p.y - f.y;
      if (Math.sqrt(dx*dx + dy*dy) < f.size * 0.75) {
        f.hit = true;
        f.riseSpd = 55;
        MiniGameManager.addScore(f.pts);
        if (window.GameSounds) { if (f.pts > 0) GameSounds.minigameHit(); else GameSounds.minigameMiss(); }
        break;
      }
    }
  },

  _render: function() {
    if (!this._running) return;
    var self = this;
    var ctx = this._ctx;
    var canvas = this._canvas;
    var last = null;

    function loop(ts) {
      if (!self._running) return;
      var dt = last ? Math.min((ts - last) / 1000, 0.05) : 0.016;
      last = ts;

      // Background — dark water
      ctx.fillStyle = '#061524';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Wave lines
      ctx.strokeStyle = 'rgba(74,170,255,0.08)';
      ctx.lineWidth = 1;
      for (var wy = 30; wy < canvas.height; wy += 45) {
        ctx.beginPath();
        for (var wx = 0; wx <= canvas.width; wx += 8) {
          var wv = Math.sin((wx + ts * 0.04) * 0.06) * 4;
          wx === 0 ? ctx.moveTo(wx, wy + wv) : ctx.lineTo(wx, wy + wv);
        }
        ctx.stroke();
      }

      ctx.font = '14px monospace';
      ctx.fillStyle = '#B8B8D0';
      ctx.textAlign = 'left';
      ctx.fillText('Click the fish! 🎣', 8, 20);

      // Fish
      for (var i = self._fish.length - 1; i >= 0; i--) {
        var f = self._fish[i];
        f.x += f.speed * dt;
        if (f.hit) {
          f.y -= f.riseSpd * dt;
          f.alpha -= dt * 2.5;
        }
        if (f.x > canvas.width + 60 || f.alpha <= 0) {
          self._fish.splice(i, 1); continue;
        }

        ctx.save();
        ctx.globalAlpha = Math.max(0, f.alpha);
        ctx.font = f.size + 'px serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(f.emoji, f.x, f.y);

        if (!f.hit) {
          ctx.font = '11px monospace';
          ctx.fillStyle = f.pts > 0 ? '#4aff6b' : '#ff6b6b';
          ctx.textBaseline = 'alphabetic';
          ctx.fillText((f.pts > 0 ? '+' : '') + f.pts, f.x, f.y - f.size * 0.55);
        }
        ctx.restore();
      }

      self._animFrame = requestAnimationFrame(loop);
    }
    self._animFrame = requestAnimationFrame(loop);
  },

  stop: function() {
    this._running = false;
    if (this._spawnTimer) { clearInterval(this._spawnTimer); this._spawnTimer = null; }
    if (this._animFrame) { cancelAnimationFrame(this._animFrame); this._animFrame = null; }
    if (this._canvas) { this._canvas.onclick = null; this._canvas.ontouchend = null; }
  },
};

// ─── Herb Garden (Club Soda) ───────────────────────────────────────────────

var HerbGardenGame = {
  duration: 20,
  COLS: 4,
  ROWS: 3,
  _canvas: null,
  _ctx: null,
  _cells: [],
  _running: false,
  _animFrame: null,

  init: function(canvas, ctx) {
    this._canvas = canvas;
    this._ctx = ctx;
    this._cells = [];
    this._running = true;

    for (var i = 0; i < this.COLS * this.ROWS; i++) {
      var r = Math.random();
      this._cells.push({
        stage: r < 0.25 ? 0 : (r < 0.6 ? 1 : 2),
        timer: 0,
        growSpeed: 3.5 + Math.random() * 3.5,
        wilted: false,
        harvested: false,
        harvestPts: 0,
        popAnim: 0,
        popTimer: 0,
      });
    }

    var self = this;
    var handler = this._handleClick.bind(this);
    canvas.onclick = handler;
    canvas.ontouchend = function(e) { e.preventDefault(); handler(e.changedTouches[0]); };
    this._render();
  },

  _handleClick: function(e) {
    if (!this._running) return;
    var rect = this._canvas.getBoundingClientRect();
    var sx = this._canvas.width / rect.width;
    var sy = this._canvas.height / rect.height;
    var mx = ((e.clientX !== undefined ? e.clientX : e.pageX) - rect.left) * sx;
    var my = ((e.clientY !== undefined ? e.clientY : e.pageY) - rect.top) * sy;

    var cw = this._canvas.width / this.COLS;
    var ch = this._canvas.height / this.ROWS;
    var col = Math.floor(mx / cw);
    var row = Math.floor(my / ch);
    if (col < 0 || col >= this.COLS || row < 0 || row >= this.ROWS) return;
    var idx = row * this.COLS + col;
    var cell = this._cells[idx];
    if (!cell || cell.harvested || cell.wilted) return;

    var pts = 0;
    if (cell.stage === 2) pts = 3;
    else if (cell.stage === 1) pts = 1;
    if (pts > 0) {
      cell.harvested = true;
      cell.harvestPts = pts;
      cell.popAnim = 1.0;
      cell.popTimer = 1.0;
      MiniGameManager.addScore(pts);
      if (window.GameSounds) GameSounds.minigameHit();
    }
  },

  _render: function() {
    if (!this._running) return;
    var self = this;
    var ctx = this._ctx;
    var canvas = this._canvas;
    var last = null;

    function loop(ts) {
      if (!self._running) return;
      var dt = last ? Math.min((ts - last) / 1000, 0.05) : 0.016;
      last = ts;

      ctx.fillStyle = '#060e06';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      var cw = canvas.width / self.COLS;
      var ch = canvas.height / self.ROWS;

      for (var i = 0; i < self._cells.length; i++) {
        var cell = self._cells[i];
        var col = i % self.COLS;
        var row = Math.floor(i / self.COLS);
        var cx = col * cw;
        var cy = row * ch;

        if (!cell.harvested && !cell.wilted) {
          cell.timer += dt;
          if (cell.timer >= cell.growSpeed) {
            cell.timer = 0;
            cell.stage++;
            if (cell.stage > 3) { cell.wilted = true; cell.stage = 3; }
          }
        }
        if (cell.popTimer > 0) cell.popTimer -= dt * 1.8;

        // Cell background
        var bgs = ['#0a140a','#0d200d','#0d3010','#1a1506'];
        ctx.fillStyle = cell.harvested ? '#050905' : (cell.wilted ? '#18100a' : bgs[Math.min(cell.stage, 3)]);
        ctx.fillRect(cx + 2, cy + 2, cw - 4, ch - 4);

        // Herb emoji
        if (!cell.harvested) {
          var emojis = ['🌱','🌿','🌿','🍂'];
          ctx.font = Math.min(cw, ch) * 0.45 + 'px serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.globalAlpha = cell.wilted ? 0.4 : 1;
          ctx.fillText(emojis[cell.stage], cx + cw / 2, cy + ch / 2 - 6);
          ctx.globalAlpha = 1;

          // Stage label
          var labels = ['sprout','growing','✦ RIPE!','wilted'];
          var lcols  = ['#666','#4aff6b','#00ff66','#884400'];
          ctx.font = '10px monospace';
          ctx.fillStyle = lcols[cell.stage];
          ctx.fillText(labels[cell.stage], cx + cw / 2, cy + ch - 8);
        } else {
          ctx.font = Math.min(cw, ch) * 0.4 + 'px serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.globalAlpha = 0.15;
          ctx.fillText('🌿', cx + cw / 2, cy + ch / 2);
          ctx.globalAlpha = 1;
        }

        // Harvest pop animation
        if (cell.popTimer > 0 && cell.harvestPts > 0) {
          var t = cell.popTimer;
          ctx.globalAlpha = t;
          ctx.fillStyle = '#4aff6b';
          ctx.font = 'bold 16px monospace';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'alphabetic';
          ctx.fillText('+' + cell.harvestPts, cx + cw / 2, cy + ch / 2 - (1 - t) * 28);
          ctx.globalAlpha = 1;
        }

        ctx.strokeStyle = '#0e1e0e';
        ctx.lineWidth = 1;
        ctx.strokeRect(cx, cy, cw, ch);
      }

      self._animFrame = requestAnimationFrame(loop);
    }
    self._animFrame = requestAnimationFrame(loop);
  },

  stop: function() {
    this._running = false;
    if (this._animFrame) { cancelAnimationFrame(this._animFrame); this._animFrame = null; }
    if (this._canvas) { this._canvas.onclick = null; this._canvas.ontouchend = null; }
  },
};

// ─── Juggle Master (Parkmusement) ──────────────────────────────────────────

var JuggleMasterGame = {
  duration: 15,
  _canvas: null,
  _ctx: null,
  _running: false,
  _animFrame: null,
  _ball: null,
  _combo: 0,
  _hitZoneY: 0,
  _hitZoneH: 0,
  _clickCooldown: 0,
  _flash: null,

  init: function(canvas, ctx) {
    this._canvas = canvas;
    this._ctx = ctx;
    this._running = true;
    this._combo = 0;
    this._clickCooldown = 0;
    this._flash = null;

    this._hitZoneY = canvas.height * 0.62;
    this._hitZoneH = canvas.height * 0.14;

    this._ball = {
      x: canvas.width / 2, y: canvas.height * 0.2,
      vy: 200, gravity: 380, floorY: canvas.height * 0.88,
    };

    var self = this;
    var handler = this._handleClick.bind(this);
    canvas.onclick = handler;
    canvas.ontouchend = function(e) { e.preventDefault(); handler(e.changedTouches[0]); };
    this._render();
  },

  _handleClick: function() {
    if (!this._running || this._clickCooldown > 0) return;
    var b = this._ball;
    var inZone = b.y >= this._hitZoneY && b.y <= this._hitZoneY + this._hitZoneH;
    if (inZone) {
      this._combo++;
      var pts = this._combo >= 3 ? 3 + this._combo : (this._combo >= 2 ? 4 : 3);
      MiniGameManager.addScore(pts);
      this._flash = { text: '+' + pts + (this._combo >= 2 ? ' x' + this._combo + '!' : ''), color: '#4aff6b', t: 1.0 };
      b.vy = -(280 + Math.min(this._combo, 5) * 20);
      if (window.GameSounds) { if (this._combo >= 2) GameSounds.minigameCombo(); else GameSounds.minigameHit(); }
    } else {
      this._combo = 0;
      this._flash = { text: 'MISS!', color: '#ff6b6b', t: 0.8 };
      if (window.GameSounds) GameSounds.minigameMiss();
    }
    this._clickCooldown = 0.35;
  },

  _render: function() {
    if (!this._running) return;
    var self = this;
    var ctx = this._ctx;
    var canvas = this._canvas;
    var last = null;

    function loop(ts) {
      if (!self._running) return;
      var dt = last ? Math.min((ts - last) / 1000, 0.05) : 0.016;
      last = ts;

      if (self._clickCooldown > 0) self._clickCooldown -= dt;

      ctx.fillStyle = '#0a0915';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Physics
      var b = self._ball;
      b.vy += b.gravity * dt;
      b.y += b.vy * dt;
      if (b.y >= b.floorY) { b.y = b.floorY; b.vy = -Math.abs(b.vy) * 0.72; self._combo = 0; }

      // Hit zone
      var hz = self._hitZoneY;
      var hh = self._hitZoneH;
      ctx.fillStyle = 'rgba(74,255,107,0.07)';
      ctx.fillRect(0, hz, canvas.width, hh);
      ctx.strokeStyle = '#4aff6b';
      ctx.lineWidth = 1;
      ctx.setLineDash([6, 5]);
      ctx.strokeRect(0, hz, canvas.width, hh);
      ctx.setLineDash([]);
      ctx.fillStyle = '#4aff6b';
      ctx.font = '10px monospace';
      ctx.textAlign = 'right';
      ctx.fillText('HIT ZONE', canvas.width - 5, hz + hh / 2 + 4);

      // Ball
      var inZone = b.y >= hz && b.y <= hz + hh;
      ctx.beginPath();
      ctx.arc(b.x, b.y, 22, 0, Math.PI * 2);
      ctx.fillStyle = inZone ? '#FFD700' : '#6688cc';
      ctx.fill();
      ctx.strokeStyle = inZone ? '#fff' : '#334488';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.font = '26px serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('🎪', b.x, b.y);
      ctx.textBaseline = 'alphabetic';

      // Instruction
      ctx.textAlign = 'center';
      ctx.fillStyle = inZone ? '#FFD700' : '#556';
      ctx.font = 'bold 14px monospace';
      ctx.fillText(inZone ? '👆 CLICK NOW!' : 'Wait for the zone...', canvas.width / 2, 26);

      // Combo
      if (self._combo >= 2) {
        ctx.fillStyle = '#FFD700';
        ctx.font = 'bold 18px monospace';
        ctx.fillText('🔥 x' + self._combo + ' COMBO!', canvas.width / 2, 52);
      }

      // Flash
      if (self._flash && self._flash.t > 0) {
        self._flash.t -= dt * 1.6;
        ctx.globalAlpha = Math.max(0, self._flash.t);
        ctx.fillStyle = self._flash.color;
        ctx.font = 'bold 22px monospace';
        ctx.fillText(self._flash.text, canvas.width / 2, canvas.height * 0.38);
        ctx.globalAlpha = 1;
      }

      ctx.textAlign = 'left';
      self._animFrame = requestAnimationFrame(loop);
    }
    self._animFrame = requestAnimationFrame(loop);
  },

  stop: function() {
    this._running = false;
    if (this._animFrame) { cancelAnimationFrame(this._animFrame); this._animFrame = null; }
    if (this._canvas) { this._canvas.onclick = null; this._canvas.ontouchend = null; }
  },
};

// ─── Rune Memory (Cursed Temple) ───────────────────────────────────────────

var RuneMemoryGame = {
  duration: 50,
  _canvas: null,
  _ctx: null,
  _running: false,
  _animFrame: null,
  _runes: [],
  _sequence: [],
  _input: [],
  _phase: 'show', // show | input | result
  _showIdx: 0,
  _showTimer: 0,
  _resultTimer: 0,
  _correct: null,
  _round: 0,

  RUNES:  ['🔮','⚡','🌊','🔥','🌿','💀'],
  COLORS: ['#A86EFF','#FFD700','#4aafff','#FF6B6B','#4aff6b','#B8B8D0'],

  init: function(canvas, ctx) {
    this._canvas = canvas;
    this._ctx = ctx;
    this._running = true;
    this._sequence = [];
    this._input = [];
    this._phase = 'show';
    this._showIdx = 0;
    this._showTimer = 0.4;
    this._correct = null;
    this._round = 0;

    var cx = canvas.width / 2;
    var cy = canvas.height / 2 + 10;
    var r = Math.min(canvas.width, canvas.height) * 0.34;
    this._runes = [];
    for (var i = 0; i < 6; i++) {
      var a = (i / 6) * Math.PI * 2 - Math.PI / 2;
      this._runes.push({ x: cx + Math.cos(a) * r, y: cy + Math.sin(a) * r, lit: false, litT: 0, idx: i });
    }

    this._startRound();
    var self = this;
    var handler = this._handleClick.bind(this);
    canvas.onclick = handler;
    canvas.ontouchend = function(e) { e.preventDefault(); handler(e.changedTouches[0]); };
    this._render();
  },

  _startRound: function() {
    this._round++;
    this._sequence.push(Math.floor(Math.random() * 6));
    this._input = [];
    this._phase = 'show';
    this._showIdx = 0;
    this._showTimer = 0.6;
  },

  _handleClick: function(e) {
    if (!this._running || this._phase !== 'input') return;
    var rect = this._canvas.getBoundingClientRect();
    var sx = this._canvas.width / rect.width;
    var sy = this._canvas.height / rect.height;
    var mx = ((e.clientX !== undefined ? e.clientX : e.pageX) - rect.left) * sx;
    var my = ((e.clientY !== undefined ? e.clientY : e.pageY) - rect.top) * sy;

    for (var i = 0; i < this._runes.length; i++) {
      var rn = this._runes[i];
      var dx = mx - rn.x, dy = my - rn.y;
      if (Math.sqrt(dx*dx + dy*dy) < 32) {
        this._input.push(rn.idx);
        rn.lit = true; rn.litT = 0.5;
        var pos = this._input.length - 1;
        if (rn.idx !== this._sequence[pos]) {
          this._phase = 'result'; this._resultTimer = 1.4; this._correct = false;
          MiniGameManager.addScore(-3);
          if (window.GameSounds) GameSounds.minigameMiss();
        } else if (this._input.length === this._sequence.length) {
          this._phase = 'result'; this._resultTimer = 0.9; this._correct = true;
          var pts = 5 + this._round * 3;
          MiniGameManager.addScore(pts);
          if (window.GameSounds) { if (this._round >= 3) GameSounds.minigameCombo(); else GameSounds.minigameHit(); }
        }
        break;
      }
    }
  },

  _render: function() {
    if (!this._running) return;
    var self = this;
    var ctx = this._ctx;
    var canvas = this._canvas;
    var last = null;

    function loop(ts) {
      if (!self._running) return;
      var dt = last ? Math.min((ts - last) / 1000, 0.05) : 0.016;
      last = ts;

      ctx.fillStyle = '#06020e';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Phase update
      if (self._phase === 'show') {
        self._showTimer -= dt;
        if (self._showTimer <= 0) {
          if (self._showIdx < self._sequence.length) {
            self._runes[self._sequence[self._showIdx]].lit = true;
            self._runes[self._sequence[self._showIdx]].litT = 0.65;
            self._showIdx++;
            self._showTimer = 0.85;
          } else {
            self._phase = 'input';
          }
        }
      } else if (self._phase === 'result') {
        self._resultTimer -= dt;
        if (self._resultTimer <= 0) {
          if (self._correct) { self._startRound(); }
          else {
            self._sequence = [Math.floor(Math.random() * 6)];
            self._input = []; self._phase = 'show'; self._showIdx = 0; self._showTimer = 0.5;
          }
        }
      }

      // Runes
      for (var i = 0; i < self._runes.length; i++) {
        var rn = self._runes[i];
        if (rn.litT > 0) rn.litT -= dt;
        var lit = rn.lit && rn.litT > 0;
        if (rn.lit && rn.litT <= 0) rn.lit = false;

        ctx.beginPath();
        ctx.arc(rn.x, rn.y, 29, 0, Math.PI * 2);
        ctx.fillStyle = lit ? self.COLORS[rn.idx] + '55' : '#12081e';
        ctx.fill();
        ctx.strokeStyle = lit ? self.COLORS[rn.idx] : '#2a1a3a';
        ctx.lineWidth = lit ? 3 : 1.5;
        ctx.stroke();

        ctx.font = '22px serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.globalAlpha = lit ? 1 : 0.45;
        ctx.fillText(self.RUNES[rn.idx], rn.x, rn.y);
        ctx.globalAlpha = 1;
      }

      // HUD text
      ctx.textAlign = 'center';
      ctx.textBaseline = 'alphabetic';
      if (self._phase === 'show') {
        ctx.fillStyle = '#A86EFF';
        ctx.font = 'bold 15px monospace';
        ctx.fillText('MEMORIZE THE SEQUENCE...', canvas.width / 2, 28);
        ctx.fillStyle = '#B8B8D0';
        ctx.font = '12px monospace';
        ctx.fillText('Round ' + self._round + ' — ' + self._sequence.length + ' rune(s)', canvas.width / 2, 48);
      } else if (self._phase === 'input') {
        ctx.fillStyle = '#4aff6b';
        ctx.font = 'bold 15px monospace';
        ctx.fillText('YOUR TURN! (' + self._input.length + ' / ' + self._sequence.length + ')', canvas.width / 2, 28);
        ctx.fillStyle = '#B8B8D0';
        ctx.font = '12px monospace';
        ctx.fillText('Tap the runes in order', canvas.width / 2, 48);
      } else if (self._phase === 'result') {
        ctx.fillStyle = self._correct ? '#4aff6b' : '#ff6b6b';
        ctx.font = 'bold 20px monospace';
        ctx.fillText(self._correct ? '✓ CORRECT! +' + (5 + self._round * 3) : '✗ WRONG! -3', canvas.width / 2, 28);
      }

      ctx.textAlign = 'left';
      self._animFrame = requestAnimationFrame(loop);
    }
    self._animFrame = requestAnimationFrame(loop);
  },

  stop: function() {
    this._running = false;
    if (this._animFrame) { cancelAnimationFrame(this._animFrame); this._animFrame = null; }
    if (this._canvas) { this._canvas.onclick = null; this._canvas.ontouchend = null; }
  },
};

// ─── Whack-A-Target (Guillotine) ──────────────────────────────────────────

var ExecutionerGame = {
  duration: 15,
  COLS: 4,
  ROWS: 3,
  _canvas: null,
  _ctx: null,
  _running: false,
  _animFrame: null,
  _targets: [],
  _spawnTimer: null,

  init: function(canvas, ctx) {
    this._canvas = canvas;
    this._ctx = ctx;
    this._targets = [];
    this._running = true;

    var self = this;
    this._spawnTarget();
    this._spawnTimer = setInterval(function() { self._spawnTarget(); }, 780);

    var handler = this._handleClick.bind(this);
    canvas.onclick = handler;
    canvas.ontouchend = function(e) { e.preventDefault(); handler(e.changedTouches[0]); };
    this._render();
  },

  _spawnTarget: function() {
    if (!this._running) return;
    var occupied = {};
    for (var i = 0; i < this._targets.length; i++) occupied[this._targets[i].cell] = true;
    var free = [];
    for (var c = 0; c < this.COLS * this.ROWS; c++) { if (!occupied[c]) free.push(c); }
    if (!free.length) return;

    var cell = free[Math.floor(Math.random() * free.length)];
    var pool = ['monster','monster','monster','elite','penguin'];
    var type = pool[Math.floor(Math.random() * pool.length)];
    var cfgs = {
      monster: { emoji:'👹', pts: 4,  color:'#ff6b6b', life:2.0 },
      elite:   { emoji:'💀', pts:10,  color:'#FF8C00', life:1.3 },
      penguin: { emoji:'🐧', pts:-6,  color:'#4aafff', life:1.9 },
    };
    var c = cfgs[type];
    this._targets.push({
      cell: cell, type: type, emoji: c.emoji, pts: c.pts, color: c.color,
      life: c.life, timer: c.life, popAnim: 0.05,
      hit: false, hitAnim: 0,
    });
  },

  _handleClick: function(e) {
    if (!this._running) return;
    var rect = this._canvas.getBoundingClientRect();
    var sx = this._canvas.width / rect.width;
    var sy = this._canvas.height / rect.height;
    var mx = ((e.clientX !== undefined ? e.clientX : e.pageX) - rect.left) * sx;
    var my = ((e.clientY !== undefined ? e.clientY : e.pageY) - rect.top) * sy;

    var cw = this._canvas.width / this.COLS;
    var ch = this._canvas.height / this.ROWS;
    var col = Math.floor(mx / cw);
    var row = Math.floor(my / ch);
    if (col < 0 || col >= this.COLS || row < 0 || row >= this.ROWS) return;
    var cellIdx = row * this.COLS + col;

    for (var i = 0; i < this._targets.length; i++) {
      var t = this._targets[i];
      if (t.cell === cellIdx && !t.hit) {
        t.hit = true; t.hitAnim = 1.0;
        MiniGameManager.addScore(t.pts);
        if (window.GameSounds) { if (t.pts > 0) GameSounds.minigameHit(); else GameSounds.minigameMiss(); }
        break;
      }
    }
  },

  _render: function() {
    if (!this._running) return;
    var self = this;
    var ctx = this._ctx;
    var canvas = this._canvas;
    var last = null;

    function loop(ts) {
      if (!self._running) return;
      var dt = last ? Math.min((ts - last) / 1000, 0.05) : 0.016;
      last = ts;

      ctx.fillStyle = '#100408';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      var cw = canvas.width / self.COLS;
      var ch = canvas.height / self.ROWS;

      // Holes
      for (var row = 0; row < self.ROWS; row++) {
        for (var col = 0; col < self.COLS; col++) {
          var hx = col * cw + cw / 2;
          var hy = row * ch + ch / 2;
          ctx.beginPath();
          ctx.ellipse(hx, hy, cw * 0.36, ch * 0.26, 0, 0, Math.PI * 2);
          ctx.fillStyle = '#050102';
          ctx.fill();
          ctx.strokeStyle = '#201016';
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      }

      // Targets
      for (var i = self._targets.length - 1; i >= 0; i--) {
        var t = self._targets[i];
        if (!t.hit) {
          t.timer -= dt;
          t.popAnim = Math.min(1, t.popAnim + dt * 5);
          if (t.timer <= 0) { self._targets.splice(i, 1); continue; }
        } else {
          t.hitAnim -= dt * 3.5;
          if (t.hitAnim <= 0) { self._targets.splice(i, 1); continue; }
        }

        var tcol = t.cell % self.COLS;
        var trow = Math.floor(t.cell / self.COLS);
        var tx = tcol * cw + cw / 2;
        var ty = trow * ch + ch / 2;
        var scale = t.hit ? t.hitAnim : t.popAnim;

        ctx.save();
        ctx.translate(tx, ty);
        ctx.scale(scale, scale);

        ctx.beginPath();
        ctx.arc(0, 0, Math.min(cw, ch) * 0.32, 0, Math.PI * 2);
        ctx.fillStyle = t.color + '22';
        ctx.fill();
        ctx.strokeStyle = t.color;
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.font = Math.min(cw, ch) * 0.38 + 'px serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(t.emoji, 0, -3);

        ctx.font = 'bold 11px monospace';
        ctx.fillStyle = t.pts > 0 ? '#4aff6b' : '#ff6b6b';
        ctx.textBaseline = 'alphabetic';
        ctx.fillText((t.pts > 0 ? '+' : '') + t.pts, 0, Math.min(cw, ch) * 0.36);

        ctx.restore();

        // Timer bar
        if (!t.hit) {
          var bw = cw * 0.65;
          var bx = tcol * cw + cw / 2 - bw / 2;
          var by = (trow + 1) * ch - 7;
          var pct = t.timer / t.life;
          ctx.fillStyle = '#1a0a10';
          ctx.fillRect(bx, by, bw, 4);
          ctx.fillStyle = pct > 0.5 ? '#4aff6b' : (pct > 0.25 ? '#FF8C00' : '#ff6b6b');
          ctx.fillRect(bx, by, bw * pct, 4);
        }
      }

      self._animFrame = requestAnimationFrame(loop);
    }
    self._animFrame = requestAnimationFrame(loop);
  },

  stop: function() {
    this._running = false;
    if (this._spawnTimer) { clearInterval(this._spawnTimer); this._spawnTimer = null; }
    if (this._animFrame) { cancelAnimationFrame(this._animFrame); this._animFrame = null; }
    if (this._canvas) { this._canvas.onclick = null; this._canvas.ontouchend = null; }
  },
};
