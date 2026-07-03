// ─── Mini-Game System ──────────────────────────────────────────────────────

var MiniGameManager = {
  _overlay: null,
  _canvas: null,
  _ctx: null,
  _score: 0,
  _timeLeft: 0,
  _duration: 15,
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
      club_soda:     'Catch leaves 🌿 (+5) & ice 🧊 (+3) in your basket! Dodge toxic shrooms 🍄 (−5)! Arrow keys or drag.',
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

  // Returns a linear 1.0→2.0 multiplier over the game's duration.
  // Games use this to scale spawn rates, speeds, and timing windows.
  getDifficultyMult: function() {
    var elapsed = this._duration - this._timeLeft;
    return 1.0 + elapsed / this._duration;
  },

  _startTimer: function(seconds) {
    var self = this;
    self._timeLeft = seconds;
    self._duration = seconds;
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
    var self = this;
    function _schedFish() {
      self._spawnFish();
      if (self._running)
        self._spawnTimer = setTimeout(_schedFish, 1100 / MiniGameManager.getDifficultyMult());
    }
    _schedFish();
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
    var mult = MiniGameManager.getDifficultyMult();
    this._fish.push({
      x: -55, y: 45 + Math.random() * (this._canvas.height - 90),
      speed: c.speed * mult, size: c.size, pts: c.pts, emoji: c.emoji,
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
    if (this._spawnTimer) { clearTimeout(this._spawnTimer); this._spawnTimer = null; }
    if (this._animFrame) { cancelAnimationFrame(this._animFrame); this._animFrame = null; }
    if (this._canvas) { this._canvas.onclick = null; this._canvas.ontouchend = null; }
  },
};

// ─── Herb Garden (Club Soda) ───────────────────────────────────────────────
// Falling-object catcher: move basket left/right (arrow keys or touch drag),
// catch leaves (+5) and ice cubes (+3), dodge noxious mushrooms (-5).

var HerbGardenGame = {
  duration: 20,
  _canvas: null,
  _ctx: null,
  _running: false,
  _animFrame: null,
  _objects: [],
  _spawnTimer: null,
  _basketX: 0,
  _basketW: 70,
  _basketY: 0,
  _basketSpeed: 280,
  _keys: null,
  _keyHandler: null,
  _keyUpHandler: null,
  _touchStartX: null,
  _touchBasketX: null,

  _CFGS: {
    leaf:    { emoji: '🌿', pts:  5, color: '#4aff6b' },
    ice:     { emoji: '🧊', pts:  3, color: '#4aafff' },
    noxious: { emoji: '🍄', pts: -5, color: '#ff6b6b' },
  },
  _POOL: ['leaf','leaf','ice','ice','noxious'],

  init: function(canvas, ctx) {
    this._canvas = canvas;
    this._ctx = ctx;
    this._objects = [];
    this._running = true;
    this._keys = { left: false, right: false };
    this._basketW = Math.min(70, canvas.width * 0.18);
    this._basketX = canvas.width / 2 - this._basketW / 2;
    this._basketY = canvas.height - 40;
    this._touchStartX = null;
    this._touchBasketX = null;

    var self = this;

    // Keyboard input
    this._keyHandler = function(e) {
      if (e.key === 'ArrowLeft')  { self._keys.left  = true; e.preventDefault(); }
      if (e.key === 'ArrowRight') { self._keys.right = true; e.preventDefault(); }
    };
    this._keyUpHandler = function(e) {
      if (e.key === 'ArrowLeft')  self._keys.left  = false;
      if (e.key === 'ArrowRight') self._keys.right = false;
    };
    document.addEventListener('keydown', this._keyHandler);
    document.addEventListener('keyup',   this._keyUpHandler);

    // Touch drag
    canvas.onclick    = null;
    canvas.ontouchend = null;
    canvas.ontouchstart = function(e) {
      e.preventDefault();
      self._touchStartX  = e.touches[0].clientX;
      self._touchBasketX = self._basketX;
    };
    canvas.ontouchmove = function(e) {
      e.preventDefault();
      if (self._touchStartX === null) return;
      var rect = canvas.getBoundingClientRect();
      var sx = canvas.width / rect.width;
      var dx = (e.touches[0].clientX - self._touchStartX) * sx;
      self._basketX = Math.max(0, Math.min(canvas.width - self._basketW,
                                            self._touchBasketX + dx));
    };

    // Spawn first object immediately; reschedule each time so interval adapts to difficulty
    function _schedObj() {
      if (!self._running) return;
      self._spawnObject();
      self._spawnTimer = setTimeout(_schedObj, 820 / MiniGameManager.getDifficultyMult());
    }
    _schedObj();

    this._render();
  },

  _spawnObject: function() {
    var canvas = this._canvas;
    var type = this._POOL[Math.floor(Math.random() * this._POOL.length)];
    var c = this._CFGS[type];
    this._objects.push({
      x:      20 + Math.random() * (canvas.width - 40),
      y:      -22,
      type:   type,
      emoji:  c.emoji,
      pts:    c.pts,
      color:  c.color,
      speed:  (80 + Math.random() * 60) * MiniGameManager.getDifficultyMult(),
      size:   28,
      caught: false,
      alpha:  1,
      popY:   0,
    });
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

      // Move basket via keyboard
      if (self._keys.left)
        self._basketX = Math.max(0, self._basketX - self._basketSpeed * dt);
      if (self._keys.right)
        self._basketX = Math.min(canvas.width - self._basketW, self._basketX + self._basketSpeed * dt);

      // Background
      ctx.fillStyle = '#060e06';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Hint text
      ctx.font = '12px monospace';
      ctx.fillStyle = '#55775555';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'alphabetic';
      ctx.fillText('← → or drag', canvas.width / 2, canvas.height - 8);

      var bLeft  = self._basketX;
      var bRight = self._basketX + self._basketW;
      var bTop   = self._basketY;

      // Objects
      for (var i = self._objects.length - 1; i >= 0; i--) {
        var o = self._objects[i];

        if (!o.caught) {
          o.y += o.speed * dt;

          // Collision: object bottom edge reaches basket top, x inside basket
          if (o.y + o.size * 0.5 >= bTop &&
              o.x >= bLeft  - o.size * 0.5 &&
              o.x <= bRight + o.size * 0.5) {
            o.caught = true;
            o.popY   = bTop - 4;
            MiniGameManager.addScore(o.pts);
            if (window.GameSounds) {
              if (o.pts > 0) GameSounds.minigameHit();
              else           GameSounds.minigameMiss();
            }
          }

          if (o.y > canvas.height + 32) { self._objects.splice(i, 1); continue; }
        } else {
          o.alpha -= dt * 3.5;
          o.popY  -= 28 * dt;
          if (o.alpha <= 0) { self._objects.splice(i, 1); continue; }
        }

        ctx.save();
        ctx.globalAlpha = Math.max(0, o.alpha);

        if (!o.caught) {
          // Draw falling object
          ctx.font = o.size + 'px serif';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(o.emoji, o.x, o.y);

          // Point label beneath emoji
          ctx.font = '11px monospace';
          ctx.fillStyle = o.pts > 0 ? '#4aff6b' : '#ff6b6b';
          ctx.textBaseline = 'alphabetic';
          ctx.fillText((o.pts > 0 ? '+' : '') + o.pts, o.x, o.y + o.size * 0.65);
        } else {
          // Pop score float
          ctx.font = 'bold 15px monospace';
          ctx.fillStyle = o.pts > 0 ? '#4aff6b' : '#ff4444';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'alphabetic';
          ctx.fillText((o.pts > 0 ? '+' : '') + o.pts, o.x, o.popY);
        }

        ctx.restore();
      }

      // Draw basket
      var bx = self._basketX, by = self._basketY, bw = self._basketW, bh = 28;
      ctx.fillStyle = '#5a3e10';
      ctx.fillRect(bx, by, bw, bh);
      // Weave lines
      ctx.strokeStyle = '#8B6514';
      ctx.lineWidth = 1;
      for (var lx = bx + 8; lx < bx + bw; lx += 10) {
        ctx.beginPath(); ctx.moveTo(lx, by); ctx.lineTo(lx, by + bh); ctx.stroke();
      }
      ctx.beginPath(); ctx.moveTo(bx, by + bh * 0.45); ctx.lineTo(bx + bw, by + bh * 0.45); ctx.stroke();
      // Gold rim
      ctx.strokeStyle = '#C8961E';
      ctx.lineWidth = 2;
      ctx.strokeRect(bx, by, bw, bh);

      self._animFrame = requestAnimationFrame(loop);
    }
    self._animFrame = requestAnimationFrame(loop);
  },

  stop: function() {
    this._running = false;
    if (this._spawnTimer)  { clearTimeout(this._spawnTimer);        this._spawnTimer  = null; }
    if (this._animFrame)   { cancelAnimationFrame(this._animFrame); this._animFrame   = null; }
    if (this._keyHandler)  document.removeEventListener('keydown', this._keyHandler);
    if (this._keyUpHandler)document.removeEventListener('keyup',   this._keyUpHandler);
    if (this._canvas) {
      this._canvas.onclick      = null;
      this._canvas.ontouchstart = null;
      this._canvas.ontouchmove  = null;
      this._canvas.ontouchend   = null;
    }
  },
};

// ─── Juggle Master (Parkmusement) ──────────────────────────────────────────
// Click/tap moves ball horizontally toward the click X AND bounces it.
// At combo 10 a second ball spawns; game ends only when ALL balls drop.

var JuggleMasterGame = {
  duration: 45,
  _canvas: null,
  _ctx: null,
  _running: false,
  _animFrame: null,
  _balls: [],              // array so more balls can be added at higher streaks later
  _combo: 0,
  _hitZoneY: 0,
  _hitZoneH: 0,
  _clickCooldown: 0,
  _flash: null,
  _secondBallSpawned: false,

  _makeBall: function(canvas, xOff) {
    return {
      x:       canvas.width / 2 + (xOff || 0),
      y:       canvas.height * 0.20,
      vx:      0,
      vy:      200,
      gravity: 380,
      floorY:  canvas.height * 0.88,
    };
  },

  init: function(canvas, ctx) {
    this._canvas = canvas;
    this._ctx = ctx;
    this._running = true;
    this._combo = 0;
    this._clickCooldown = 0;
    this._flash = null;
    this._secondBallSpawned = false;

    this._hitZoneY = canvas.height * 0.62;
    this._hitZoneH = canvas.height * 0.14;
    this._balls    = [this._makeBall(canvas)];

    var self = this;
    var handler = this._handleClick.bind(this);
    canvas.onclick = handler;
    canvas.ontouchend = function(e) { e.preventDefault(); handler(e.changedTouches[0]); };
    this._render();
  },

  _handleClick: function(e) {
    if (!this._running || this._clickCooldown > 0) return;

    // Resolve click X for horizontal nudge
    var mx = this._canvas.width / 2;
    if (e) {
      var rect = this._canvas.getBoundingClientRect();
      var sx = this._canvas.width / rect.width;
      mx = ((e.clientX !== undefined ? e.clientX : e.pageX) - rect.left) * sx;
    }

    var hitAny = false;
    for (var i = 0; i < this._balls.length; i++) {
      var b = this._balls[i];
      var inZone = b.y >= this._hitZoneY && b.y <= this._hitZoneY + this._hitZoneH;
      if (!inZone) continue;
      hitAny = true;
      this._combo++;
      // Horizontal nudge: push ball toward click position (capped at ±200 px/s)
      b.vx = Math.max(-200, Math.min(200, (mx - b.x) * 1.5));
      b.vy = -(280 + Math.min(this._combo, 5) * 20);
      var pts = this._combo >= 3 ? 3 + this._combo : (this._combo >= 2 ? 4 : 3);
      MiniGameManager.addScore(pts);
      this._flash = { text: '+' + pts + (this._combo >= 2 ? ' ×' + this._combo + '!' : ''), color: '#4aff6b', t: 1.0 };
      if (window.GameSounds) { if (this._combo >= 2) GameSounds.minigameCombo(); else GameSounds.minigameHit(); }
    }

    if (!hitAny) {
      this._combo = 0;
      this._flash = { text: 'MISS!', color: '#ff6b6b', t: 0.8 };
      if (window.GameSounds) GameSounds.minigameMiss();
    } else if (this._combo >= 10 && !this._secondBallSpawned && this._balls.length === 1) {
      // Spawn second ball at streak 10
      this._secondBallSpawned = true;
      var b2 = this._makeBall(this._canvas, Math.random() > 0.5 ? 65 : -65);
      b2.vx = (Math.random() < 0.5 ? 1 : -1) * 60;
      this._balls.push(b2);
      this._flash = { text: '🎪 2ND BALL!', color: '#FFD700', t: 1.8 };
      if (window.GameSounds) GameSounds.minigameCombo();
    }

    this._clickCooldown = 0.35;
  },

  _render: function() {
    if (!this._running) return;
    var self = this;
    var ctx = this._ctx;
    var canvas = this._canvas;
    var last = null;
    var BALL_R  = 22;
    var BALL_EMOJIS = ['🎪', '⭐'];

    function loop(ts) {
      if (!self._running) return;
      var dt = last ? Math.min((ts - last) / 1000, 0.05) : 0.016;
      last = ts;

      if (self._clickCooldown > 0) self._clickCooldown -= dt;

      ctx.fillStyle = '#0a0915';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Physics — floor drops or respawns ball
      for (var i = self._balls.length - 1; i >= 0; i--) {
        var b = self._balls[i];
        b.vy += b.gravity * MiniGameManager.getDifficultyMult() * dt;
        b.y  += b.vy * dt;
        b.x  += b.vx * dt;
        // Horizontal wall bounce (slight energy loss)
        if (b.x < BALL_R)               { b.x = BALL_R;               b.vx =  Math.abs(b.vx) * 0.85; }
        if (b.x > canvas.width - BALL_R) { b.x = canvas.width - BALL_R; b.vx = -Math.abs(b.vx) * 0.85; }
        // Floor
        if (b.y >= b.floorY) {
          self._combo = 0;
          if (window.GameSounds) GameSounds.minigameMiss();
          if (self._balls.length === 1) {
            // Last ball — bounce in place so the game never empties
            b.y  = b.floorY;
            b.vy = -Math.max(Math.abs(b.vy) * 0.7, 180);
            self._flash = { text: '⤴️ BOUNCE!', color: '#ffaa44', t: 1.0 };
          } else {
            // Extra ball dropped — splice it out, single ball keeps playing
            self._flash = { text: '💧 DROPPED!', color: '#ff6b6b', t: 1.0 };
            self._balls.splice(i, 1);
          }
        }
      }

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

      // Draw balls
      var anyInZone = false;
      for (var i = 0; i < self._balls.length; i++) {
        var b = self._balls[i];
        var inZone = b.y >= hz && b.y <= hz + hh;
        if (inZone) anyInZone = true;
        ctx.beginPath();
        ctx.arc(b.x, b.y, BALL_R, 0, Math.PI * 2);
        ctx.fillStyle = inZone ? '#FFD700' : '#6688cc';
        ctx.fill();
        ctx.strokeStyle = inZone ? '#fff' : '#334488';
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.font = '26px serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(BALL_EMOJIS[i] || '🎪', b.x, b.y);
        ctx.textBaseline = 'alphabetic';
      }

      // Instruction
      ctx.textAlign = 'center';
      ctx.fillStyle = anyInZone ? '#FFD700' : '#556';
      ctx.font = 'bold 14px monospace';
      ctx.fillText(anyInZone ? '👆 CLICK NOW!' : 'Wait for the zone...', canvas.width / 2, 26);

      // Combo
      if (self._combo >= 2) {
        ctx.fillStyle = '#FFD700';
        ctx.font = 'bold 18px monospace';
        ctx.fillText('🔥 ×' + self._combo + ' COMBO!', canvas.width / 2, 52);
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
    if (this._spawnTimer) { clearTimeout(this._spawnTimer); this._spawnTimer = null; }
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
        if (window.GameSounds) GameSounds.runeChime(rn.idx);
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
            if (window.GameSounds) GameSounds.runeChime(self._sequence[self._showIdx]);
            self._showIdx++;
            // Cap at 1.5× so the sequence remains readable even late in the game
            self._showTimer = 0.85 / Math.min(MiniGameManager.getDifficultyMult(), 1.5);
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
    function _schedTarget() {
      if (!self._running) return;
      self._spawnTarget();
      self._spawnTimer = setTimeout(_schedTarget, 780 / MiniGameManager.getDifficultyMult());
    }
    _schedTarget();

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
    var mult = MiniGameManager.getDifficultyMult();
    var cfgs = {
      monster: { emoji:'👹', pts: 4,  color:'#ff6b6b', life:2.0 / mult },
      elite:   { emoji:'💀', pts:10,  color:'#FF8C00', life:1.3 / mult },
      penguin: { emoji:'🐧', pts:-6,  color:'#4aafff', life:1.9 / mult },
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
