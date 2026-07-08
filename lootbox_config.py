# ── LOOTBOX DROP RATES ────────────────────────────────────────────────────────
# Percent chance per rarity — placeholder curve, tune during balance-pass.
# Must sum to 100.
LOOTBOX_DROP_RATES = {
    "legendary": 5,
    "rare":      10,
    "epic":      7,
    "uncommon":  28,
    "common":    50,
}

GOLD_RANGE     = (50, 100)
RESOURCE_RANGE = (1, 50)

# Gatherable resources eligible for the lootbox resource roll (excludes gold,
# which has its own roll, and mayor_seals, a premium currency).
RESOURCE_TYPES = ["fish", "herbs", "blood_gems", "bones", "spell_fragments", "ice_blocks"]
