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
    hud.style.cssText = 'display:flex;gap:16px;align-items:center;margin-bottom:10px;font-family:monospace;font-size:16px;flex-wrap:wrap;justify-content:center;';
    hud.innerHTML =
      '<span id="mg-title" style="color:#4aff6b;font-size:17px;font-weight:bold;"></span>' +
      '<span id="mg-score" style="color:#FFD700;">SCORE: 0</span>' +
      '<span id="mg-timer" style="color:#FF6B6B;">TIME: 15</span>' +
      '<button onclick="MiniGameManager.close()" style="background:#2a2a3a;color:#B8B8D0;border:1px solid #555;padding:3px 10px;cursor:pointer;font-family:monospace;font-size:16px;">✕ QUIT</button>';

    var cw = Math.min(window.innerWidth - 24, 500);
    var ch = Math.min(window.innerHeight - 130, 380);

    var canvas = document.createElement('canvas');
    canvas.id = 'mg-canvas';
    canvas.width = cw;
    canvas.height = ch;
    canvas.style.cssText = 'display:block;background:#111;border:2px solid #2a2a4a;touch-action:none;';

    var inst = document.createElement('div');
    inst.id = 'mg-instruction';
    inst.style.cssText = 'color:#8888A8;font-size:16px;margin-top:7px;text-align:center;max-width:500px;padding:0 10px;';

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
      grand_piano:   '🎹 PIANO RECITAL',
      horny_jail:    '🚪 CELL BLOCK BEAT',
      sports_centre: '🤾 SPORT TOSS',
    };
    var insts = {
      sea_lion_pit:  'Click fish to catch them! Avoid puffer fish! Golden fish = jackpot!',
      club_soda:     'Catch leaves 🌿 (+5) & ice 🧊 (+3) in your basket! Dodge toxic shrooms 🍄 (−5)! Arrow keys or drag.',
      parkmusement:  'Click in the green zone to bounce the ball! Hit 🎯 targets for +8 pts! Click off-center to steer.',
      cursed_temple: 'Watch the rune sequence, then repeat it in order!',
      guillotine:    'Whack monsters & elites! Never hit a penguin!',
      grand_piano:   'Watch the keys light up, then play them back in order!',
      horny_jail:    'Watch the door shake out the beat, then knock it back — match the COUNT and the TIMING between knocks!',
      sports_centre: 'PRESS & HOLD to wind up, RELEASE in the green zone to score a hit!',
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
      case 'grand_piano':   this._activeGame = PianoRecitalGame; break;
      case 'horny_jail':    this._activeGame = CellBlockBeatGame; break;
      case 'sports_centre': this._activeGame = SportTossGame;    break;
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
    // Raw, uncapped score -- stored/displayed as-is now so real records and
    // leaderboards aren't artificially ceilinged (see app.py's
    // minigame_complete/calculate_minigame_rewards for the backend side of
    // this). Used to be hard-clamped to 100 here; the S/A/B/C/D grade below
    // still grades against that old 0-100 scale so the lettering keeps
    // meaning what it always did.
    var finalScore = this._score;
    var gradeScore = Math.min(100, finalScore);
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
    if (gradeScore >= 80) { grade = 'S'; gradeColor = '#FFD700'; }
    else if (gradeScore >= 60) { grade = 'A'; gradeColor = '#4aff6b'; }
    else if (gradeScore >= 40) { grade = 'B'; gradeColor = '#4aafff'; }
    else if (gradeScore >= 20) { grade = 'C'; gradeColor = '#FF8C00'; }
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
        'padding:12px 28px;font-size:16px;font-family:monospace;',
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
// Click/tap in the hit zone bounces the ball. Click direction is INVERTED:
// clicking right of ball center deflects it LEFT (billiard-style).
// At combo 10 a second ball spawns. Targets spawn periodically for bonus pts.

var JuggleMasterGame = {
  duration: 45,
  _canvas: null,
  _ctx: null,
  _running: false,
  _animFrame: null,
  _balls: [],
  _combo: 0,
  _hitZoneY: 0,
  _hitZoneH: 0,
  _clickCooldown: 0,
  _flash: null,
  _secondBallSpawned: false,
  _targets: [],
  _spawnTimer: null,
  _nextSpawnIn: 3.0,

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

  _makeTarget: function(canvas) {
    var icons  = ['🎯', '⭐', '💎', '🌟'];
    var colors = ['#FFD700', '#4aff6b', '#A86EFF', '#FF7FE5'];
    var idx = Math.floor(Math.random() * icons.length);
    var r = 14;
    return {
      x: r + Math.random() * (canvas.width - r * 2),
      y: canvas.height * (0.12 + Math.random() * 0.38),
      r: r,
      icon:  icons[idx],
      color: colors[idx],
      life: 5.0,
      pts:  8,
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
    this._targets = [];
    this._nextSpawnIn = 3.0;

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
      // INVERTED deflection: click right of ball → ball goes left (billiard-style).
      // Multiplier 3.0 and cap ±380 for sharper, more skill-dependent angles.
      b.vx = Math.max(-380, Math.min(380, (b.x - mx) * 3.0));
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
    var TARGET_R = 14;
    var BALL_EMOJIS = ['🎪', '⭐'];

    function loop(ts) {
      if (!self._running) return;
      var dt = last ? Math.min((ts - last) / 1000, 0.05) : 0.016;
      last = ts;

      if (self._clickCooldown > 0) self._clickCooldown -= dt;

      ctx.fillStyle = '#0a0915';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Target spawn timer
      self._nextSpawnIn -= dt;
      if (self._nextSpawnIn <= 0 && self._targets.length < 3) {
        self._targets.push(self._makeTarget(canvas));
        self._nextSpawnIn = 3.0 + Math.random() * 2.0;
      }

      // Ball physics
      for (var i = self._balls.length - 1; i >= 0; i--) {
        var b = self._balls[i];
        b.vy += b.gravity * MiniGameManager.getDifficultyMult() * dt;
        b.y  += b.vy * dt;
        b.x  += b.vx * dt;
        if (b.x < BALL_R)               { b.x = BALL_R;               b.vx =  Math.abs(b.vx) * 0.85; }
        if (b.x > canvas.width - BALL_R) { b.x = canvas.width - BALL_R; b.vx = -Math.abs(b.vx) * 0.85; }
        if (b.y >= b.floorY) {
          self._combo = 0;
          if (window.GameSounds) GameSounds.minigameMiss();
          if (self._balls.length === 1) {
            b.y  = b.floorY;
            b.vy = -Math.max(Math.abs(b.vy) * 0.7, 180);
            self._flash = { text: '⤴️ BOUNCE!', color: '#ffaa44', t: 1.0 };
          } else {
            self._flash = { text: '💧 DROPPED!', color: '#ff6b6b', t: 1.0 };
            self._balls.splice(i, 1);
          }
        }
      }

      // Target collision + expiry
      for (var ti = self._targets.length - 1; ti >= 0; ti--) {
        var tgt = self._targets[ti];
        tgt.life -= dt;
        var hit = false;
        for (var bi = 0; bi < self._balls.length; bi++) {
          var bl = self._balls[bi];
          var dx = bl.x - tgt.x, dy = bl.y - tgt.y;
          if (dx * dx + dy * dy < (BALL_R + tgt.r) * (BALL_R + tgt.r)) { hit = true; break; }
        }
        if (hit || tgt.life <= 0) {
          if (hit) {
            MiniGameManager.addScore(tgt.pts);
            self._flash = { text: '🎯 +' + tgt.pts + '!', color: tgt.color, t: 1.2 };
            if (window.GameSounds) GameSounds.minigameCombo();
          }
          self._targets.splice(ti, 1);
        }
      }

      // Draw targets
      for (var ti = 0; ti < self._targets.length; ti++) {
        var tgt = self._targets[ti];
        var alpha = tgt.life < 1 ? tgt.life : 1;
        ctx.globalAlpha = alpha;
        ctx.beginPath();
        ctx.arc(tgt.x, tgt.y, tgt.r, 0, Math.PI * 2);
        ctx.fillStyle = tgt.color + '33';
        ctx.fill();
        ctx.strokeStyle = tgt.color;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.font = '18px serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(tgt.icon, tgt.x, tgt.y);
        ctx.textBaseline = 'alphabetic';
        ctx.globalAlpha = 1;
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

      // Top instruction
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

// ─── Piano Recital (Grand Piano) ───────────────────────────────────────────
// Same show/repeat structure as RuneMemoryGame, re-themed with piano keys
// laid out in a row instead of runes in a circle, and GameSounds.pianoKey()
// instead of runeChime() for a distinct note per key.

var PianoRecitalGame = {
  duration: 50,
  _canvas: null,
  _ctx: null,
  _running: false,
  _animFrame: null,
  _keys: [],
  _sequence: [],
  _input: [],
  _phase: 'show', // show | input | result
  _showIdx: 0,
  _showTimer: 0,
  _resultTimer: 0,
  _correct: null,
  _round: 0,

  NOTES:  ['C','D','E','F','G','A','B','C'],
  COLORS: ['#FF6B6B','#FF8C00','#FFD700','#4aff6b','#4aafff','#A86EFF','#FF6BC1','#FF6B6B'],

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

    var n = 8;
    var keyW = Math.min((canvas.width - 20) / n, 52);
    var keyH = keyW * 2.1;
    var startX = (canvas.width - keyW * n) / 2;
    var y = canvas.height / 2 - keyH / 2 + 20;
    this._keys = [];
    for (var i = 0; i < n; i++) {
      this._keys.push({ x: startX + i * keyW, y: y, w: keyW - 3, h: keyH, lit: false, litT: 0, idx: i });
    }

    this._startRound();
    var handler = this._handleClick.bind(this);
    canvas.onclick = handler;
    canvas.ontouchend = function(e) { e.preventDefault(); handler(e.changedTouches[0]); };
    this._render();
  },

  _startRound: function() {
    this._round++;
    this._sequence.push(Math.floor(Math.random() * 8));
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

    for (var i = 0; i < this._keys.length; i++) {
      var k = this._keys[i];
      if (mx >= k.x && mx <= k.x + k.w && my >= k.y && my <= k.y + k.h) {
        this._input.push(k.idx);
        k.lit = true; k.litT = 0.5;
        if (window.GameSounds) GameSounds.pianoKey(k.idx);
        var pos = this._input.length - 1;
        if (k.idx !== this._sequence[pos]) {
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

      ctx.fillStyle = '#0e0a06';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Phase update
      if (self._phase === 'show') {
        self._showTimer -= dt;
        if (self._showTimer <= 0) {
          if (self._showIdx < self._sequence.length) {
            self._keys[self._sequence[self._showIdx]].lit = true;
            self._keys[self._sequence[self._showIdx]].litT = 0.65;
            if (window.GameSounds) GameSounds.pianoKey(self._sequence[self._showIdx]);
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
            self._sequence = [Math.floor(Math.random() * 8)];
            self._input = []; self._phase = 'show'; self._showIdx = 0; self._showTimer = 0.5;
          }
        }
      }

      // Keys
      for (var i = 0; i < self._keys.length; i++) {
        var k = self._keys[i];
        if (k.litT > 0) k.litT -= dt;
        var lit = k.lit && k.litT > 0;
        if (k.lit && k.litT <= 0) k.lit = false;

        ctx.fillStyle = lit ? self.COLORS[k.idx] : '#f0e8d8';
        ctx.fillRect(k.x, k.y, k.w, k.h);
        ctx.strokeStyle = '#2a2018';
        ctx.lineWidth = 2;
        ctx.strokeRect(k.x, k.y, k.w, k.h);

        ctx.fillStyle = lit ? '#000' : '#4a3a28';
        ctx.font = 'bold 15px monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'alphabetic';
        ctx.fillText(self.NOTES[k.idx], k.x + k.w / 2, k.y + k.h - 10);
      }

      // HUD text
      ctx.textAlign = 'center';
      ctx.textBaseline = 'alphabetic';
      if (self._phase === 'show') {
        ctx.fillStyle = '#FFD700';
        ctx.font = 'bold 15px monospace';
        ctx.fillText('MEMORIZE THE MELODY...', canvas.width / 2, 28);
        ctx.fillStyle = '#B8B8D0';
        ctx.font = '12px monospace';
        ctx.fillText('Round ' + self._round + ' — ' + self._sequence.length + ' note(s)', canvas.width / 2, 48);
      } else if (self._phase === 'input') {
        ctx.fillStyle = '#4aff6b';
        ctx.font = 'bold 15px monospace';
        ctx.fillText('YOUR TURN! (' + self._input.length + ' / ' + self._sequence.length + ')', canvas.width / 2, 28);
        ctx.fillStyle = '#B8B8D0';
        ctx.font = '12px monospace';
        ctx.fillText('Play the keys in order', canvas.width / 2, 48);
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

// ─── Cell Block Beat (Horny Jail) ───────────────────────────────────────────
// Timing-based, deliberately NOT a Rune Memory reskin: Rune Memory only
// grades WHICH rune the player taps, in order -- position, never time (see
// RuneMemoryGame._handleClick above, it just compares rn.idx to
// this._sequence[pos]; nothing there ever reads a timestamp). This game
// shows a pattern of clicks with specific gaps between them (ms) -- some
// slow/even, some fast/back-to-back -- then grades the player's own taps on
// TWO axes: did they land the right COUNT of taps, and did each gap between
// two consecutive taps land close to the matching target gap. Screen
// position is irrelevant (one big tap zone), only rhythm matters.
var CellBlockBeatGame = {
  duration: 45,
  _canvas: null,
  _ctx: null,
  _running: false,
  _animFrame: null,

  _phase: 'show',   // show | input | result
  _round: 0,
  _pattern: [],     // target gaps (ms) between consecutive taps -- length tapCount-1
  _tapCount: 0,

  // Show-phase playback state
  _showBeatIdx: 0,      // how many beats have played so far this round
  _showNextBeatAt: 0,   // performance.now() timestamp the next beat plays at
  _showPulse: 0,        // 0-1, decays after each beat -- drives the circle's flash

  // Input-phase state
  _inputTaps: [],        // performance.now() timestamps of the player's taps this round
  _inputDeadline: 0,     // performance.now() timestamp -- round auto-ends (remaining taps = Miss) past this
  _lastBand: null,       // 'perfect' | 'good' | 'miss' | 'start' -- last graded tap, for HUD/circle color
  _tapPulse: 0,          // 0-1, decays after each tap

  _resultUntil: 0,
  _resultCounts: null,   // {perfect, good, miss} tallied for the round just finished

  // Door presentation state -- the beat/tap is shown as a door on its frame
  // taking a hit each beat (see _render()'s door group below) instead of a
  // free-floating circle. _shake/_particles/_swing* are purely cosmetic;
  // none of them feed into timing or grading.
  _shake:      0,   // 0-1, decays like _showPulse/_tapPulse -- door jolt magnitude
  _swingAngle: 0,   // "OCCUPIED" sign pendulum angle (radians), hung off the knob
  _swingVel:   0,
  _particles:  [],  // dust puffs off the top of the door frame

  // Timing windows (ms): how far an actual inter-tap gap can be from the
  // pattern's target gap and still count as Perfect/Good. Past GOOD_WINDOW_MS
  // is a Miss -- no credit, same "no credit for Miss" as Bits & Bops' Hammer
  // Time bands this is modeled on.
  PERFECT_WINDOW_MS: 80,
  GOOD_WINDOW_MS:    180,

  // Points per graded gap. Calibrated against the shared 0-100 S/A/B/C/D
  // grade scale (_showResults()'s gradeScore) so a strong run reaches S
  // around round 4-5, not round 2 -- rounds ramp mostly via MORE graded
  // gaps (tapCount grows) rather than steep per-tap point growth.
  PERFECT_PTS: 6,
  GOOD_PTS:    3,

  // Gap durations (ms) patterns are built from -- SLOW is the evenly-spaced
  // "click...click...click" baseline; MEDIUM/FAST mix in the "click-click"
  // back-to-back feel the spec calls for, phased in from round 2 onward.
  SLOW_GAP:   650,
  MEDIUM_GAP: 400,
  FAST_GAP:   180,

  init: function(canvas, ctx) {
    this._canvas = canvas;
    this._ctx = ctx;
    this._running = true;
    this._round = 0;
    this._resultCounts = null;
    this._particles = [];
    this._swingAngle = 0;
    this._swingVel = 0;

    var handler = this._handleTap.bind(this);
    canvas.onclick = handler;
    canvas.ontouchend = function(e) { e.preventDefault(); handler(e.changedTouches[0]); };

    this._startRound();
    this._render();
  },

  // Round N: tapCount grows 3 -> 8 (capped) as N increases; the gaps between
  // those taps start all-SLOW (round 1, a clean baseline) and increasingly
  // mix in MEDIUM/FAST gaps as N grows -- "more clicks and/or more complex
  // spacing patterns" per round, exactly as specced.
  _buildPattern: function(round) {
    var tapCount = Math.min(2 + round, 8);
    var fastChance = Math.min(0.15 * (round - 1), 0.45);
    var medChance  = Math.min(0.15 * (round - 1), 0.35);
    var gaps = [];
    for (var i = 0; i < tapCount - 1; i++) {
      var gap = this.SLOW_GAP;
      if (round > 1) {
        var roll = Math.random();
        if (roll < fastChance) gap = this.FAST_GAP;
        else if (roll < fastChance + medChance) gap = this.MEDIUM_GAP;
      }
      gaps.push(gap);
    }
    return { tapCount: tapCount, gaps: gaps };
  },

  _startRound: function() {
    this._round++;
    var built = this._buildPattern(this._round);
    this._tapCount = built.tapCount;
    this._pattern = built.gaps;
    this._phase = 'show';
    this._showBeatIdx = 0;
    this._showPulse = 0;
    this._showNextBeatAt = performance.now() + 500; // brief pause before the round starts
    this._inputTaps = [];
    this._lastBand = null;
  },

  // Kicks the door's cosmetic reaction -- jolt magnitude, a nudge to the
  // "OCCUPIED" sign's pendulum, and a few dust puffs off the frame. Purely
  // presentational, called from both the show-phase beat and every tap.
  _kick: function(mag) {
    this._shake = 1;
    this._swingVel += (Math.random() < 0.5 ? -1 : 1) * 2.4 * (mag || 1);
    for (var i = 0; i < 4; i++) {
      this._particles.push({
        x: (Math.random() - 0.5) * 14,
        y: 0,
        vx: (Math.random() - 0.5) * 22,
        vy: -20 - Math.random() * 30,
        life: 0.5 + Math.random() * 0.25,
        maxLife: 0.75,
        size: 1.6 + Math.random() * 1.6,
      });
    }
  },

  _handleTap: function(e) {
    if (!this._running || this._phase !== 'input') return;
    // Extra taps past tapCount are ignored rather than punished -- an
    // accidental double-click shouldn't cost a Miss the player never
    // actually had a gap to misjudge.
    if (this._inputTaps.length >= this._tapCount) return;

    var now = performance.now();
    this._inputTaps.push(now);
    this._tapPulse = 1;

    var i = this._inputTaps.length - 1;
    if (i === 0) {
      // The first tap has no preceding gap to grade -- it only marks t0 that
      // every later gap is measured from.
      this._lastBand = 'start';
      if (window.GameSounds) GameSounds.minigameKnockStart();
      this._kick(0.6);
    } else {
      var actualGap = this._inputTaps[i] - this._inputTaps[i - 1];
      var targetGap = this._pattern[i - 1];
      var diff = Math.abs(actualGap - targetGap);
      var band, pts;
      if (diff <= this.PERFECT_WINDOW_MS)     { band = 'perfect'; pts = this.PERFECT_PTS; }
      else if (diff <= this.GOOD_WINDOW_MS)   { band = 'good';    pts = this.GOOD_PTS;    }
      else                                    { band = 'miss';    pts = 0;                }
      this._lastBand = band;
      if (pts > 0) MiniGameManager.addScore(pts);
      if (!this._resultCounts) this._resultCounts = { perfect: 0, good: 0, miss: 0 };
      this._resultCounts[band]++;
      if (window.GameSounds) {
        if (band === 'perfect') GameSounds.minigameKnockPerfect();
        else if (band === 'good') GameSounds.minigameKnockGood();
        else GameSounds.minigameKnockMiss();
      }
      this._kick(band === 'miss' ? 0.5 : 1);
    }

    if (this._inputTaps.length >= this._tapCount) this._endRoundInput(false);
  },

  // Heart doorknob -- the "click target" the whole door presentation is
  // organized around.
  _drawHeart: function(ctx, cx, cy, size, color) {
    var top = size * 0.3;
    ctx.beginPath();
    ctx.moveTo(cx, cy + top);
    ctx.bezierCurveTo(cx, cy, cx - size / 2, cy, cx - size / 2, cy + top);
    ctx.bezierCurveTo(cx - size / 2, cy + (size + top) / 2, cx, cy + (size + top) / 2, cx, cy + size);
    ctx.bezierCurveTo(cx, cy + (size + top) / 2, cx + size / 2, cy + (size + top) / 2, cx + size / 2, cy + top);
    ctx.bezierCurveTo(cx + size / 2, cy, cx, cy, cx, cy + top);
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
  },

  // timedOut=true: the player ran out of time before landing tapCount taps.
  // Every gap that never got a chance to be graded (including all of them,
  // if they never tapped at all) is scored as a Miss -- reproducing the
  // wrong COUNT is graded here, not just a wrong gap.
  _endRoundInput: function(timedOut) {
    if (timedOut) {
      if (!this._resultCounts) this._resultCounts = { perfect: 0, good: 0, miss: 0 };
      var gradedGaps = Math.max(0, this._inputTaps.length - 1);
      var totalGaps  = this._tapCount - 1;
      this._resultCounts.miss += Math.max(0, totalGaps - gradedGaps);
    }
    this._phase = 'result';
    this._resultUntil = performance.now() + 1400;
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
      var now = performance.now();

      // ── background: dim hallway, vignette toward the door ──
      var cx = canvas.width / 2, cy = canvas.height / 2 - 6;
      var grad = ctx.createRadialGradient(cx, cy, canvas.height * 0.1, cx, cy, canvas.height * 0.75);
      grad.addColorStop(0, '#1a0f22');
      grad.addColorStop(1, '#0a0612');
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = '#241a30';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(0, canvas.height * 0.87);
      ctx.lineTo(canvas.width, canvas.height * 0.87);
      ctx.stroke();

      if (self._phase === 'show') {
        if (self._showBeatIdx < self._tapCount && now >= self._showNextBeatAt) {
          self._showPulse = 1;
          if (window.GameSounds) GameSounds.minigameThump();
          self._kick(1);
          var justPlayedIdx = self._showBeatIdx;
          self._showBeatIdx++;
          self._showNextBeatAt = now + (self._showBeatIdx < self._tapCount
            ? self._pattern[justPlayedIdx]
            : 500); // breathing room after the last cue before input opens
        } else if (self._showBeatIdx >= self._tapCount && now >= self._showNextBeatAt) {
          self._phase = 'input';
          // Deadline anchored from when input OPENS (not from show's start),
          // so the pattern's own playback length never eats into the
          // player's actual reaction/tap time.
          var totalGapMs = self._pattern.reduce(function(a, b) { return a + b; }, 0);
          self._inputDeadline = now + totalGapMs + 2500;
        }
        if (self._showPulse > 0) self._showPulse = Math.max(0, self._showPulse - dt * 3);
      } else if (self._phase === 'input') {
        if (self._tapPulse > 0) self._tapPulse = Math.max(0, self._tapPulse - dt * 3);
        if (now >= self._inputDeadline) self._endRoundInput(true);
      } else if (self._phase === 'result') {
        if (now >= self._resultUntil) {
          self._resultCounts = null;
          self._startRound();
        }
      }

      // ── cosmetic physics: shake decay, sign pendulum, dust particles ──
      if (self._shake > 0) self._shake = Math.max(0, self._shake - dt * 4);
      self._swingVel += -14 * self._swingAngle * dt;
      self._swingVel *= (1 - Math.min(1, dt * 1.4));
      self._swingAngle += self._swingVel * dt;
      for (var pi = self._particles.length - 1; pi >= 0; pi--) {
        var p = self._particles[pi];
        p.x += p.vx * dt; p.y += p.vy * dt; p.vy += 60 * dt;
        p.life -= dt;
        if (p.life <= 0) self._particles.splice(pi, 1);
      }

      var pulse = self._phase === 'show' ? self._showPulse : self._tapPulse;
      var color = '#F5C518';
      if (self._phase === 'input') {
        if (self._lastBand === 'perfect') color = '#FFD700';
        else if (self._lastBand === 'good') color = '#4aafff';
        else if (self._lastBand === 'miss') color = '#ff6b6b';
        else color = '#4aff6b';
      }

      // ── door group (shaken) ──
      ctx.save();
      var shakeX = (Math.random() - 0.5) * 10 * self._shake;
      var shakeY = (Math.random() - 0.5) * 5 * self._shake;
      ctx.translate(shakeX, shakeY);

      var doorW = canvas.width * 0.30;
      var doorH = canvas.height * 0.54;
      var doorX = cx - doorW / 2;
      var doorY = canvas.height * 0.22;

      ctx.fillStyle = '#3a2317';
      ctx.fillRect(doorX - 10, doorY - 10, doorW + 20, doorH + 14);

      ctx.fillStyle = '#B84A82';
      ctx.fillRect(doorX, doorY, doorW, doorH);
      ctx.strokeStyle = 'rgba(0,0,0,0.28)';
      ctx.lineWidth = 2;
      ctx.strokeRect(doorX + doorW * 0.12, doorY + doorH * 0.30, doorW * 0.76, doorH * 0.24);
      ctx.strokeRect(doorX + doorW * 0.12, doorY + doorH * 0.60, doorW * 0.76, doorH * 0.28);

      // barred window, glowing with the beat
      var winW = doorW * 0.42, winH = doorH * 0.14;
      var winX = cx - winW / 2, winY = doorY + doorH * 0.08;
      ctx.fillStyle = color;
      ctx.globalAlpha = 0.22 + pulse * 0.55;
      ctx.fillRect(winX, winY, winW, winH);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = '#241408';
      ctx.lineWidth = 2;
      ctx.strokeRect(winX, winY, winW, winH);
      for (var b = 1; b < 4; b++) {
        var bx = winX + (winW / 4) * b;
        ctx.beginPath();
        ctx.moveTo(bx, winY);
        ctx.lineTo(bx, winY + winH);
        ctx.stroke();
      }

      // doorknob (heart)
      var knobX = doorX + doorW * 0.87, knobY = doorY + doorH * 0.56;
      var knobSize = doorW * 0.16 * (1 + pulse * 0.3);
      self._drawHeart(ctx, knobX, knobY - knobSize * 0.55, knobSize, color);

      // "OCCUPIED" sign, swinging from the knob
      ctx.save();
      ctx.translate(knobX, knobY);
      ctx.rotate(self._swingAngle);
      ctx.strokeStyle = '#8a8a9a';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(0, 16);
      ctx.stroke();
      var signW = 58, signH = 20;
      ctx.fillStyle = '#f2e9d8';
      ctx.strokeStyle = '#3a2317';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(-signW / 2, 16, signW, signH, 3);
      else ctx.rect(-signW / 2, 16, signW, signH);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = '#B0304F';
      ctx.font = 'bold 9.5px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('OCCUPIED', 0, 16 + signH / 2 + 0.5);
      ctx.restore();

      // dust particles off the top of the frame
      ctx.fillStyle = '#cfc3a8';
      for (var dpi = 0; dpi < self._particles.length; dpi++) {
        var dp = self._particles[dpi];
        ctx.globalAlpha = Math.max(0, dp.life / dp.maxLife) * 0.85;
        ctx.beginPath();
        ctx.arc(cx + dp.x, doorY - 6 + dp.y, dp.size, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      // knock: fist punches toward the door on _tapPulse, from off-panel
      if (self._phase !== 'show' && self._tapPulse > 0) {
        var reach = (1 - self._tapPulse) * 34;
        var fx = knobX - 46 + reach;
        var fy = knobY - knobSize * 0.55;
        ctx.save();
        ctx.globalAlpha = Math.min(1, self._tapPulse * 1.4);
        ctx.font = '26px serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('✊', fx, fy);
        ctx.restore();
      }

      ctx.restore(); // door group

      // ── HUD text (unshaken) ──
      ctx.textAlign = 'center';
      ctx.textBaseline = 'alphabetic';
      if (self._phase === 'show') {
        ctx.fillStyle = '#F5C518';
        ctx.font = 'bold 15px monospace';
        ctx.fillText('WATCH THE DOOR...', cx, 28);
        ctx.fillStyle = '#B8B8D0';
        ctx.font = '12px monospace';
        ctx.fillText('Round ' + self._round + ' — ' + self._tapCount + ' knock(s)', cx, 48);
      } else if (self._phase === 'input') {
        ctx.fillStyle = '#4aff6b';
        ctx.font = 'bold 15px monospace';
        ctx.fillText('KNOCK IT BACK! (' + self._inputTaps.length + ' / ' + self._tapCount + ')', cx, 28);
        ctx.fillStyle = '#B8B8D0';
        ctx.font = '12px monospace';
        var bandLabel = self._lastBand === 'perfect' ? 'PERFECT KNOCK!'
          : self._lastBand === 'good' ? 'GOOD KNOCK'
          : self._lastBand === 'miss' ? 'MISSED KNOCK'
          : 'Knock the beat back';
        ctx.fillText(bandLabel, cx, 48);
      } else if (self._phase === 'result') {
        var rc = self._resultCounts || { perfect: 0, good: 0, miss: 0 };
        ctx.fillStyle = '#A86EFF';
        ctx.font = 'bold 16px monospace';
        ctx.fillText('ROUND ' + self._round + ' COMPLETE', cx, 28);
        ctx.fillStyle = '#B8B8D0';
        ctx.font = '12px monospace';
        ctx.fillText('★' + rc.perfect + '  ✓' + rc.good + '  ✗' + rc.miss, cx, 48);
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

// ─── Sport Toss (Penguin Sports Centre) ─────────────────────────────────────
// Throw-COUNT-limited, not time-limited like every other game here (though
// `duration` above still caps the session as a safety net -- see
// _finishSession() below for how a normal run ends earlier than that).
// Genuinely new mechanic: press-and-hold charges a power meter that
// oscillates 0-100 back and forth; releasing reads the meter's value at that
// instant as the throw's power, and only a release landing inside that
// throw's own randomized target zone (different every throw, never the same
// twice) counts as a hit -- release too early and it falls short, hold too
// long and it overshoots. Binary hit/miss per throw, not graded bands like
// CellBlockBeatGame's Perfect/Good/Miss -- the reward spec's own "per
// successful hit" phrasing reads as a discrete outcome, and giving the two
// newest minigames different scoring shapes (banded vs. binary) keeps them
// feeling distinct rather than reskins of each other. Handball/dodgeball
// framing throughout (🐧/🥅/🤾) -- no weapon or shooting-range visuals or
// text anywhere here.
var SportTossGame = {
  duration: 55,       // generous safety cap -- THROW_COUNT below is what
                       // actually ends a normal session (_finishSession()).
  THROW_COUNT: 7,

  MIN_TARGET: 15,      // target zone center is randomized within this power
  MAX_TARGET: 95,      // range (0-100) each throw, kept off the very edges
                        // so it's always reachable both rising and falling.
  ZONE_HALF_WIDTH: 8,  // a release within +-8 power of the target is a hit
  FLIGHT_MS: 450,      // snowball travel time from penguin to landing spot

  _canvas: null,
  _ctx: null,
  _running: false,
  _animFrame: null,

  _throwIdx: 0,      // throws taken so far this session (0-based)
  _phase: 'ready',   // ready | charging | throwing | result
  _power: 0,         // 0-100, current gauge value while charging
  _direction: 1,     // 1 while rising toward 100, -1 while falling toward 0
  _cycleMs: 900,     // ms for the gauge to cross 0->100 (or 100->0) -- shrinks each throw
  _target: 50,
  _outcome: null,    // 'hit' | 'short' | 'over'
  _landingX: 0,
  _flightStart: 0,
  _resultUntil: 0,
  _leanT: 0,         // 0-1, decays after release -- the throw-snap lean
  _hits: 0,

  init: function(canvas, ctx) {
    this._canvas = canvas;
    this._ctx = ctx;
    this._running = true;
    this._throwIdx = 0;
    this._hits = 0;
    this._outcome = null;
    this._leanT = 0;

    // Scene layout -- computed once from this session's actual canvas size
    // (MiniGameManager sizes it per-viewport, so this can't be hardcoded
    // like a fixed-canvas preview could) and reused every frame. The 🎯
    // never moves; only where the snowball lands relative to it changes.
    var W = canvas.width, H = canvas.height;
    this._W = W; this._H = H;
    this._groundY = H * 0.78;
    this._penguinX = W * 0.16;
    this._targetX = W * 0.78;
    // To the penguin's LEFT (clear of its body/flipper, which reach from
    // about -27 to +50px of penguinX) rather than directly overhead -- an
    // overhead gauge would sit inside the character's own footprint on a
    // short canvas. Height uses a capped fraction of H so it still fits (and
    // scales down instead of clipping) on an unusually short viewport.
    this._gaugeX = this._penguinX - 50;
    this._gaugeW = 13;
    this._gaugeTop = this._groundY - Math.min(175, H * 0.62);
    this._gaugeBottom = this._groundY - Math.min(95, H * 0.34);
    this._pxPerPowerUnit = W / 232; // scales a power/target miss onto the ground
    this._landingMinX = this._penguinX + W * 0.09;
    this._landingMaxX = W * 0.965;

    var self = this;
    var down = function(e) { e.preventDefault(); self._startCharge(); };
    var up   = function(e) { e.preventDefault(); self._release(); };
    canvas.onmousedown  = down;
    canvas.onmouseup    = up;
    canvas.onmouseleave = up; // dragging off-canvas still releases, same as letting go of the button
    canvas.ontouchstart = down;
    canvas.ontouchend   = up;

    this._newTarget();
    this._render();
  },

  _newTarget: function() {
    this._target = this.MIN_TARGET + Math.random() * (this.MAX_TARGET - this.MIN_TARGET);
    this._phase = 'ready';
    this._power = 0;
    this._direction = 1;
    // Shrinking cycle = a tighter release window -- this game's stand-in
    // for a per-round difficulty ramp, since throws aren't rounds.
    this._cycleMs = Math.max(420, 900 - this._throwIdx * 70);
  },

  _startCharge: function() {
    if (!this._running || this._phase !== 'ready') return;
    this._phase = 'charging';
    this._power = 0;
    this._direction = 1;
    if (window.GameSounds) GameSounds.minigameStart();
  },

  _release: function() {
    if (!this._running || this._phase !== 'charging') return;
    var diff = this._power - this._target;
    var hit = Math.abs(diff) <= this.ZONE_HALF_WIDTH;
    this._outcome = hit ? 'hit' : (diff < 0 ? 'short' : 'over');
    if (hit) {
      this._hits++;
      MiniGameManager.addScore(15);
      if (window.GameSounds) GameSounds.minigameCombo();
    } else if (window.GameSounds) {
      GameSounds.minigameMiss();
    }

    // Landing spot is the FIXED target plus how far off-power the release
    // was -- under the window lands short of it, over the window sails past
    // it, exactly matching the target's own tolerance band in scale.
    this._landingX = hit ? this._targetX
      : Math.max(this._landingMinX, Math.min(this._landingMaxX, this._targetX + diff * this._pxPerPowerUnit));

    this._throwIdx++;
    this._phase = 'throwing';
    this._flightStart = performance.now();
    this._leanT = 1;
  },

  // ── Drawing (all layout fields read from init()'s one-time scene calc) ──

  _drawGround: function(ctx) {
    ctx.strokeStyle = '#1f5c3c';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(this._penguinX - 30, this._groundY);
    ctx.lineTo(this._W - 20, this._groundY);
    ctx.stroke();
    ctx.strokeStyle = 'rgba(255,255,255,0.10)';
    ctx.lineWidth = 1;
    for (var x = this._penguinX - 20; x < this._W - 20; x += 26) {
      ctx.beginPath();
      ctx.arc(x, this._groundY + 3, 5, Math.PI, 0);
      ctx.stroke();
    }
  },

  // Still the real aiming feedback -- the marked band is this throw's actual
  // target +-tolerance, the same window _release() checks against, just
  // drawn as a vertical gauge next to the penguin instead of a bar under it.
  _drawGauge: function(ctx) {
    var gh = this._gaugeBottom - this._gaugeTop;
    ctx.fillStyle = 'rgba(255,255,255,0.05)';
    ctx.fillRect(this._gaugeX, this._gaugeTop, this._gaugeW, gh);
    ctx.strokeStyle = '#1f5c3c';
    ctx.lineWidth = 2;
    ctx.strokeRect(this._gaugeX, this._gaugeTop, this._gaugeW, gh);

    var zoneTopY = this._gaugeBottom - gh * ((this._target + this.ZONE_HALF_WIDTH) / 100);
    var zoneH = gh * (this.ZONE_HALF_WIDTH * 2 / 100);
    ctx.fillStyle = 'rgba(74,255,107,0.34)';
    ctx.fillRect(this._gaugeX, zoneTopY, this._gaugeW, zoneH);
    ctx.strokeStyle = '#4aff6b';
    ctx.strokeRect(this._gaugeX, zoneTopY, this._gaugeW, zoneH);

    if (this._phase === 'ready' || this._phase === 'charging') {
      var markerY = this._gaugeBottom - gh * (this._power / 100);
      ctx.beginPath();
      ctx.arc(this._gaugeX + this._gaugeW / 2, markerY, 8, 0, Math.PI * 2);
      ctx.fillStyle = '#FFD700';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  },

  // Lazily-populated per-src image cache, persisted across sessions (not
  // reset in init()) since the player's own sprite/cosmetics don't change
  // mid-game. Returns the loaded Image, or null (and kicks off a load) if
  // it isn't ready yet -- same "check .complete, draw once it's there"
  // pop-in behavior village_map.js's own worn-item rendering already uses.
  _spriteCache: {},
  _getSprite: function(src) {
    var img = this._spriteCache[src];
    if (!img) {
      img = new Image();
      img.src = src;
      this._spriteCache[src] = img;
    }
    return (img.complete && img.naturalWidth > 0) ? img : null;
  },

  // The REAL player's penguin -- body shape/color + worn cosmetics, not a
  // hand-illustrated stand-in. Reuses the exact walk-strip + recolorPenguin()
  // + worn-item-compositing technique village_map.js's drawPenguin() already
  // uses for the live map (PLAYER_SHAPE/PLAYER_COLOR are globals set by
  // home.html; window.getPlayerWornItems() is a small accessor it exposes
  // for exactly this cross-script case). No new sprite assets: "winding
  // up"/"throwing" borrows the strip's other frame as a reach pose (same
  // technique the Era Recap overlay uses for its jump), and the throw-snap
  // motion is still the same lean rotation as before, just applied to the
  // whole sprite instead of one hand-drawn limb.
  _drawPenguin: function(ctx) {
    var lean  = this._phase === 'charging' ? -0.16 * (this._power / 100) : (0.30 * this._leanT);
    var shape = (typeof PLAYER_SHAPE !== 'undefined' && PLAYER_SHAPE) || 'normal';
    var color = (typeof PLAYER_COLOR !== 'undefined' && PLAYER_COLOR) || '#1a1a1a';
    var cfg   = (window.SHAPE_CONFIG && window.SHAPE_CONFIG[shape]) || { frameWidth: 32, frameHeight: 40, stripFile: 'penguin_normal.png' };

    var drawHeight = Math.min(118, this._H * 0.36);
    var drawWidth  = drawHeight * (cfg.frameWidth / cfg.frameHeight);
    var frame  = (this._phase === 'charging' || this._phase === 'throwing') ? 1 : 0;
    var frameX = frame * cfg.frameWidth;

    ctx.save();
    ctx.translate(this._penguinX, this._groundY);
    ctx.rotate(lean);

    var baseSprite = this._getSprite('/static/' + cfg.stripFile);
    if (baseSprite) {
      var recolored = getRecoloredSprite('sporttoss_' + shape, baseSprite, color);
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(recolored, frameX, 0, cfg.frameWidth, cfg.frameHeight,
        -drawWidth / 2, -drawHeight, drawWidth, drawHeight);

      var wornItems  = (window.getPlayerWornItems && window.getPlayerWornItems()) || {};
      var areaFolder = window._AREA_FOLDER || { head: 'hats', body: 'outfits', feet: 'footwear', hand: 'accessories' };
      var order = ['body', 'feet', 'hand', 'head'];
      for (var i = 0; i < order.length; i++) {
        var area   = order[i];
        var itemId = wornItems[area];
        if (!itemId) continue;
        var folder  = areaFolder[area] || area;
        var wornImg = this._getSprite('/static/penguin_wearing/' + shape + '/' + folder + '/' + itemId + '.png');
        if (wornImg) {
          ctx.drawImage(wornImg, frameX, 0, cfg.frameWidth, cfg.frameHeight,
            -drawWidth / 2, -drawHeight, drawWidth, drawHeight);
        }
      }
    } else {
      // Sprite not loaded yet -- flat silhouette placeholder, same fallback
      // shape village_map.js's own _drawPenguinSprite() uses.
      ctx.beginPath();
      ctx.arc(0, -drawHeight / 2, drawWidth / 2, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
    }

    ctx.restore();
  },

  _drawTarget: function(ctx) {
    ctx.save();
    ctx.translate(this._targetX, this._groundY);
    // tolerance ring -- the same +-8 window shown on the gauge, to scale on the ground
    ctx.setLineDash([4, 5]);
    ctx.strokeStyle = 'rgba(74,255,107,0.55)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(0, -14, this.ZONE_HALF_WIDTH * this._pxPerPowerUnit, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.font = '28px serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText('🎯', 0, -14);
    ctx.restore();
  },

  _drawSnowball: function(ctx) {
    if (this._phase !== 'throwing' && this._phase !== 'result') return;
    var t = this._phase === 'result' ? 1 : Math.min(1, (performance.now() - this._flightStart) / this.FLIGHT_MS);
    var startX = this._penguinX + 34, startY = this._groundY - 58;
    var x = startX + (this._landingX - startX) * t;
    var arc = Math.sin(t * Math.PI) * 34; // a small toss arc, not real physics
    var y = (startY + (this._groundY - startY) * t) - arc;

    ctx.beginPath();
    ctx.arc(x, y, 8, 0, Math.PI * 2);
    ctx.fillStyle = '#f4fbf6';
    ctx.fill();
    ctx.strokeStyle = 'rgba(16,36,26,0.25)';
    ctx.lineWidth = 1;
    ctx.stroke();

    if (t >= 1) {
      var markColor = this._outcome === 'hit' ? '#4aff6b' : '#ff6b6b';
      ctx.beginPath();
      ctx.ellipse(this._landingX, this._groundY + 4, 14, 5, 0, 0, Math.PI * 2);
      ctx.fillStyle = markColor + '55';
      ctx.fill();
      ctx.strokeStyle = markColor;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
  },

  _drawHud: function(ctx) {
    ctx.textAlign = 'center';
    ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = '#4aff6b';
    ctx.font = 'bold 15px monospace';
    ctx.fillText('THROW ' + Math.min(this._throwIdx + 1, this.THROW_COUNT) + ' / ' + this.THROW_COUNT, this._W / 2, 30);

    ctx.font = '12px monospace';
    if (this._phase === 'ready') {
      ctx.fillStyle = '#B8B8D0';
      ctx.fillText(this._throwIdx === 0 ? 'PRESS & HOLD TO WIND UP' : 'NEXT THROW — PRESS & HOLD', this._W / 2, 52);
    } else if (this._phase === 'charging') {
      ctx.fillStyle = '#B8B8D0';
      ctx.fillText('RELEASE IN THE MARKED BAND', this._W / 2, 52);
    } else if (this._phase === 'throwing') {
      ctx.fillStyle = '#B8B8D0';
      ctx.fillText('...', this._W / 2, 52);
    } else if (this._phase === 'result') {
      var labels = { hit: '✓ ON TARGET!', short: '✗ FELL SHORT', over: '✗ SAILED OVER' };
      ctx.fillStyle = this._outcome === 'hit' ? '#4aff6b' : '#ff6b6b';
      ctx.fillText(labels[this._outcome], this._W / 2, 52);
    }

    ctx.fillStyle = '#8888A8';
    ctx.fillText('Hits: ' + this._hits + ' / ' + this.THROW_COUNT, this._W / 2, this._H - 14);
    ctx.textAlign = 'left';
  },

  _render: function() {
    if (!this._running) return;
    var self = this;
    var ctx = this._ctx;
    var last = null;

    function loop(ts) {
      if (!self._running) return;
      var dt = last ? Math.min((ts - last) / 1000, 0.05) : 0.016;
      last = ts;
      var now = performance.now();

      if (self._phase === 'charging') {
        var stepPct = (dt * 1000 / self._cycleMs) * 100;
        self._power += self._direction * stepPct;
        if (self._power >= 100) { self._power = 100; self._direction = -1; }
        else if (self._power <= 0) { self._power = 0; self._direction = 1; }
      } else if (self._phase === 'throwing') {
        if (now - self._flightStart >= self.FLIGHT_MS) {
          self._phase = 'result';
          self._resultUntil = now + 1000;
        }
      } else if (self._phase === 'result' && now >= self._resultUntil) {
        if (self._throwIdx >= self.THROW_COUNT) {
          self._finishSession();
          return; // session over -- don't draw or schedule another frame
        }
        self._newTarget();
      }
      if (self._leanT > 0) self._leanT = Math.max(0, self._leanT - dt * 2.7);

      ctx.fillStyle = '#08140c';
      ctx.fillRect(0, 0, self._W, self._H);
      self._drawGround(ctx);
      self._drawTarget(ctx);
      self._drawGauge(ctx);
      self._drawPenguin(ctx);
      self._drawSnowball(ctx);
      self._drawHud(ctx);

      self._animFrame = requestAnimationFrame(loop);
    }
    self._animFrame = requestAnimationFrame(loop);
  },

  // All THROW_COUNT throws are used -- end the session right away instead of
  // waiting out the rest of the safety-cap `duration`. Mirrors
  // MiniGameManager._endGame() but clears its own countdown interval FIRST,
  // so that interval can't also independently reach 0 and call _endGame() a
  // second time (which would double-fire _showResults()/the reward flow).
  _finishSession: function() {
    this._running = false;
    if (MiniGameManager._timer) {
      clearInterval(MiniGameManager._timer);
      MiniGameManager._timer = null;
    }
    MiniGameManager._endGame();
  },

  stop: function() {
    this._running = false;
    if (this._animFrame) { cancelAnimationFrame(this._animFrame); this._animFrame = null; }
    if (this._canvas) {
      this._canvas.onmousedown = null;
      this._canvas.onmouseup = null;
      this._canvas.onmouseleave = null;
      this._canvas.ontouchstart = null;
      this._canvas.ontouchend = null;
    }
  },
};
