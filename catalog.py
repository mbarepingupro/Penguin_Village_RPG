"""DB-backed replacements for what used to be app.py's BARRACKS_SHOP,
BOUTIQUE_ITEMS, GEAR_TEMPLATES, and SET_BONUSES dict literals -- same idea as
raid_settings.py: a live-editable store instead of a hardcoded constant,
backed by the barracks_shop/boutique_items/gear_templates/set_bonuses tables
(see database.py's init_db() for the schema).

Each loader reconstructs the EXACT shape the old literal had -- same
dict-of-lists/dict-of-dicts nesting, same keys, even the same sparse
"event_exclusive" key (only present when true, never present-and-False) --
so every existing call site kept working by just swapping the bare name for
a loader call; no downstream logic had to change.

migrate_catalog_tables.py performed the original one-time seed of an
already-populated app.py's dict literals into these tables, back when both
still existed side by side -- but now that those literals are gone (this is
the DB, not app.py, that's the live source of truth), a genuinely fresh
database (a new deploy, or any test's from-scratch DB) has no other way to
get seeded. So the DEFAULT_* constants below (exact copies of the original
literals' values) get seeded into their tables once, by database.py's
init_db(), the first time it finds a table empty -- NOT lazily inside the
load_*() functions below (that was tried and reverted: a load_*() can run
mid-transaction on a caller's borrowed `db`, and a second, unrelated
connection calling it concurrently could try to write the seed rows into a
table the first connection already holds an uncommitted lock on -- a real
"database is locked" error). load_*() here is purely read-only. After the
one seed, the DB is fully in control: editing a row directly (or,
eventually, via a CRUD admin tool) changes what every loader returns from
then on, same as raid_settings.
"""
import json
import sqlite3
import os

DATABASE = os.environ.get('DATABASE_PATH', 'village.db')

# barracks_shop isn't part of the gear_templates 5-tier ladder (no set_name,
# no family spanning multiple rarities), but each of its material families
# is pinned to exactly one rarity, so it maps 1:1 onto one gear tier and
# gets that tier's required_level threshold from the SAME table the 26 sets
# use: iron/driftwood (common) -> Tier 1 @1, steel/coral (uncommon) ->
# Tier 2 @6, crystal/aurora (rare) -> Tier 3 @11, obsidian (epic) ->
# Tier 4 @18, mythril (legendary) -> Tier 5 @24. Spread 2/2/2/1/1 across the
# 5 tiers -- roughly even, and matches the power progression the material
# names already implied. Existing databases need migrate_barracks_tier_
# levels.py to pick these up (this dict only seeds a genuinely fresh DB).
_BARRACKS_REQUIRED_LEVEL = {"common": 1, "uncommon": 6, "rare": 11, "epic": 18, "legendary": 24}

# -- Design notes preserved from the old BARRACKS_SHOP literal --
#
# Each rarity carries one purely-cosmetic ALTERNATIVE per slot alongside the
# original (iron/steel/crystal): identical combat_power to its slot+rarity
# counterpart -- no new stat dimension, no playstyle differentiation, just a
# second name/theme at the same power level. Gold is kept IDENTICAL to the
# original item so there's no "objectively better deal" between the two. The
# secondary resource is swapped from bones/blood_gems (Guillotine, 5/hr) to
# fish/herbs (Sea Lion Pit/Club Soda, 12.5/hr) to spread farming load off
# Guillotine -- amounts are scaled by that same 12.5/5 = 2.5x rate difference
# so the alternative costs the same GATHERING TIME, not less. Uncommon keeps
# its blood_gems component unchanged (only the bones portion is swapped);
# rare keeps spell_fragments unchanged and swaps out its blood_gems portion
# instead. Barracks items have never had individual worn-gear sprites (the
# shop UI shows a generic per-slot emoji, and the worn-gear overlay system
# already tolerates a missing sprite file via its existing
# `if not os.path.exists(item_path): continue` skip).
#
# epic/legendary: standalone (no set_name -- barracks_buy() always writes
# NULL), so these grant no set bonus. CP per slot matches gear_templates'
# own epic/legendary split exactly (Temple Mystic 28/22/20/25, Penguin
# Emperor 45/35/32/42) so a forged item is exactly as strong as the
# equivalent drop-set piece. Cost keeps the ~2.5-3x per-tier gold/resource
# growth already established from common->rare. bones and mayor_seals stay
# out (bones was already dropped at rare; mayor_seals stays walled off to
# the Seal Shop). fish/herbs/ice_blocks are folded in as a
# same-gathering-TIME-value slice carved out of each item's existing
# spell_fragments/blood_gems rather than added on top (25% of
# spell_fragments -> fish for weapon/boots or herbs for helmet/armor, 1:1
# since both produce at 12.5/hr; 20% of blood_gems -> ice_blocks at a ~4.2x
# ratio, derived from update_passive_energy()'s 10 energy/hr regen spent at
# build_roll()'s 5-energy-per-roll cost, averaging ~10.5 ice_blocks/roll ->
# ~21/hr, against blood_gems' 5/hr).
DEFAULT_BARRACKS_SHOP = {
    "common": [
        {"id": "iron_sword",   "name": "Iron Sword",   "slot": "weapon", "combat_power": 4,  "cost": {"gold": 200, "bones": 50}},
        {"id": "iron_helmet",  "name": "Iron Helmet",  "slot": "helmet", "combat_power": 3,  "cost": {"gold": 200, "bones": 40}},
        {"id": "iron_boots",   "name": "Iron Boots",   "slot": "boots",  "combat_power": 3,  "cost": {"gold": 150, "bones": 30}},
        {"id": "iron_plate",   "name": "Iron Plate",   "slot": "armor",  "combat_power": 4,  "cost": {"gold": 250, "bones": 60}},
        {"id": "driftwood_club",    "name": "Driftwood Club",    "slot": "weapon", "combat_power": 4,  "cost": {"gold": 200, "fish": 125}},
        {"id": "driftwood_cap",     "name": "Driftwood Cap",     "slot": "helmet", "combat_power": 3,  "cost": {"gold": 200, "herbs": 100}},
        {"id": "driftwood_sandals", "name": "Driftwood Sandals", "slot": "boots",  "combat_power": 3,  "cost": {"gold": 150, "fish": 75}},
        {"id": "driftwood_vest",    "name": "Driftwood Vest",    "slot": "armor",  "combat_power": 4,  "cost": {"gold": 250, "herbs": 150}},
    ],
    "uncommon": [
        {"id": "steel_sword",  "name": "Steel Sword",  "slot": "weapon", "combat_power": 9,  "cost": {"gold": 500,  "bones": 100, "blood_gems": 20}},
        {"id": "steel_helmet", "name": "Steel Helmet", "slot": "helmet", "combat_power": 7,  "cost": {"gold": 500,  "bones": 80,  "blood_gems": 15}},
        {"id": "steel_boots",  "name": "Steel Boots",  "slot": "boots",  "combat_power": 6,  "cost": {"gold": 400,  "bones": 70,  "blood_gems": 15}},
        {"id": "steel_plate",  "name": "Steel Plate",  "slot": "armor",  "combat_power": 9,  "cost": {"gold": 600,  "bones": 120, "blood_gems": 25}},
        {"id": "coral_blade", "name": "Coral Blade", "slot": "weapon", "combat_power": 9,  "cost": {"gold": 500, "fish": 250,  "blood_gems": 20}},
        {"id": "coral_helm",  "name": "Coral Helm",  "slot": "helmet", "combat_power": 7,  "cost": {"gold": 500, "herbs": 200, "blood_gems": 15}},
        {"id": "coral_boots", "name": "Coral Boots", "slot": "boots",  "combat_power": 6,  "cost": {"gold": 400, "fish": 175,  "blood_gems": 15}},
        {"id": "coral_guard", "name": "Coral Guard", "slot": "armor",  "combat_power": 9,  "cost": {"gold": 600, "herbs": 300, "blood_gems": 25}},
    ],
    "rare": [
        {"id": "crystal_blade",   "name": "Crystal Blade",   "slot": "weapon", "combat_power": 19, "cost": {"gold": 1500, "blood_gems": 80,  "spell_fragments": 40}},
        {"id": "crystal_crown",   "name": "Crystal Crown",   "slot": "helmet", "combat_power": 15, "cost": {"gold": 1200, "blood_gems": 60,  "spell_fragments": 30}},
        {"id": "crystal_greaves", "name": "Crystal Greaves", "slot": "boots",  "combat_power": 14, "cost": {"gold": 1000, "blood_gems": 50,  "spell_fragments": 25}},
        {"id": "crystal_armor",   "name": "Crystal Armor",   "slot": "armor",  "combat_power": 18, "cost": {"gold": 1800, "blood_gems": 100, "spell_fragments": 50}},
        {"id": "aurora_blade",  "name": "Aurora Blade",  "slot": "weapon", "combat_power": 19, "cost": {"gold": 1500, "fish": 200,  "spell_fragments": 40}},
        {"id": "aurora_diadem", "name": "Aurora Diadem", "slot": "helmet", "combat_power": 15, "cost": {"gold": 1200, "herbs": 150, "spell_fragments": 30}},
        {"id": "aurora_boots",  "name": "Aurora Boots",  "slot": "boots",  "combat_power": 14, "cost": {"gold": 1000, "fish": 125,  "spell_fragments": 25}},
        {"id": "aurora_mail",   "name": "Aurora Mail",   "slot": "armor",  "combat_power": 18, "cost": {"gold": 1800, "herbs": 250, "spell_fragments": 50}},
    ],
    "epic": [
        {"id": "obsidian_blade",   "name": "Obsidian Blade",   "slot": "weapon", "combat_power": 28, "cost": {"gold": 4000, "blood_gems": 176, "spell_fragments": 82,  "fish": 28,           "ice_blocks": 185}},
        {"id": "obsidian_crest",   "name": "Obsidian Crest",   "slot": "helmet", "combat_power": 22, "cost": {"gold": 3200, "blood_gems": 128, "spell_fragments": 60,  "herbs": 20,          "ice_blocks": 134}},
        {"id": "obsidian_greaves", "name": "Obsidian Greaves", "slot": "boots",  "combat_power": 20, "cost": {"gold": 2700, "blood_gems": 108, "spell_fragments": 52,  "fish": 18,           "ice_blocks": 113}},
        {"id": "obsidian_plate",   "name": "Obsidian Plate",   "slot": "armor",  "combat_power": 25, "cost": {"gold": 4800, "blood_gems": 216, "spell_fragments": 101, "herbs": 34,          "ice_blocks": 227}},
    ],
    "legendary": [
        {"id": "mythril_blade",    "name": "Mythril Blade",    "slot": "weapon", "combat_power": 45, "cost": {"gold": 11000, "blood_gems": 480, "spell_fragments": 225, "fish": 75,  "ice_blocks": 504}},
        {"id": "mythril_diadem",   "name": "Mythril Diadem",   "slot": "helmet", "combat_power": 35, "cost": {"gold": 8600,  "blood_gems": 344, "spell_fragments": 165, "herbs": 55, "ice_blocks": 361}},
        {"id": "mythril_sabatons", "name": "Mythril Sabatons", "slot": "boots",  "combat_power": 32, "cost": {"gold": 7300,  "blood_gems": 292, "spell_fragments": 142, "fish": 48,  "ice_blocks": 307}},
        {"id": "mythril_plate",    "name": "Mythril Plate",    "slot": "armor",  "combat_power": 42, "cost": {"gold": 13000, "blood_gems": 584, "spell_fragments": 274, "herbs": 91, "ice_blocks": 613}},
    ],
}

DEFAULT_BOUTIQUE_ITEMS = {
    "hats": [
        {"id": "baseball_cap",  "name": "Baseball Cap",  "slot": "hat", "price": 200,  "tier": "cheap"},
        {"id": "beanie",        "name": "Beanie",         "slot": "hat", "price": 350,  "tier": "cheap"},
        {"id": "party_hat",     "name": "Party Hat",      "slot": "hat", "price": 400,  "tier": "mid", "event_exclusive": True},
        {"id": "beret",         "name": "Beret",          "slot": "hat", "price": 450,  "tier": "mid"},
        {"id": "chefs_hat",     "name": "Chef's Hat",     "slot": "hat", "price": 500,  "tier": "mid"},
        {"id": "cowboy_hat",    "name": "Cowboy Hat",     "slot": "hat", "price": 600,  "tier": "mid"},
        {"id": "viking_helmet", "name": "Viking Helmet",  "slot": "hat", "price": 800,  "tier": "mid"},
        {"id": "top_hat",       "name": "Top Hat",        "slot": "hat", "price": 800,  "tier": "mid"},
        {"id": "pirate_hat",    "name": "Pirate Hat",     "slot": "hat", "price": 1000, "tier": "expensive"},
    ],
    "outfits": [
        {"id": "plain_tshirt",    "name": "Plain T-Shirt",    "slot": "outfit", "price": 200,  "tier": "cheap"},
        {"id": "hawaiian_shirt",  "name": "Hawaiian Shirt",   "slot": "outfit", "price": 350,  "tier": "cheap"},
        {"id": "hoodie",          "name": "Hoodie",           "slot": "outfit", "price": 400,  "tier": "mid"},
        {"id": "bra",             "name": "Bra",              "slot": "outfit", "price": 500,  "tier": "mid"},
        {"id": "lab_coat",        "name": "Lab Coat",         "slot": "outfit", "price": 600,  "tier": "mid"},
        {"id": "leather_jacket",  "name": "Leather Jacket",   "slot": "outfit", "price": 800,  "tier": "mid"},
        {"id": "tuxedo_vest",     "name": "Tuxedo Vest",      "slot": "outfit", "price": 1200, "tier": "expensive"},
        {"id": "superhero_cape",  "name": "Superhero Cape",   "slot": "outfit", "price": 1500, "tier": "expensive"},
        {"id": "tuxedo",          "name": "Full Tuxedo",      "slot": "outfit", "price": 2500, "tier": "expensive"},
    ],
    "footwear": [
        {"id": "sandals",       "name": "Sandals",       "slot": "footwear", "price": 150, "tier": "cheap"},
        {"id": "sneakers",      "name": "Sneakers",      "slot": "footwear", "price": 200, "tier": "cheap"},
        {"id": "fuzzy_slippers","name": "Fuzzy Slippers","slot": "footwear", "price": 250, "tier": "cheap"},
        {"id": "rain_boots",    "name": "Rain Boots",    "slot": "footwear", "price": 300, "tier": "cheap"},
        {"id": "roller_skates", "name": "Roller Skates", "slot": "footwear", "price": 500, "tier": "mid"},
        {"id": "cowboy_boots",  "name": "Cowboy Boots",  "slot": "footwear", "price": 700, "tier": "mid"},
    ],
    "accessories": [
        {"id": "lollipop",    "name": "Lollipop",    "slot": "accessory", "price": 150,  "tier": "cheap"},
        {"id": "scarf_shop",  "name": "Scarf",        "slot": "accessory", "price": 200,  "tier": "cheap"},
        {"id": "sunglasses",  "name": "Sunglasses",   "slot": "accessory", "price": 300,  "tier": "cheap"},
        {"id": "bow_tie",     "name": "Bow Tie",       "slot": "accessory", "price": 350,  "tier": "mid"},
        {"id": "backpack",    "name": "Backpack",      "slot": "accessory", "price": 400,  "tier": "mid"},
        {"id": "monocle",     "name": "Monocle",       "slot": "accessory", "price": 500,  "tier": "mid"},
        {"id": "bubble_pipe", "name": "Bubble Pipe",   "slot": "accessory", "price": 600,  "tier": "mid"},
        {"id": "village_bandana","name": "Village Bandana","slot": "accessory","price": 750,  "tier": "mid"},
        {"id": "gold_chain",  "name": "Gold Chain",    "slot": "accessory", "price": 1000, "tier": "expensive"},
        {"id": "dragon_wings","name": "Dragon Wings",  "slot": "accessory", "price": 3000, "tier": "expensive"},
    ],
}

# -- Session 8: combat gear level tiers --
#
# 26 sets replace the old 4 (Frost Guardian/Blood Reaper/Temple Mystic/
# Penguin Emperor): 5 families x 5 rarity stages (common->legendary) + the
# standalone Penguin Emperor set. Each family IS a level tier -- every stage
# within a family shares that family's required_level schedule and 2pc/3pc
# set-bonus percentages (see SET_BONUSES below), only the rarity stage
# (name/combat_power) differs:
#   Frost    (lvl 1-5,   T1): Icicle(C) -> Frost(U) -> Glacial(R) -> Permafrost(E) -> Absolute Zero(L)
#   Blood    (lvl 6-10,  T2): Bone(C) -> Blood Reaper(U) -> Crimson Fury(R) -> Skullcracker(E) -> Grim Reaper(L)
#   Storm    (lvl 11-15, T3): Squall(C) -> Storm(U) -> Tempest(R) -> Maelstrom(E) -> Godstorm(L)
#   Sea Lion (lvl 16-20, T4): Pup(C) -> Sea Lion(U) -> Leopard Seal(R) -> Orca(E) -> Kraken(L)
#   Temple   (lvl 21-30, T5): Acolyte(C) -> Mystic(U) -> Cursed(R) -> Forbidden(E) -> Eldritch(L)
# required_level within a family: common/uncommon/rare share the tier's
# floor, epic and legendary step up from there (e.g. Frost: 1/1/1/3/4).
# combat_power per rarity is IDENTICAL across all 5 families+standalone --
# reuses the exact per-slot split the old 4 sets already established
# (weapon/helmet/boots/armor): common 3/2/2/3, uncommon 7/5/5/7,
# rare 15/12/11/14, epic 28/22/20/25, legendary 45/35/32/42 -- tiers
# differentiate by required_level, not raw power. Penguin Emperor scales
# that same legendary split proportionally up to a 190 total (56/43/39/52),
# required_level 25 on all 4 pieces, standalone (not part of the 5-tier
# ladder). The 4 non-set common items below predate this pass and aren't
# part of "the existing 4 sets" being replaced (no set_name -- never granted
# a set bonus), so they're kept as-is with required_level=1.
DEFAULT_GEAR_TEMPLATES = {
    "common": [
        {"name": "Rusty Sword",  "slot": "weapon", "set_name": None, "combat_power": 3, "required_level": 1},
        {"name": "Leather Cap",  "slot": "helmet", "set_name": None, "combat_power": 2, "required_level": 1},
        {"name": "Worn Boots",   "slot": "boots",  "set_name": None, "combat_power": 2, "required_level": 1},
        {"name": "Padded Vest",  "slot": "armor",  "set_name": None, "combat_power": 3, "required_level": 1},
        {"name": "Icicle Blade", "slot": "weapon", "set_name": "Icicle", "combat_power": 3, "required_level": 1},
        {"name": "Icicle Helm", "slot": "helmet", "set_name": "Icicle", "combat_power": 2, "required_level": 1},
        {"name": "Icicle Greaves", "slot": "boots", "set_name": "Icicle", "combat_power": 2, "required_level": 1},
        {"name": "Icicle Mail", "slot": "armor", "set_name": "Icicle", "combat_power": 3, "required_level": 1},
        {"name": "Bone Scythe", "slot": "weapon", "set_name": "Bone", "combat_power": 3, "required_level": 6},
        {"name": "Bone Crown", "slot": "helmet", "set_name": "Bone", "combat_power": 2, "required_level": 6},
        {"name": "Bone Stompers", "slot": "boots", "set_name": "Bone", "combat_power": 2, "required_level": 6},
        {"name": "Bone Plate", "slot": "armor", "set_name": "Bone", "combat_power": 3, "required_level": 6},
        {"name": "Squall Bolt", "slot": "weapon", "set_name": "Squall", "combat_power": 3, "required_level": 11},
        {"name": "Squall Crest", "slot": "helmet", "set_name": "Squall", "combat_power": 2, "required_level": 11},
        {"name": "Squall Treads", "slot": "boots", "set_name": "Squall", "combat_power": 2, "required_level": 11},
        {"name": "Squall Vestments", "slot": "armor", "set_name": "Squall", "combat_power": 3, "required_level": 11},
        {"name": "Pup Fang", "slot": "weapon", "set_name": "Pup", "combat_power": 3, "required_level": 16},
        {"name": "Pup Hood", "slot": "helmet", "set_name": "Pup", "combat_power": 2, "required_level": 16},
        {"name": "Pup Flippers", "slot": "boots", "set_name": "Pup", "combat_power": 2, "required_level": 16},
        {"name": "Pup Hide", "slot": "armor", "set_name": "Pup", "combat_power": 3, "required_level": 16},
        {"name": "Acolyte Staff", "slot": "weapon", "set_name": "Acolyte", "combat_power": 3, "required_level": 21},
        {"name": "Acolyte Hood", "slot": "helmet", "set_name": "Acolyte", "combat_power": 2, "required_level": 21},
        {"name": "Acolyte Sandals", "slot": "boots", "set_name": "Acolyte", "combat_power": 2, "required_level": 21},
        {"name": "Acolyte Robes", "slot": "armor", "set_name": "Acolyte", "combat_power": 3, "required_level": 21},
    ],
    "uncommon": [
        {"name": "Frost Blade", "slot": "weapon", "set_name": "Frost", "combat_power": 7, "required_level": 1},
        {"name": "Frost Helm", "slot": "helmet", "set_name": "Frost", "combat_power": 5, "required_level": 1},
        {"name": "Frost Greaves", "slot": "boots", "set_name": "Frost", "combat_power": 5, "required_level": 1},
        {"name": "Frost Mail", "slot": "armor", "set_name": "Frost", "combat_power": 7, "required_level": 1},
        {"name": "Blood Reaper Scythe", "slot": "weapon", "set_name": "Blood Reaper", "combat_power": 7, "required_level": 6},
        {"name": "Blood Reaper Crown", "slot": "helmet", "set_name": "Blood Reaper", "combat_power": 5, "required_level": 6},
        {"name": "Blood Reaper Stompers", "slot": "boots", "set_name": "Blood Reaper", "combat_power": 5, "required_level": 6},
        {"name": "Blood Reaper Plate", "slot": "armor", "set_name": "Blood Reaper", "combat_power": 7, "required_level": 6},
        {"name": "Storm Bolt", "slot": "weapon", "set_name": "Storm", "combat_power": 7, "required_level": 11},
        {"name": "Storm Crest", "slot": "helmet", "set_name": "Storm", "combat_power": 5, "required_level": 11},
        {"name": "Storm Treads", "slot": "boots", "set_name": "Storm", "combat_power": 5, "required_level": 11},
        {"name": "Storm Vestments", "slot": "armor", "set_name": "Storm", "combat_power": 7, "required_level": 11},
        {"name": "Sea Lion Fang", "slot": "weapon", "set_name": "Sea Lion", "combat_power": 7, "required_level": 16},
        {"name": "Sea Lion Hood", "slot": "helmet", "set_name": "Sea Lion", "combat_power": 5, "required_level": 16},
        {"name": "Sea Lion Flippers", "slot": "boots", "set_name": "Sea Lion", "combat_power": 5, "required_level": 16},
        {"name": "Sea Lion Hide", "slot": "armor", "set_name": "Sea Lion", "combat_power": 7, "required_level": 16},
        {"name": "Mystic Staff", "slot": "weapon", "set_name": "Mystic", "combat_power": 7, "required_level": 21},
        {"name": "Mystic Hood", "slot": "helmet", "set_name": "Mystic", "combat_power": 5, "required_level": 21},
        {"name": "Mystic Sandals", "slot": "boots", "set_name": "Mystic", "combat_power": 5, "required_level": 21},
        {"name": "Mystic Robes", "slot": "armor", "set_name": "Mystic", "combat_power": 7, "required_level": 21},
    ],
    "rare": [
        {"name": "Glacial Blade", "slot": "weapon", "set_name": "Glacial", "combat_power": 15, "required_level": 1},
        {"name": "Glacial Helm", "slot": "helmet", "set_name": "Glacial", "combat_power": 12, "required_level": 1},
        {"name": "Glacial Greaves", "slot": "boots", "set_name": "Glacial", "combat_power": 11, "required_level": 1},
        {"name": "Glacial Mail", "slot": "armor", "set_name": "Glacial", "combat_power": 14, "required_level": 1},
        {"name": "Crimson Fury Scythe", "slot": "weapon", "set_name": "Crimson Fury", "combat_power": 15, "required_level": 6},
        {"name": "Crimson Fury Crown", "slot": "helmet", "set_name": "Crimson Fury", "combat_power": 12, "required_level": 6},
        {"name": "Crimson Fury Stompers", "slot": "boots", "set_name": "Crimson Fury", "combat_power": 11, "required_level": 6},
        {"name": "Crimson Fury Plate", "slot": "armor", "set_name": "Crimson Fury", "combat_power": 14, "required_level": 6},
        {"name": "Tempest Bolt", "slot": "weapon", "set_name": "Tempest", "combat_power": 15, "required_level": 11},
        {"name": "Tempest Crest", "slot": "helmet", "set_name": "Tempest", "combat_power": 12, "required_level": 11},
        {"name": "Tempest Treads", "slot": "boots", "set_name": "Tempest", "combat_power": 11, "required_level": 11},
        {"name": "Tempest Vestments", "slot": "armor", "set_name": "Tempest", "combat_power": 14, "required_level": 11},
        {"name": "Leopard Seal Fang", "slot": "weapon", "set_name": "Leopard Seal", "combat_power": 15, "required_level": 16},
        {"name": "Leopard Seal Hood", "slot": "helmet", "set_name": "Leopard Seal", "combat_power": 12, "required_level": 16},
        {"name": "Leopard Seal Flippers", "slot": "boots", "set_name": "Leopard Seal", "combat_power": 11, "required_level": 16},
        {"name": "Leopard Seal Hide", "slot": "armor", "set_name": "Leopard Seal", "combat_power": 14, "required_level": 16},
        {"name": "Cursed Staff", "slot": "weapon", "set_name": "Cursed", "combat_power": 15, "required_level": 21},
        {"name": "Cursed Hood", "slot": "helmet", "set_name": "Cursed", "combat_power": 12, "required_level": 21},
        {"name": "Cursed Sandals", "slot": "boots", "set_name": "Cursed", "combat_power": 11, "required_level": 21},
        {"name": "Cursed Robes", "slot": "armor", "set_name": "Cursed", "combat_power": 14, "required_level": 21},
    ],
    "epic": [
        {"name": "Permafrost Blade", "slot": "weapon", "set_name": "Permafrost", "combat_power": 28, "required_level": 3},
        {"name": "Permafrost Helm", "slot": "helmet", "set_name": "Permafrost", "combat_power": 22, "required_level": 3},
        {"name": "Permafrost Greaves", "slot": "boots", "set_name": "Permafrost", "combat_power": 20, "required_level": 3},
        {"name": "Permafrost Mail", "slot": "armor", "set_name": "Permafrost", "combat_power": 25, "required_level": 3},
        {"name": "Skullcracker Scythe", "slot": "weapon", "set_name": "Skullcracker", "combat_power": 28, "required_level": 8},
        {"name": "Skullcracker Crown", "slot": "helmet", "set_name": "Skullcracker", "combat_power": 22, "required_level": 8},
        {"name": "Skullcracker Stompers", "slot": "boots", "set_name": "Skullcracker", "combat_power": 20, "required_level": 8},
        {"name": "Skullcracker Plate", "slot": "armor", "set_name": "Skullcracker", "combat_power": 25, "required_level": 8},
        {"name": "Maelstrom Bolt", "slot": "weapon", "set_name": "Maelstrom", "combat_power": 28, "required_level": 13},
        {"name": "Maelstrom Crest", "slot": "helmet", "set_name": "Maelstrom", "combat_power": 22, "required_level": 13},
        {"name": "Maelstrom Treads", "slot": "boots", "set_name": "Maelstrom", "combat_power": 20, "required_level": 13},
        {"name": "Maelstrom Vestments", "slot": "armor", "set_name": "Maelstrom", "combat_power": 25, "required_level": 13},
        {"name": "Orca Fang", "slot": "weapon", "set_name": "Orca", "combat_power": 28, "required_level": 18},
        {"name": "Orca Hood", "slot": "helmet", "set_name": "Orca", "combat_power": 22, "required_level": 18},
        {"name": "Orca Flippers", "slot": "boots", "set_name": "Orca", "combat_power": 20, "required_level": 18},
        {"name": "Orca Hide", "slot": "armor", "set_name": "Orca", "combat_power": 25, "required_level": 18},
        {"name": "Forbidden Staff", "slot": "weapon", "set_name": "Forbidden", "combat_power": 28, "required_level": 23},
        {"name": "Forbidden Hood", "slot": "helmet", "set_name": "Forbidden", "combat_power": 22, "required_level": 23},
        {"name": "Forbidden Sandals", "slot": "boots", "set_name": "Forbidden", "combat_power": 20, "required_level": 23},
        {"name": "Forbidden Robes", "slot": "armor", "set_name": "Forbidden", "combat_power": 25, "required_level": 23},
    ],
    "legendary": [
        {"name": "Absolute Zero Blade", "slot": "weapon", "set_name": "Absolute Zero", "combat_power": 45, "required_level": 4},
        {"name": "Absolute Zero Helm", "slot": "helmet", "set_name": "Absolute Zero", "combat_power": 35, "required_level": 4},
        {"name": "Absolute Zero Greaves", "slot": "boots", "set_name": "Absolute Zero", "combat_power": 32, "required_level": 4},
        {"name": "Absolute Zero Mail", "slot": "armor", "set_name": "Absolute Zero", "combat_power": 42, "required_level": 4},
        {"name": "Grim Reaper Scythe", "slot": "weapon", "set_name": "Grim Reaper", "combat_power": 45, "required_level": 9},
        {"name": "Grim Reaper Crown", "slot": "helmet", "set_name": "Grim Reaper", "combat_power": 35, "required_level": 9},
        {"name": "Grim Reaper Stompers", "slot": "boots", "set_name": "Grim Reaper", "combat_power": 32, "required_level": 9},
        {"name": "Grim Reaper Plate", "slot": "armor", "set_name": "Grim Reaper", "combat_power": 42, "required_level": 9},
        {"name": "Godstorm Bolt", "slot": "weapon", "set_name": "Godstorm", "combat_power": 45, "required_level": 14},
        {"name": "Godstorm Crest", "slot": "helmet", "set_name": "Godstorm", "combat_power": 35, "required_level": 14},
        {"name": "Godstorm Treads", "slot": "boots", "set_name": "Godstorm", "combat_power": 32, "required_level": 14},
        {"name": "Godstorm Vestments", "slot": "armor", "set_name": "Godstorm", "combat_power": 42, "required_level": 14},
        {"name": "Kraken Fang", "slot": "weapon", "set_name": "Kraken", "combat_power": 45, "required_level": 19},
        {"name": "Kraken Hood", "slot": "helmet", "set_name": "Kraken", "combat_power": 35, "required_level": 19},
        {"name": "Kraken Flippers", "slot": "boots", "set_name": "Kraken", "combat_power": 32, "required_level": 19},
        {"name": "Kraken Hide", "slot": "armor", "set_name": "Kraken", "combat_power": 42, "required_level": 19},
        {"name": "Eldritch Staff", "slot": "weapon", "set_name": "Eldritch", "combat_power": 45, "required_level": 24},
        {"name": "Eldritch Hood", "slot": "helmet", "set_name": "Eldritch", "combat_power": 35, "required_level": 24},
        {"name": "Eldritch Sandals", "slot": "boots", "set_name": "Eldritch", "combat_power": 32, "required_level": 24},
        {"name": "Eldritch Robes", "slot": "armor", "set_name": "Eldritch", "combat_power": 42, "required_level": 24},
        {"name": "Emperor's Scepter", "slot": "weapon", "set_name": "Penguin Emperor", "combat_power": 56, "required_level": 25},
        {"name": "Emperor's Diadem", "slot": "helmet", "set_name": "Penguin Emperor", "combat_power": 43, "required_level": 25},
        {"name": "Emperor's Sabatons", "slot": "boots", "set_name": "Penguin Emperor", "combat_power": 39, "required_level": 25},
        {"name": "Emperor's Regalia", "slot": "armor", "set_name": "Penguin Emperor", "combat_power": 52, "required_level": 25},
    ],
}

# Set-bonus scaling is per TIER (family), shared by all 5 rarity stages
# within it, and mutually exclusive 2pc-vs-3pc same as before (Session 7's
# stacking fix in calculate_set_bonuses -- only the highest piece-count tier
# a player reaches applies). Unlike the old table, these are PERCENTAGES of
# total combat power (not flat CP): bonus_2pc_cp/bonus_3pc_cp store whole
# percentage points (e.g. 5 == +5%) -- see calculate_set_bonuses() in
# app.py, which now applies the sum multiplicatively instead of adding it.
# Frost/Blood/Storm reuse the existing "buff combat power" convention every
# prior set already used. Sea Lion and Temple are new families -- their
# bonus is flavored (aquatic instinct / mystic focus in the description)
# but mechanically still combat_power_bonus, since that's the only stat
# calculate_set_bonuses currently wires up (attack/defense/speed/hp bonus
# are hardcoded to 0 for sets, individual-item-only). No secret-cosmetic
# tier for any of these 26 -- the task only specced 2pc/3-4pc scaling.
DEFAULT_SET_BONUSES = {
    "Icicle": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 3, "description": "+3% Combat Power"},
        "3pc": {"combat_power_bonus": 6, "description": "+6% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Frost": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 3, "description": "+3% Combat Power"},
        "3pc": {"combat_power_bonus": 6, "description": "+6% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Glacial": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 3, "description": "+3% Combat Power"},
        "3pc": {"combat_power_bonus": 6, "description": "+6% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Permafrost": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 3, "description": "+3% Combat Power"},
        "3pc": {"combat_power_bonus": 6, "description": "+6% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Absolute Zero": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 3, "description": "+3% Combat Power"},
        "3pc": {"combat_power_bonus": 6, "description": "+6% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Bone": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 5, "description": "+5% Combat Power"},
        "3pc": {"combat_power_bonus": 10, "description": "+10% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Blood Reaper": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 5, "description": "+5% Combat Power"},
        "3pc": {"combat_power_bonus": 10, "description": "+10% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Crimson Fury": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 5, "description": "+5% Combat Power"},
        "3pc": {"combat_power_bonus": 10, "description": "+10% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Skullcracker": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 5, "description": "+5% Combat Power"},
        "3pc": {"combat_power_bonus": 10, "description": "+10% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Grim Reaper": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 5, "description": "+5% Combat Power"},
        "3pc": {"combat_power_bonus": 10, "description": "+10% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Squall": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 7, "description": "+7% Combat Power"},
        "3pc": {"combat_power_bonus": 14, "description": "+14% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Storm": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 7, "description": "+7% Combat Power"},
        "3pc": {"combat_power_bonus": 14, "description": "+14% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Tempest": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 7, "description": "+7% Combat Power"},
        "3pc": {"combat_power_bonus": 14, "description": "+14% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Maelstrom": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 7, "description": "+7% Combat Power"},
        "3pc": {"combat_power_bonus": 14, "description": "+14% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Godstorm": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 7, "description": "+7% Combat Power"},
        "3pc": {"combat_power_bonus": 14, "description": "+14% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Pup": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 9, "description": "+9% Combat Power (Aquatic Instinct)"},
        "3pc": {"combat_power_bonus": 18, "description": "+18% Combat Power (Aquatic Instinct)"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Sea Lion": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 9, "description": "+9% Combat Power (Aquatic Instinct)"},
        "3pc": {"combat_power_bonus": 18, "description": "+18% Combat Power (Aquatic Instinct)"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Leopard Seal": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 9, "description": "+9% Combat Power (Aquatic Instinct)"},
        "3pc": {"combat_power_bonus": 18, "description": "+18% Combat Power (Aquatic Instinct)"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Orca": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 9, "description": "+9% Combat Power (Aquatic Instinct)"},
        "3pc": {"combat_power_bonus": 18, "description": "+18% Combat Power (Aquatic Instinct)"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Kraken": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 9, "description": "+9% Combat Power (Aquatic Instinct)"},
        "3pc": {"combat_power_bonus": 18, "description": "+18% Combat Power (Aquatic Instinct)"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Acolyte": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 11, "description": "+11% Combat Power (Mystic Focus)"},
        "3pc": {"combat_power_bonus": 22, "description": "+22% Combat Power (Mystic Focus)"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Mystic": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 11, "description": "+11% Combat Power (Mystic Focus)"},
        "3pc": {"combat_power_bonus": 22, "description": "+22% Combat Power (Mystic Focus)"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Cursed": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 11, "description": "+11% Combat Power (Mystic Focus)"},
        "3pc": {"combat_power_bonus": 22, "description": "+22% Combat Power (Mystic Focus)"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Forbidden": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 11, "description": "+11% Combat Power (Mystic Focus)"},
        "3pc": {"combat_power_bonus": 22, "description": "+22% Combat Power (Mystic Focus)"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Eldritch": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 11, "description": "+11% Combat Power (Mystic Focus)"},
        "3pc": {"combat_power_bonus": 22, "description": "+22% Combat Power (Mystic Focus)"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
    "Penguin Emperor": {
        "pieces_needed": 3,
        "2pc": {"combat_power_bonus": 15, "description": "+15% Combat Power"},
        "3pc": {"combat_power_bonus": 30, "description": "+30% Combat Power"},
        "secret": {"cosmetic_required": None, "combat_power_bonus": 0, "description": "No secret bonus"},
    },
}


def _get_db():
    conn = sqlite3.connect(DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _slugify(text):
    import re
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _seed_barracks_shop_if_empty(db, owns_conn):
    if db.execute("SELECT 1 FROM barracks_shop LIMIT 1").fetchone():
        return
    for rarity, items in DEFAULT_BARRACKS_SHOP.items():
        for item in items:
            db.execute(
                "INSERT OR IGNORE INTO barracks_shop (id, name, slot, rarity, combat_power, cost, event_exclusive, required_level) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (item["id"], item["name"], item["slot"], rarity, item["combat_power"],
                 json.dumps(item["cost"]), int(bool(item.get("event_exclusive", False))),
                 _BARRACKS_REQUIRED_LEVEL.get(rarity, 1))
            )
    if owns_conn:
        db.commit()


def _seed_boutique_items_if_empty(db, owns_conn):
    if db.execute("SELECT 1 FROM boutique_items LIMIT 1").fetchone():
        return
    for category, items in DEFAULT_BOUTIQUE_ITEMS.items():
        for item in items:
            db.execute(
                "INSERT OR IGNORE INTO boutique_items (id, name, category, slot, price, tier, event_exclusive) "
                "VALUES (?,?,?,?,?,?,?)",
                (item["id"], item["name"], category, item["slot"], item["price"], item["tier"],
                 int(bool(item.get("event_exclusive", False))))
            )
    if owns_conn:
        db.commit()


def _seed_gear_templates_if_empty(db, owns_conn):
    if db.execute("SELECT 1 FROM gear_templates LIMIT 1").fetchone():
        return
    for rarity, items in DEFAULT_GEAR_TEMPLATES.items():
        for item in items:
            gid = f"{_slugify(item['name'])}_{item['slot']}_{rarity}"
            db.execute(
                "INSERT OR IGNORE INTO gear_templates (id, name, slot, rarity, set_name, combat_power, required_level) "
                "VALUES (?,?,?,?,?,?,?)",
                (gid, item["name"], item["slot"], rarity, item["set_name"], item["combat_power"],
                 item.get("required_level", 1))
            )
    if owns_conn:
        db.commit()


def _seed_set_bonuses_if_empty(db, owns_conn):
    if db.execute("SELECT 1 FROM set_bonuses LIMIT 1").fetchone():
        return
    for set_name, sb in DEFAULT_SET_BONUSES.items():
        db.execute(
            "INSERT OR IGNORE INTO set_bonuses "
            "(set_name, pieces_needed, bonus_2pc_cp, bonus_2pc_desc, bonus_3pc_cp, bonus_3pc_desc, "
            "secret_cosmetic_required, secret_cp, secret_desc) VALUES (?,?,?,?,?,?,?,?,?)",
            (set_name, sb["pieces_needed"],
             sb["2pc"]["combat_power_bonus"], sb["2pc"]["description"],
             sb["3pc"]["combat_power_bonus"], sb["3pc"]["description"],
             sb["secret"]["cosmetic_required"], sb["secret"]["combat_power_bonus"], sb["secret"]["description"])
        )
    if owns_conn:
        db.commit()


def load_barracks_shop(db=None):
    """Same shape as the old BARRACKS_SHOP literal, plus a "required_level"
    key (Session 8): dict of rarity -> list of
    {"id","name","slot","combat_power","cost","required_level", optionally
    "event_exclusive": True}.

    Pass the caller's own already-open `db` connection when calling mid-
    transaction -- see raid_settings.get_setting's docstring for why opening
    a second connection there is a real bug class in this codebase, not
    theoretical. Omit `db` for a standalone call (opens/closes its own).

    Read-only -- seeding happens once in database.py's init_db(), not here.
    A lazy seed-on-read was tried and reverted: this function can run on a
    borrowed `db` from a caller that's mid-transaction (e.g.
    calculate_set_bonuses), and a SECOND, unrelated connection calling this
    at the same time (e.g. get_combat_power() opens its own) could try to
    write the seed rows into a table the first connection already holds an
    uncommitted lock on -- a real "database is locked" error, not
    theoretical (hit it via /combat/fight -> get_combat_power ->
    calculate_set_bonuses -> load_set_bonuses while another connection had
    an open transaction). Seeding once in init_db(), before any request
    handling starts, avoids that entirely.
    """
    owns_conn = db is None
    if owns_conn:
        db = _get_db()
    rows = db.execute("SELECT * FROM barracks_shop ORDER BY rowid").fetchall()
    if owns_conn:
        db.close()
    result = {}
    for row in rows:
        item = {
            "id": row["id"], "name": row["name"], "slot": row["slot"],
            "combat_power": row["combat_power"], "cost": json.loads(row["cost"]),
            "required_level": row["required_level"],
        }
        if row["event_exclusive"]:
            item["event_exclusive"] = True
        result.setdefault(row["rarity"], []).append(item)
    return result


def load_boutique_items(db=None):
    """Same shape as the old BOUTIQUE_ITEMS literal: dict of
    category -> list of {"id","name","slot","price","tier", optionally
    "event_exclusive": True}. Same optional-`db` convention as
    load_barracks_shop() -- read-only, see that docstring for why seeding
    isn't done lazily here."""
    owns_conn = db is None
    if owns_conn:
        db = _get_db()
    rows = db.execute("SELECT * FROM boutique_items ORDER BY rowid").fetchall()
    if owns_conn:
        db.close()
    result = {}
    for row in rows:
        item = {
            "id": row["id"], "name": row["name"], "slot": row["slot"],
            "price": row["price"], "tier": row["tier"],
        }
        if row["event_exclusive"]:
            item["event_exclusive"] = True
        result.setdefault(row["category"], []).append(item)
    return result


def load_gear_templates(db=None):
    """Same shape as the old GEAR_TEMPLATES literal, plus a "required_level"
    key (Session 8): dict of rarity -> list of
    {"name","slot","set_name","combat_power","required_level"}. Same
    optional-`db` convention as load_barracks_shop() -- read-only, see that
    docstring for why seeding isn't done lazily here. Note these entries
    have no stable id (a fresh item_id is generated per drop instead) --
    the gear_templates table's own id column (slugify(name)_slot_rarity) is
    not part of this returned shape, since the old literal never had one
    either."""
    owns_conn = db is None
    if owns_conn:
        db = _get_db()
    rows = db.execute("SELECT * FROM gear_templates ORDER BY rowid").fetchall()
    if owns_conn:
        db.close()
    result = {}
    for row in rows:
        item = {
            "name": row["name"], "slot": row["slot"],
            "set_name": row["set_name"], "combat_power": row["combat_power"],
            "required_level": row["required_level"],
        }
        result.setdefault(row["rarity"], []).append(item)
    return result


def load_set_bonuses(db=None):
    """Same shape as the old SET_BONUSES literal: dict of
    set_name -> {"pieces_needed", "2pc": {"combat_power_bonus","description"},
    "3pc": {...}, "secret": {"cosmetic_required","combat_power_bonus","description"}}.
    Same optional-`db` convention as load_barracks_shop() -- read-only, see
    that docstring for why seeding isn't done lazily here. Does NOT cover
    COSMETIC_SET_BONUSES, a separate dict literal in app.py with a
    different shape that was not part of this migration."""
    owns_conn = db is None
    if owns_conn:
        db = _get_db()
    rows = db.execute("SELECT * FROM set_bonuses ORDER BY rowid").fetchall()
    if owns_conn:
        db.close()
    result = {}
    for row in rows:
        result[row["set_name"]] = {
            "pieces_needed": row["pieces_needed"],
            "2pc": {"combat_power_bonus": row["bonus_2pc_cp"], "description": row["bonus_2pc_desc"]},
            "3pc": {"combat_power_bonus": row["bonus_3pc_cp"], "description": row["bonus_3pc_desc"]},
            "secret": {
                "cosmetic_required": row["secret_cosmetic_required"],
                "combat_power_bonus": row["secret_cp"],
                "description": row["secret_desc"],
            },
        }
    return result
