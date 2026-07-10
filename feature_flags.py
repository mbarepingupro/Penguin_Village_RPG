FEATURES = {
    "combat":        True,
    "gear_equip":    True,
    "gear_crafting": True,
    "prestige":      True,
    "achievements":  True,
    "daily_missions": True,
    "login_streak":  True,
    "event_log":     True,
    "hotel_rest":    True,
    "weekly_raid":   True,    # phases 1-5 complete — join window, attack, lootboxes, resolution
    "social_modes":  False,   # Social/Homebody/Focus mode selector + its autonomous-action weighting.
                              # Data/columns/logic stay intact when off — gated in app.py's
                              # run_autonomous_actions() (forces "social" mode for scoring) and
                              # templates/home.html (hides the social-mode-section UI).
                              # /penguin/social-mode and the DB columns are untouched/ungated so
                              # re-enabling is just flipping this flag back to True.
    "minigame_leaderboard": False,  # Weekly combined minigame leaderboard + Saturday 00:00 reward
                                    # resolution job. Raw score persistence (minigame_scores table)
                                    # and the Award Hall's all-time records tab are NOT gated by
                                    # this — only the live weekly rankings + rank rewards + chat
                                    # announcement. Flip to True to go live.
}
