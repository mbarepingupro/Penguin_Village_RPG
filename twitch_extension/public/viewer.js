// Panel view (Twitch Extension, type: Panel). Loaded inside the Twitch
// Developer Rig / the real Twitch player iframe.

// In-memory only, never localStorage/sessionStorage -- the JWT is short-lived
// and re-issued by onAuthorized on its own refresh cadence, so persisting it
// would just be a stale-token liability with no benefit.
let extensionJWT = null;

window.Twitch.ext.onAuthorized((auth) => {
  extensionJWT = auth.token;
  console.log("[PenguinVillage] onAuthorized fired, JWT captured:", auth);
  refreshPanel();
});

// Attaches the captured JWT as `Authorization: Bearer <token>` to a request
// against the backend. Not called anywhere yet -- endpoint wiring is a later
// phase; this just establishes the pattern every /extension/* call will use.
function authedFetch(path, options = {}) {
  const headers = {
    ...(options.headers || {}),
    Authorization: `Bearer ${extensionJWT}`,
  };
  return fetch(path, { ...options, headers });
}

// ── PENGUIN RENDER ───────────────────────────────────────────────────────
// Reproduces the site's own sprite/recolor conventions client-side:
// SHAPE_CONFIG from static/village_map.js and the recolor algorithm from
// static/recolor.js, ported verbatim rather than imported via <script src>
// so this Rig project stays a standalone scaffold with no dependency on the
// Flask app's own asset pipeline. First frame only (static pose) -- no
// animation loop for the panel.

// CORS: app.py's after_request hook now covers /static/* (in addition to
// /extension/* and the card image route below) so recolorPenguin()'s
// ctx.getImageData() call on the drawn sprite no longer taints the canvas.
// Verified directly (Flask test_client(), not assumed): GET /static/<real
// file>, GET /static/<missing file>, and the OPTIONS preflight for both all
// come back with Access-Control-Allow-Origin set; no sibling route picked it
// up as a side effect. img.crossOrigin="anonymous" below is still required
// for getImageData() to work even with the header present -- kept as-is.
const BACKEND_ORIGIN = "https://penguinvillagerpg-production.up.railway.app";

const SHAPE_CONFIG = {
  normal: { frameWidth: 32, frameHeight: 40, stripFile: "penguin_normal.png" },
  tall:   { frameWidth: 32, frameHeight: 50, stripFile: "penguin_tall.png" },
};

// Verbatim port of recolorPenguin() from static/recolor.js: skips
// transparent pixels, skips belly/white (brightness > 180), skips the
// orange beak/feet range, and scales everything else -- including
// brightness = 0 (the flat black body, deliberately NOT skipped) -- by
// max(1.0, brightness / 26) against the target color.
function recolorPenguin(sourceImage, targetColor) {
  if (!targetColor || !targetColor.startsWith('#') || targetColor.length < 7) return sourceImage;
  if (targetColor === '#1a1a1a') return sourceImage;

  const offscreen = document.createElement('canvas');
  offscreen.width  = sourceImage.naturalWidth  || sourceImage.width  || 64;
  offscreen.height = sourceImage.naturalHeight || sourceImage.height || 40;
  const ctx = offscreen.getContext('2d');
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(sourceImage, 0, 0);

  // Throws SecurityError here if sourceImage tainted the canvas -- see the
  // CORS flag above. Left uncaught; renderPenguinFrame() below is the catch
  // boundary so the failure (and its cause) surfaces clearly in the console.
  const imageData = ctx.getImageData(0, 0, offscreen.width, offscreen.height);
  const pixels     = imageData.data;

  const tr = parseInt(targetColor.slice(1, 3), 16);
  const tg = parseInt(targetColor.slice(3, 5), 16);
  const tb = parseInt(targetColor.slice(5, 7), 16);
  if (isNaN(tr) || isNaN(tg) || isNaN(tb)) return sourceImage;

  for (let i = 0; i < pixels.length; i += 4) {
    const r = pixels[i], g = pixels[i + 1], b = pixels[i + 2], a = pixels[i + 3];
    if (a === 0) continue;
    const brightness = (r + g + b) / 3;
    if (brightness > 180) continue;                              // belly / white areas
    if (r > 150 && g > 80 && g < 180 && b < 80) continue;         // beak / feet (orange)
    const scale = Math.max(1.0, brightness / 26);
    pixels[i]     = Math.min(255, Math.floor(tr * scale));
    pixels[i + 1] = Math.min(255, Math.floor(tg * scale));
    pixels[i + 2] = Math.min(255, Math.floor(tb * scale));
  }
  ctx.putImageData(imageData, 0, 0);
  return offscreen;
}

// Draws frame 0 (the standing pose) of the shape's walk-strip sprite,
// recolored, onto #penguin-canvas. Static only, matching the panel's needs
// -- the site's own animation loop (animFrame cycling) is not ported here.
function renderPenguinFrame(shape, color) {
  const cfg    = SHAPE_CONFIG[shape] || SHAPE_CONFIG.normal;
  const canvas = document.getElementById('penguin-canvas');
  const ctx    = canvas.getContext('2d');

  const drawWidth  = 96;
  const drawHeight = (cfg.frameHeight / cfg.frameWidth) * drawWidth;
  canvas.width  = drawWidth;
  canvas.height = drawHeight;
  ctx.imageSmoothingEnabled = false;

  const img = new Image();
  // Required for getImageData() in recolorPenguin() to succeed on a
  // cross-origin sprite -- see the CORS note above. /static/* now sends
  // Access-Control-Allow-Origin, so this should load and recolor cleanly;
  // kept as try/catch + onerror below in case a future deploy regresses it.
  img.crossOrigin = 'anonymous';
  img.onload = () => {
    let recolored;
    try {
      recolored = recolorPenguin(img, color);
    } catch (err) {
      console.error('[PenguinVillage] Recolor failed (CORS should be fixed -- check /static/* response headers):', err);
      recolored = img;
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(
      recolored,
      0, 0, cfg.frameWidth, cfg.frameHeight,
      0, 0, drawWidth, drawHeight
    );
  };
  img.onerror = () => {
    console.error('[PenguinVillage] Sprite failed to load:', img.src);
  };
  img.src = `${BACKEND_ORIGIN}/static/${cfg.stripFile}`;
}

// ── SUMMARY / ACTIONS ────────────────────────────────────────────────────
// GET /extension/summary and POST /extension/build_roll,
// POST /extension/raid_attack were verified directly (a real Flask test
// client run against the actual route code, not read-and-assume) before
// wiring this. Two things that verification caught, both load-bearing here:
//
// 1. /extension/build_roll and /extension/raid_attack do NOT mirror their
//    website counterparts' response shapes -- they return a materially
//    smaller field set (e.g. no energy_remaining on either, no
//    free_rolls_remaining, no player_cp/roll/was_crit on raid_attack). Only
//    fields actually present in the extension responses are read below.
// 2. Because neither action response includes updated energy/eligibility,
//    refreshPanel() (a fresh GET /extension/summary) is what keeps energy,
//    ice_blocks, build_available and raid_active correct after an action --
//    not the action response itself.

const linkPromptEl  = document.getElementById('link-prompt');
const linkOpaqueEl  = document.getElementById('link-opaque-id');
const linkUrlEl     = document.getElementById('link-url');
const playerPanelEl = document.getElementById('player-panel');
const statLevelEl   = document.getElementById('stat-level');
const statCpEl      = document.getElementById('stat-cp');
const statEnergyEl  = document.getElementById('stat-energy');
const statIceEl     = document.getElementById('stat-ice-blocks');
const buildBtn      = document.getElementById('build-btn');
const attackBtn     = document.getElementById('attack-btn');
const copyCardBtn   = document.getElementById('copy-card-btn');
const actionResultEl = document.getElementById('action-result');
const tabPlayerBtn  = document.getElementById('tab-player');
const tabEventsBtn  = document.getElementById('tab-events');
const eventsPanelEl = document.getElementById('events-panel');
const eventsListEl  = document.getElementById('events-list');

let currentUsername = null;
let isLinked         = false;
let activeTab         = 'player';

// Which of link-prompt / player-panel / events-panel is shown depends on
// both the active tab and the last-known linked state -- refreshPanel() and
// the tab buttons both funnel through this instead of setting .hidden
// directly, so the two states can't fight each other.
function renderTabVisibility() {
  tabPlayerBtn.classList.toggle('active', activeTab === 'player');
  tabEventsBtn.classList.toggle('active', activeTab === 'events');
  linkPromptEl.hidden  = !(activeTab === 'player' && !isLinked);
  playerPanelEl.hidden = !(activeTab === 'player' && isLinked);
  eventsPanelEl.hidden = activeTab !== 'events';
}

tabPlayerBtn.addEventListener('click', () => {
  activeTab = 'player';
  renderTabVisibility();
});
tabEventsBtn.addEventListener('click', () => {
  activeTab = 'events';
  renderTabVisibility();
  loadEvents();
});

async function refreshPanel() {
  let resp, data;
  try {
    resp = await authedFetch(`${BACKEND_ORIGIN}/extension/summary`);
    data = await resp.json();
  } catch (err) {
    console.error('[PenguinVillage] Failed to load /extension/summary:', err);
    return;
  }
  if (!resp.ok) {
    console.error('[PenguinVillage] /extension/summary error:', resp.status, data);
    return;
  }

  isLinked = data.linked;

  if (!data.linked) {
    linkOpaqueEl.textContent = data.opaque_user_id || '';
    linkUrlEl.href = data.link_url;
    linkUrlEl.textContent = data.link_url;
    renderTabVisibility();
    return;
  }

  currentUsername = data.username;

  statLevelEl.textContent = `Lv ${data.level}`;
  statCpEl.textContent = `CP ${data.cp}`;
  statEnergyEl.textContent = `⚡ ${data.energy}/${data.energy_max}`;
  statIceEl.textContent = `🧊 ${data.ice_blocks}`;

  // build_available is energy > 0 server-side, not energy >= the actual 5-
  // energy roll cost (flagged in /extension/summary's own docstring) -- so
  // this can read enabled at 1-4 energy even though the roll itself will
  // fail. Left as-is per the summary's documented field, not silently
  // tightened client-side.
  buildBtn.disabled = !data.build_available;
  attackBtn.disabled = !data.raid_active;

  renderPenguinFrame(data.shape, data.color);
  renderTabVisibility();
}

async function handleBuild() {
  buildBtn.disabled = true;
  actionResultEl.textContent = 'Building...';
  try {
    const resp = await authedFetch(`${BACKEND_ORIGIN}/extension/build_roll`, { method: 'POST' });
    const data = await resp.json();
    if (!resp.ok || data.status !== 'success') {
      actionResultEl.textContent = data.message || 'Build failed.';
    } else {
      actionResultEl.textContent = data.crit
        ? `Crit! Rolled ${data.roll}, +${data.ice_blocks_earned} ice blocks, +${data.xp_earned} XP.`
        : `Rolled ${data.roll}, +${data.ice_blocks_earned} ice blocks, +${data.xp_earned} XP.`;
    }
  } catch (err) {
    console.error('[PenguinVillage] /extension/build_roll failed:', err);
    actionResultEl.textContent = 'Could not reach the server.';
  }
  refreshPanel();
}

async function handleAttack() {
  attackBtn.disabled = true;
  actionResultEl.textContent = 'Attacking...';
  try {
    const resp = await authedFetch(`${BACKEND_ORIGIN}/extension/raid_attack`, { method: 'POST' });
    const data = await resp.json();
    if (!resp.ok || data.status !== 'success') {
      actionResultEl.textContent = data.message || 'Attack failed.';
    } else if (data.resolution) {
      actionResultEl.textContent = `Dealt ${data.damage_dealt} damage -- boss defeated!`;
    } else {
      actionResultEl.textContent = `Dealt ${data.damage_dealt} damage. Boss HP: ${data.boss_current_hp}/${data.boss_max_hp}.`;
    }
  } catch (err) {
    console.error('[PenguinVillage] /extension/raid_attack failed:', err);
    actionResultEl.textContent = 'Could not reach the server.';
  }
  refreshPanel();
}

// /card/<username>/image is public (no authedFetch/JWT needed). app.py's
// CORS hook now covers this route by endpoint name (card_image) in addition
// to /extension/* and /static/* -- verified directly (Flask test_client()):
// both the 200 (real username) and 404 (missing username) responses carry
// Access-Control-Allow-Origin, and sibling /card/* routes (the HTML page,
// /card/<username>/share, /card/backgrounds/<username>) do not pick it up.
async function handleCopyCard() {
  if (!currentUsername) return;
  if (!navigator.clipboard || !window.ClipboardItem) {
    copyCardBtn.textContent = 'Not supported';
    setTimeout(() => { copyCardBtn.textContent = 'Copy Card'; }, 2000);
    return;
  }

  copyCardBtn.disabled = true;
  try {
    // Passing the blob promise straight into ClipboardItem (rather than
    // awaiting fetch()/blob() first) keeps this call inside the click's user-
    // activation window, which navigator.clipboard.write() requires and an
    // awaited gap can lose in some browsers.
    const blobPromise = fetch(`${BACKEND_ORIGIN}/card/${currentUsername}/image`).then((resp) => {
      if (!resp.ok) throw new Error(`Card image fetch failed: ${resp.status}`);
      return resp.blob();
    });
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blobPromise })]);
    copyCardBtn.textContent = 'Copied!';
  } catch (err) {
    console.error('[PenguinVillage] Copy Card failed:', err);
    copyCardBtn.textContent = 'Copy failed';
  }
  setTimeout(() => {
    copyCardBtn.textContent = 'Copy Card';
    copyCardBtn.disabled = false;
  }, 2000);
}

buildBtn.addEventListener('click', handleBuild);
attackBtn.addEventListener('click', handleAttack);
copyCardBtn.addEventListener('click', handleCopyCard);

// ── EVENTS TAB ───────────────────────────────────────────────────────────
// GET /extension/events/recent's response shape was checked against the
// actual route code (it's the shared _recent_events() helper also used by
// the site's GET /events/recent) rather than assumed: each event has
// event_type, message, created_at, time_ago, id, username, participants --
// no precomputed color/bucket field. The site's own color coding for this
// exact endpoint's data lives in templates/home.html's _TICKER_COLORS map
// (keyed by event_type, used by loadNewsTicker() -- the site's own consumer
// of /events/recent), so that data IS present in the response (event_type
// is the key _TICKER_COLORS needs) and is ported verbatim below rather than
// guessed. Its own fallback ('#B8B8D0' for any event_type not in the map)
// is kept as-is, same as the site.
const _TICKER_COLORS = {
  autonomous: '#B8B8D0', village: '#4aff6b', level_up: '#FF8C00',
  achievement: '#FF8C00', combat: '#ff6b6b', job: '#4aff6b',
  shop: '#FF7FE5', seal_shop: '#FF7FE5', igloo: '#A86EFF',
  social: '#4a9eff', milestone: '#FF8C00', title: '#FF8C00',
  gear_purchase: '#A86EFF', reshape: '#4a9eff', character_created: '#4aff6b',
  donation: '#FF8C00', building_levelup: '#4aff6b', group: '#4aff6b',
};

async function loadEvents() {
  eventsListEl.innerHTML = '<li class="events-empty">Loading...</li>';
  let resp, data;
  try {
    resp = await authedFetch(`${BACKEND_ORIGIN}/extension/events/recent`);
    data = await resp.json();
  } catch (err) {
    console.error('[PenguinVillage] /extension/events/recent failed:', err);
    eventsListEl.innerHTML = '<li class="events-empty">Could not load events.</li>';
    return;
  }
  if (!resp.ok) {
    console.error('[PenguinVillage] /extension/events/recent error:', resp.status, data);
    eventsListEl.innerHTML = '<li class="events-empty">Could not load events.</li>';
    return;
  }
  renderEvents(data.events || []);
}

function renderEvents(events) {
  eventsListEl.innerHTML = '';
  if (!events.length) {
    eventsListEl.innerHTML = '<li class="events-empty">No events yet.</li>';
    return;
  }
  for (const ev of events) {
    const li = document.createElement('li');
    li.className = 'event-row';

    const msgSpan = document.createElement('span');
    msgSpan.className = 'event-message';
    msgSpan.style.color = _TICKER_COLORS[ev.event_type] || '#B8B8D0';
    // ev.message carries inline markup (<span class="pname-hl">...</span> --
    // see highlight_name() in personality_config.py) that the site's own
    // news ticker also renders via innerHTML, not textContent -- .textContent
    // here was escaping it, showing the literal "<span..." text instead of
    // rendering it. innerHTML matches the site's existing convention for
    // this exact field. See the [SECURITY] note in this session's report:
    // event_log.message is not HTML-escaped end-to-end today (traced to
    // Discord OAuth's unsanitized global_name flowing into it) -- this
    // assumes that gets closed, it doesn't close it.
    msgSpan.innerHTML = ev.message;

    const timeSpan = document.createElement('span');
    timeSpan.className = 'event-time';
    timeSpan.textContent = ev.time_ago;

    const shareBtn = document.createElement('button');
    shareBtn.type = 'button';
    shareBtn.className = 'event-share-btn';
    shareBtn.textContent = 'Share';
    shareBtn.addEventListener('click', () => handleShareEvent(ev.id, shareBtn));

    li.appendChild(msgSpan);
    li.appendChild(timeSpan);
    li.appendChild(shareBtn);
    eventsListEl.appendChild(li);
  }
}

async function handleShareEvent(eventId, btnEl) {
  btnEl.disabled = true;
  btnEl.textContent = '...';
  try {
    const resp = await authedFetch(`${BACKEND_ORIGIN}/extension/events/share/${eventId}`, { method: 'POST' });
    const data = await resp.json();
    btnEl.textContent = (resp.ok && data.status === 'shared') ? 'Shared!' : (data.message || 'Failed');
  } catch (err) {
    console.error('[PenguinVillage] /extension/events/share failed:', err);
    btnEl.textContent = 'Failed';
  }
  setTimeout(() => {
    btnEl.textContent = 'Share';
    btnEl.disabled = false;
  }, 2000);
}
