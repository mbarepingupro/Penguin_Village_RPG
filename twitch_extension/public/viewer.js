// Panel view (Twitch Extension, type: Panel). Loaded inside the Twitch
// Developer Rig / the real Twitch player iframe.

// In-memory only, never localStorage/sessionStorage -- the JWT is short-lived
// and re-issued by onAuthorized on its own refresh cadence, so persisting it
// would just be a stale-token liability with no benefit.
let extensionJWT = null;

window.Twitch.ext.onAuthorized((auth) => {
  extensionJWT = auth.token;
  console.log("[PenguinVillage] onAuthorized fired, JWT captured:", auth);
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

// CORS FLAG (confirmed against app.py, not guessed): the Flask app's
// after_request CORS hook only adds Access-Control-Allow-Origin when
// request.path starts with "/extension/", deliberately scoped that way so
// nothing outside /extension/ changes behavior -- /static/* (where these
// sprites live) sends no CORS headers at all today. recolorPenguin() below
// calls ctx.getImageData() on a canvas the sprite was drawn into, which
// throws SecurityError for a cross-origin image the browser doesn't have
// CORS permission for -- and setting img.crossOrigin="anonymous" (required
// for getImageData to ever work) makes the image request itself get
// rejected by the browser instead, since the server never answers with an
// Allow-Origin header. Net effect: recoloring will not work against the
// real backend until either (a) /static/* gets the same CORS treatment
// /extension/* has, or (b) sprites are served through an /extension/-
// prefixed route instead. Not fixing this client-side -- flagging it here
// and via the console.error in the onerror handler below.
const BACKEND_ORIGIN = "http://localhost:5000"; // swap for the real deployed backend origin

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
  // Required for getImageData() in recolorPenguin() to ever succeed on a
  // cross-origin sprite -- see the CORS flag above. Until /static/* sends
  // Access-Control-Allow-Origin, this makes the image request itself fail
  // (onerror below) rather than loading tainted.
  img.crossOrigin = 'anonymous';
  img.onload = () => {
    let recolored;
    try {
      recolored = recolorPenguin(img, color);
    } catch (err) {
      console.error('[PenguinVillage] Recolor failed -- likely the /static/* CORS gap flagged above:', err);
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
    console.error(
      '[PenguinVillage] Sprite failed to load (expected until /static/* sends CORS headers -- see flag above):',
      img.src
    );
  };
  img.src = `${BACKEND_ORIGIN}/static/${cfg.stripFile}`;
}

// Placeholder call -- shape/color aren't wired to /extension/summary yet
// (endpoint wiring is a later phase), so this demos the render pipeline
// with a non-default color chosen specifically to exercise the recolor
// path (#1a1a1a would short-circuit it and hide the CORS issue above).
renderPenguinFrame('normal', '#3a86ff');
