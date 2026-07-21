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
