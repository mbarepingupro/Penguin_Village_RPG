# LOOTBOX_DROP_RATES, GOLD_RANGE, and RESOURCE_RANGE moved to raid_settings.py
# (raid_settings table) so the Mayor's Raid Debug panel can tune them live
# without a redeploy — see raid_settings.DEFAULTS for their current defaults.

# Gatherable resources eligible for the lootbox resource roll (excludes gold,
# which has its own roll, and mayor_seals, a premium currency). Not a balance
# knob, just the fixed set of valid resource columns — stays a constant.
RESOURCE_TYPES = ["fish", "herbs", "blood_gems", "bones", "spell_fragments", "ice_blocks"]
