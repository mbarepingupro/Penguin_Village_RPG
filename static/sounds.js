const Sounds = (function () {
  let _ctx = null;
  let _muted = false;

  function _getCtx() {
    if (!_ctx) _ctx = new (window.AudioContext || window.webkitAudioContext)();
    return _ctx;
  }

  function _tone(ctx, freq, type, start, dur, peak) {
    const osc  = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = type;
    osc.frequency.setValueAtTime(freq, start);
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(peak, start + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.001, start + dur);
    osc.start(start);
    osc.stop(start + dur);
  }

  function _seq(notes, type) {
    if (_muted) return;
    try {
      const ctx = _getCtx();
      let t = ctx.currentTime;
      for (const [freq, dur] of notes) {
        _tone(ctx, freq, type, t, dur, 0.15);
        t += dur;
      }
    } catch (e) {}
  }

  const C4 = 261.63, D4 = 293.66, E4 = 329.63, F4 = 349.23,
        G4 = 392.00, A4 = 440.00, B4 = 493.88, C5 = 523.25, E5 = 659.25;

  return {
    get muted() { return _muted; },

    toggleMute() {
      _muted = !_muted;
      const btn = document.getElementById('mute-btn');
      if (btn) btn.textContent = _muted ? '🔇' : '🔊';
      return _muted;
    },

    collect() {
      _seq([[C4, 0.10], [E4, 0.10], [G4, 0.12]], 'square');
    },

    streak() {
      _seq([[C4, 0.08], [E4, 0.08], [G4, 0.08], [C5, 0.08], [E5, 0.20]], 'triangle');
    },

    donate() {
      if (_muted) return;
      try {
        const ctx = _getCtx();
        _tone(ctx, 150, 'sine', ctx.currentTime, 0.15, 0.20);
      } catch (e) {}
    },

    levelUp() {
      _seq([
        [C4, 0.075], [D4, 0.075], [E4, 0.075], [F4, 0.075],
        [G4, 0.075], [A4, 0.075], [B4, 0.075], [C5, 0.150],
      ], 'square');
    },

    buildingLevelUp() {
      this.levelUp();
    },

    rest() {
      _seq([[E4, 0.20], [C4, 0.20]], 'sine');
    },

    equip() {
      if (_muted) return;
      try {
        const ctx = _getCtx();
        _tone(ctx, 800, 'square', ctx.currentTime, 0.10, 0.10);
      } catch (e) {}
    },
  };
})();
