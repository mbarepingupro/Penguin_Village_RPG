# StreamerBot / Twitch-Chat Integration Audit

Audit of every StreamerBot-related and Twitch-chat-related route/function in
the codebase: what each expects as input, what calls it (if anything), and
whether it sits behind a feature flag. No code was changed for this audit.

**Headline finding: there is no StreamerBot integration in this codebase.**
Two routes carry explicit `TODO StreamerBot` comments stating as much
(`app.py:4907-4908`, `app.py:7286-7287`). A handful of other routes look
StreamerBot-shaped (accept a bare `username` in a JSON body, no auth, no
in-repo caller) but nothing calls them from anywhere in this repository —
they'd have to be wired up from an external StreamerBot action/webhook that
doesn't exist here.

**Feature flags: none of these routes are gated by `feature_flags.py`.**
`FEATURES` (feature_flags.py:1-41) only controls `combat`, `gear_equip`,
`prestige`, `achievements`, `daily_missions`, `login_streak`, `event_log`,
`hotel_rest`, `weekly_raid`, `raid_join_window`, `social_modes`,
`minigame_leaderboard`, and `weekly_build_leaderboard`. Every route below is
either always-on, gated only by a runtime Twitch-API check
(`_stream_is_live()`), or hard-coded to return `501 not_implemented`.

---

## 1. Mayor's Seals endpoints

### `POST /seals/award` — app.py:3392-3411 (`seals_award`)
- **Input:** JSON body `{ "username": "<str>" }`.
- **Behavior:** if `_stream_is_live()` is true and the username maps to an
  existing penguin, increments `resources.mayor_seals` by 1 and returns the
  new total. No feature-flag check.
- **Auth:** none — no session check, no shared secret, no CSRF token.
  Anyone who can reach this endpoint can mint seals for any username.
- **Callers in this repo:** **none.** Not referenced in any template or JS.
  This is the clearest candidate for "the endpoint StreamerBot is supposed
  to hit on a channel-point redemption / chat command" — but nothing in
  this codebase actually calls it.

### `GET /seals/shop` — app.py:3414-3416 (`seals_shop`)
- **Input:** none (query-less GET).
- **Behavior:** returns the static `SEAL_SHOP` catalog as JSON.
- **Callers:** `templates/home.html:6817` — `renderSealShop()` fetches this
  alongside `/gear/cosmetics/<user>` to render the seal-shop modal.
- **Auth / flag:** none required (read-only catalog); no feature flag.

### `POST /seals/buy` — app.py:3419-3452 (`seals_buy`)
- **Input:** JSON `{ "item_id": "<str>" }`; username comes from
  `session["username"]`, not the body.
- **Behavior:** validates the item exists in `SEAL_SHOP`, checks the player
  has enough `mayor_seals`, checks they don't already own the cosmetic,
  deducts seals, inserts a `gear` row, logs a `seal_shop` event.
- **Callers:** `templates/home.html:6849` — `buySealItem(itemId)`, wired to
  the BUY button rendered by `renderSealShop()`.
- **Auth / flag:** requires an active session (server-side username); no
  feature flag.

---

## 2. Stream-presence / Twitch-chat-participation endpoints

### `POST /stream/presence` — app.py:3457-3471 (`stream_presence`)
- **Input:** JSON `{ "username": "<str>" }`.
- **Behavior:** if the penguin's `stream_tier` is below 2, bumps it to 2
  ("watching the stream" tier). No feature-flag check, no `_stream_is_live()`
  check either — it trusts the caller that presence is real.
- **Auth:** none.
- **Callers in this repo:** **none.** No template/JS references this route.
  Shape strongly suggests an external StreamerBot "viewer is present"
  trigger that was never actually wired up.

### `POST /stream/chatted` — app.py:3475-3488 (`stream_chatted`)
- **Input:** JSON `{ "username": "<str>" }`.
- **Behavior:** sets `stream_tier=3` and `last_chatted=<now>` for the
  matching penguin ("chatted on stream" tier, the highest tier).
- **Auth:** none.
- **Callers in this repo:** **none.** Same story as `/stream/presence` —
  this is the natural hook for "fired when a viewer sends a Twitch chat
  message," but no StreamerBot/Twitch-chat listener in this repo calls it.

### `GET /islive` — app.py:3352-3372 (`islive`)
- **Input:** none.
- **Behavior:** polls Twitch Helix (`GET
  https://api.twitch.tv/helix/streams?user_login=mbarepingu`) using
  `TWITCH_CLIENT_ID` / `TWITCH_APP_TOKEN`. On a live→offline or
  offline→live transition it bulk-updates all penguins' `stream_tier`
  (resets to 0 on end, bumps 0→1 on start) and tracks state in the
  module-level `_stream_was_live` global.
- **Callers:** `templates/home.html:4107` — client-side poll that feeds
  `is_live` into mission/reward rendering (`renderMissions(...,
  data.is_live)`, `4864`/`4894`).
- **Auth / flag:** public GET, no session required; no feature flag.

### `_stream_is_live()` — app.py:3377-3387 (helper, not a route)
- Same Twitch Helix call as `/islive` but synchronous/inline with a 3s
  timeout, returns a bool instead of mutating DB state.
- **Callers:** `seals_award` (app.py:3398), and the mayor dashboard
  (`app.py:7477`, `7520`) to display live status to the mayor.

---

## 3. Explicit StreamerBot stubs (dead-end by design)

### `POST /events/share/<int:event_id>` — app.py:4905-4912 (`share_event_to_twitch`)
- **Input:** `event_id` path param (int); reads `session["username"]` for
  logging only.
- **Behavior:** contains the literal comment `# TODO StreamerBot: wire this
  up to the real StreamerBot integration — no StreamerBot endpoints exist
  in this codebase yet, so this only logs the request and returns a
  not-implemented response for now.` Logs to stdout and returns
  `501 {"status": "not_implemented", "message": "Twitch sharing is coming
  soon."}` unconditionally.
- **Callers:** `templates/home.html:8539` — `shareEventToTwitch(eventId)`,
  a fire-and-forget `fetch()` off the event-log "share" button; the
  frontend itself also has a `// TODO StreamerBot` comment noting it's a
  stub and just shows a "Coming soon" toast regardless of response.
- **Auth / flag:** no feature flag; behavior is hard-coded to always
  no-op/501 regardless of any flag.

### `POST /card/<username>/share` — app.py:7285-7292 (`share_card_to_twitch`)
- **Input:** `username` path param; reads `session["username"]` (requester)
  for logging only.
- **Behavior:** identical stub pattern — comment explicitly says it
  "Mirrors `share_event_to_twitch`'s stub shape exactly," logs, returns the
  same `501 not_implemented` payload.
- **Callers:** `templates/home.html` — `shareCardToTwitch(username)`,
  fire-and-forget `fetch()` from the profile-card share button, same
  "Coming soon — Twitch sharing" toast pattern.
- **Auth / flag:** none; always-stub, no feature flag.

---

## 4. In-game "global chat" (not Twitch chat — village chat only)

These are the village's own player-to-player chat system. They are
unrelated to Twitch chat / StreamerBot despite living under `/chat/*`; no
Twitch data flows through them. Included here since "chat-activity
endpoints" was in scope and this is the only chat system that exists.

### `GET /chat/messages` — app.py:9855-9868 (`chat_get_messages`)
- **Input:** none.
- **Behavior:** returns the last 100 rows from `chat_messages`, oldest
  first. No age cutoff — retention is handled elsewhere
  (`CHAT_MESSAGE_RETENTION`, pruned in `run_autonomous_actions()`).
- **Callers:** `templates/home.html:4359` — `GlobalChat._poll()`, polled
  every 4s while the player is on the map tab.
- **Auth / flag:** public GET; no feature flag.

### `POST /chat/send` — app.py:9885-9910 (`chat_send_message`)
- **Input:** JSON `{ "username": "<str>", "message": "<str, <=200 chars>" }`.
- **Behavior:** validates non-empty username/message, length limit,
  profanity filter (`_chat_has_profanity`), and a per-username rate limit
  (`_CHAT_RATE_LIMIT_SECONDS`) before inserting via `post_chat_message()`.
- **Callers:** `templates/home.html:4401` — `GlobalChat.send()`, wired to
  the chat panel's send button/input.
- **Auth / flag:** trusts the client-supplied `username` (no session
  cross-check against it); no feature flag.

### `post_chat_message(db, username, message, now=None)` — app.py:9877-9883
- Not a route — shared insert helper. Used by `/chat/send` and by trusted
  system callers (e.g., raid-resolution announcements) that skip the
  rate-limit/profanity checks noted in its docstring.

---

## 5. Player-heartbeat presence (separate from stream presence)

### `POST /presence/ping` — app.py:7411-7421 (`presence_ping`)
- **Input:** JSON `{ "username": "<str>" }`.
- **Behavior:** updates `penguins.last_active` to now. Comment at
  app.py:7405-7409 documents this as a generic "is player online" signal
  (3-minute window) reusable by any feature, unrelated to Twitch/stream
  presence tiers.
- **Callers:** `templates/home.html:4179` — client-side heartbeat, fires
  once on load and then every 90s via `setInterval`.
- **Auth / flag:** none; no feature flag. Distinct from `/stream/presence`
  above — this one is in-app "is the player's browser tab open," not
  "is the viewer watching/chatting on Twitch."

---

## 6. Twitch OAuth login (unrelated to StreamerBot, included for completeness)

### `GET /login` — app.py:2906-2912
- Redirects to `https://id.twitch.tv/oauth2/authorize` using
  `TWITCH_CLIENT_ID` / `TWITCH_REDIRECT_URI`, scope `user:read:email`.

### `GET /auth/callback` — app.py:2917-~2945 (`callback`)
- **Input:** `code` query param from Twitch's redirect.
- **Behavior:** exchanges the code for an access token
  (`https://id.twitch.tv/oauth2/token`), fetches the Twitch user
  (`https://api.twitch.tv/helix/users`), sets `session["username"]` to the
  Twitch login, creates a `penguins` row on first login, logs a `village`
  join event. Falls back to `redirect("/?error=twitch_auth_failed")` on any
  exception.
- **Callers:** browser redirect target registered with Twitch as the OAuth
  redirect URI (`TWITCH_REDIRECT_URI`); not called from app code.
- **Auth / flag:** this *is* the auth mechanism; no feature flag.

---

## Summary table

| Route | Method | Feature flag? | In-repo caller? |
|---|---|---|---|
| `/seals/award` | POST | No | **None found** |
| `/seals/shop` | GET | No | `home.html:6817` |
| `/seals/buy` | POST | No | `home.html:6849` |
| `/stream/presence` | POST | No | **None found** |
| `/stream/chatted` | POST | No | **None found** |
| `/islive` | GET | No | `home.html:4107` |
| `/events/share/<id>` | POST | No (hard-coded 501 stub) | `home.html:8539` |
| `/card/<username>/share` | POST | No (hard-coded 501 stub) | `home.html` (`shareCardToTwitch`) |
| `/chat/messages` | GET | No | `home.html:4359` |
| `/chat/send` | POST | No | `home.html:4401` |
| `/presence/ping` | POST | No | `home.html:4179` |
| `/login` | GET | No | Twitch OAuth entry point |
| `/auth/callback` | GET | No | Twitch OAuth redirect target |

## Notable gaps / risks (observations only, no changes made)

- **No StreamerBot integration exists.** Both explicit stub routes say so
  in their own comments, and the three routes shaped for it
  (`/seals/award`, `/stream/presence`, `/stream/chatted`) have zero callers
  anywhere in this repository.
- **No authentication on the StreamerBot-shaped routes.** `/seals/award`,
  `/stream/presence`, and `/stream/chatted` accept a bare `username` in the
  JSON body with no session check, shared secret, or signature
  verification — unlike `/admin/*` routes, which check `ADMIN_SECRET`
  (app.py:5691-5695) via `X-Admin-Secret`. If/when a real StreamerBot
  webhook is wired to these, they'll need equivalent protection before
  going live, since currently anyone who can reach the server could POST a
  victim's username to mint seals or bump their stream tier.
