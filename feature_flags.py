FEATURES = {
    "combat":        True,
    "gear_equip":    True,
    "prestige":      True,
    "achievements":  True,
    "daily_missions": True,
    "login_streak":  True,
    "event_log":     True,
    "hotel_rest":    True,
    "weekly_raid":   True,    # phases 1-5 complete — join window, attack, lootboxes, resolution
    "raid_join_window": False,  # Optional pre-raid join phase. Off by default: the raid opens to
                              # every logged-in player once it goes active, no signup needed —
                              # evaluate_weekly_challenge() creates the post-success raid_state row
                              # as 'awaiting_raid' instead of 'join_window', and /raid/attack
                              # auto-creates a player's raid_participants row on their first swing
                              # instead of 403'ing players who never joined. Data/routes/UI for the
                              # join phase (POST /raid/join, raid_participants join-tracking, the
                              # "JOIN RAID" map icon + modal) stay intact — flipping this back to
                              # True makes evaluate_weekly_challenge() go back to creating
                              # 'join_window' rows and /raid/attack re-enforce the join-first gate,
                              # no rebuilding needed.
    "social_modes":  False,   # Social/Homebody/Focus mode selector + its autonomous-action weighting.
                              # Data/columns/logic stay intact when off — gated in app.py's
                              # run_autonomous_actions() (forces "social" mode for scoring) and
                              # templates/home.html (hides the social-mode-section UI).
                              # /penguin/social-mode and the DB columns are untouched/ungated so
                              # re-enabling is just flipping this flag back to True.
    "minigame_leaderboard": True,  # 5 independent per-game weekly minigame leaderboards + Saturday
                                    # 00:00 reward resolution job. Each of the 5 minigames runs its
                                    # own winner-take-one-N00Tbox weekly contest (whoever's #1 in
                                    # that game when the week ends) — no combined score, no ranks
                                    # 2/3. Raw score persistence (minigame_scores table) and the
                                    # Award Hall's all-time records tab are NOT gated by this — only
                                    # the live weekly rankings + winner reward + chat announcement.
    "weekly_build_leaderboard": True,  # Tracks cumulative ice_blocks earned per player over a
                                    # rotating week (Sun 23:59 server-time reset), gated at the
                                    # /build/roll increment call and the reset job alike. No reward
                                    # distribution yet -- resolve_weekly_build_leaderboard() only
                                    # archives final standings + starts a new week_id; Phase 3c
                                    # reads the archive to grant rewards. Flip to False to stop
                                    # tracking (existing weekly_build_leaderboard/_archive rows are
                                    # untouched either way).
    "gathering_chat_vote": False,   # Chat-vote (via /stream/gathering_vote) picks which building
                                    # hosts the next auto-started gathering, instead of
                                    # auto_start_gathering()'s random.choice(). Shipped dark: the
                                    # vote route, gathering_votes table, and the :50-past-the-hour
                                    # vote-announcement job all run regardless of this flag (so
                                    # votes can accumulate and be inspected before flipping this on)
                                    # -- only the tally-vs-random branch inside auto_start_gathering()
                                    # checks it. /mayor/debug/run_gathering_vote_resolve always
                                    # tallies regardless of this flag, for testing.
    "interactive_moments": True,   # Some requires_other autonomous-action interactions (any
                                    # category) get promoted to an interactive "moment" -- a
                                    # two-option scenario (see moment_scenarios.MOMENT_SCENARIOS,
                                    # e.g. "they should share" vs. "let them fight") the two owners
                                    # steer via a toast, instead of always auto-resolving silently.
                                    # Only option "a" (always the cooperative/friendly resolution)
                                    # calls increment_relationship() for real -- option "b" (the
                                    # confrontational one) and a timed-out window both stay a no-op,
                                    # identical to pre-launch default behavior (relationships never
                                    # moved on their own before this; see _record_auto_interaction()).
                                    # Gated only at the promotion-roll site in
                                    # run_autonomous_actions() -- flip back to False to go dark again
                                    # without touching anything else (the village_moments table,
                                    # /village/moment/resolve, /stream/moment_vote, and the
                                    # timeout-resolver job all keep running regardless, just idle).
                                    # /mayor/debug/force_moment always force-creates one regardless
                                    # of this flag, for testing.
}
