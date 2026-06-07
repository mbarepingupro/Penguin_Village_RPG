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

  // ── RESOURCE COLLECTION ANIMATION ──────────────────────────────────────────

  const _RES_ICONS = {
    gold: '🪙', fish: '🐟', herbs: '🌿', blood_gems: '💎',
    bones: '🦴', spell_fragments: '✨', xp: '⭐',
  };

  function playCollectTink() {
    try {
      if (window.Sounds && Sounds.muted) return;
      const ctx = window.Sounds ? Sounds.getCtx() : new (window.AudioContext || window.webkitAudioContext)();
      if (!ctx) return;
      const osc  = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      const t = ctx.currentTime;
      osc.frequency.setValueAtTime(1200 + Math.random() * 400, t);
      osc.type = 'sine';
      gain.gain.setValueAtTime(0.05, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.1);
      osc.start(t);
      osc.stop(t + 0.1);
    } catch(e) {}
  }

  function animateResourceCollection(resourceType, amount, sourceElement) {
    const icon = _RES_ICONS[resourceType];
    if (!icon) return;

    // For XP, target the XP bar in sidebar
    const isMobile = window.innerWidth < 768;
    let targetEl;
    if (resourceType === 'xp') {
      targetEl = document.getElementById('xp-bar') ||
                 document.querySelector('.xp-bar-wrap') ||
                 document.querySelector('[id^="stat-xp"]');
    } else {
      targetEl = document.getElementById('res-' + resourceType);
    }
    if (!targetEl) return;

    const targetRect = targetEl.getBoundingClientRect();
    const targetX    = targetRect.left + targetRect.width  / 2;
    const targetY    = targetRect.top  + targetRect.height / 2;

    let sourceX, sourceY;
    if (sourceElement) {
      const r = sourceElement.getBoundingClientRect();
      sourceX = r.left + r.width  / 2;
      sourceY = r.top  + r.height / 2;
    } else {
      sourceX = window.innerWidth  / 2;
      sourceY = window.innerHeight / 2;
    }

    const emojiCount   = Math.min(Math.max(1, amount), 20);
    const emojiSize    = isMobile ? '12px' : '18px';
    const totalDur     = 800;
    const burstDur     = 300;

    for (let i = 0; i < emojiCount; i++) {
      setTimeout(() => {
        const emoji = document.createElement('div');
        emoji.className    = 'flying-emoji';
        emoji.textContent  = icon;
        emoji.style.fontSize = emojiSize;

        const spreadX = sourceX + (Math.random() - 0.5) * 100;
        const spreadY = sourceY + (Math.random() - 0.5) * 80;
        emoji.style.left = spreadX + 'px';
        emoji.style.top  = spreadY + 'px';
        document.body.appendChild(emoji);

        const burstX = spreadX + (Math.random() - 0.5) * 60;
        const burstY = spreadY - Math.random() * 40 - 20;
        const startTime = performance.now();

        function step(now) {
          const elapsed = now - startTime;
          const prog    = Math.min(elapsed / totalDur, 1);
          let x, y, scale, opacity;

          if (elapsed < burstDur) {
            const p = elapsed / burstDur;
            x = spreadX + (burstX - spreadX) * p;
            y = spreadY + (burstY - spreadY) * p;
            scale   = 1 + p * 0.3;
            opacity = 1;
          } else {
            const p    = (elapsed - burstDur) / (totalDur - burstDur);
            const ease = p * p;
            x = burstX + (targetX - burstX) * ease;
            y = burstY + (targetY - burstY) * ease;
            scale   = 1.3 - p * 0.8;
            opacity = 1 - p * 0.3;
          }

          emoji.style.left      = x + 'px';
          emoji.style.top       = y + 'px';
          emoji.style.transform = `scale(${scale})`;
          emoji.style.opacity   = opacity;

          if (prog < 1) {
            requestAnimationFrame(step);
          } else {
            emoji.remove();
            playCollectTink();
            // Flash the counter
            const countEl = resourceType === 'xp'
              ? document.getElementById('stat-xp')
              : document.getElementById('count-' + resourceType);
            if (countEl) {
              countEl.classList.add('updated');
              setTimeout(() => countEl.classList.remove('updated'), 300);
            }
          }
        }
        requestAnimationFrame(step);
      }, i * 40);
    }

    // Update the counter after all emojis arrive
    setTimeout(() => {
      if (window.updateResourceBar) updateResourceBar();
    }, totalDur + emojiCount * 40 + 100);
  }

  function animateXPGain(amount, sourceElement) {
    animateResourceCollection('xp', Math.min(amount, 10), sourceElement);
  }

  function animateEarned(earned, sourceElement) {
    if (!earned) return;
    for (const [resource, amount] of Object.entries(earned)) {
      if (!amount || amount <= 0) continue;
      if (resource === 'xp') {
        animateXPGain(amount, sourceElement);
      } else {
        animateResourceCollection(resource, amount, sourceElement);
      }
    }
  }

  return { floatText, pulseElement, confettiBurst, flashElement, smoothFillBar,
           animateResourceCollection, animateXPGain, animateEarned, playCollectTink };
})();
