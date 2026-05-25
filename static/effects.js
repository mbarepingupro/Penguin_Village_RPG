const Effects = (function () {

  function floatText(anchorEl, text, color) {
    color = color || '#4aff6b';
    if (!anchorEl) return;
    const rect = anchorEl.getBoundingClientRect();
    const el = document.createElement('div');
    el.textContent = text;
    Object.assign(el.style, {
      position:   'fixed',
      left:       (rect.left + rect.width / 2) + 'px',
      top:        rect.top + 'px',
      transform:  'translateX(-50%)',
      color:      color,
      fontFamily: "'Press Start 2P', monospace",
      fontSize:   '9px',
      pointerEvents: 'none',
      zIndex:     '99999',
      opacity:    '1',
      whiteSpace: 'nowrap',
      textShadow: '0 0 6px ' + color,
    });
    document.body.appendChild(el);
    const startTop = rect.top;
    let startTs = null;
    function step(ts) {
      if (!startTs) startTs = ts;
      const t = Math.min((ts - startTs) / 800, 1);
      el.style.top     = (startTop - t * 45) + 'px';
      el.style.opacity = t < 0.6 ? '1' : String(1 - (t - 0.6) / 0.4);
      if (t < 1) requestAnimationFrame(step);
      else el.remove();
    }
    requestAnimationFrame(step);
  }

  function pulseElement(el, color, times) {
    times = times || 3;
    if (!el) return;
    const origShadow = el.style.boxShadow  || '';
    const origBorder = el.style.borderColor || '';
    let count = 0;
    function tick() {
      if (count >= times * 2) {
        el.style.boxShadow  = origShadow;
        el.style.borderColor = origBorder;
        return;
      }
      const on = count % 2 === 0;
      el.style.boxShadow  = on ? ('0 0 16px 4px ' + color) : origShadow;
      el.style.borderColor = on ? color : origBorder;
      count++;
      setTimeout(tick, 280);
    }
    tick();
  }

  function confettiBurst(anchorEl, count) {
    count = count || 12;
    if (!anchorEl) return;
    const rect    = anchorEl.getBoundingClientRect();
    const cx      = rect.left + rect.width  / 2;
    const cy      = rect.top  + rect.height / 2;
    const palette = ['#FF8C00', '#A86EFF', '#4aff6b', '#FF7FE5', '#4a9eff', '#ffffff'];
    for (let i = 0; i < count; i++) {
      (function (i) {
        const el    = document.createElement('div');
        el.textContent = '★';
        const angle = (i / count) * Math.PI * 2;
        const spd   = 35 + Math.random() * 40;
        const vx    = Math.cos(angle) * spd;
        const vy    = Math.sin(angle) * spd - 25;
        Object.assign(el.style, {
          position: 'fixed',
          left:  cx + 'px',
          top:   cy + 'px',
          color: palette[i % palette.length],
          fontSize: '12px',
          pointerEvents: 'none',
          zIndex: '99999',
          opacity: '1',
        });
        document.body.appendChild(el);
        let startTs = null;
        function step(ts) {
          if (!startTs) startTs = ts;
          const t = Math.min((ts - startTs) / 700, 1);
          el.style.left    = (cx + vx * t) + 'px';
          el.style.top     = (cy + vy * t + 90 * t * t) + 'px';
          el.style.opacity = t < 0.55 ? '1' : String(1 - (t - 0.55) / 0.45);
          if (t < 1) requestAnimationFrame(step);
          else el.remove();
        }
        requestAnimationFrame(step);
      })(i);
    }
  }

  function flashElement(el, color, times) {
    times = times || 3;
    if (!el) return;
    const orig = el.style.borderColor || '';
    let count = 0;
    function tick() {
      if (count >= times * 2) { el.style.borderColor = orig; return; }
      el.style.borderColor = count % 2 === 0 ? color : orig;
      count++;
      setTimeout(tick, 200);
    }
    tick();
  }

  function smoothFillBar(barEl, targetPct, duration) {
    duration = duration || 500;
    if (!barEl) return;
    const startW = parseFloat(barEl.style.width) || 0;
    const diff   = targetPct - startW;
    let startTs  = null;
    function step(ts) {
      if (!startTs) startTs = ts;
      const t    = Math.min((ts - startTs) / duration, 1);
      const ease = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
      barEl.style.width = (startW + diff * ease) + '%';
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  return { floatText, pulseElement, confettiBurst, flashElement, smoothFillBar };
})();
