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

# barracks_shop now mirrors gear_templates' 5-tier ladder (Session 10):
# each of the 5 rarities gets a distinct, standalone (no set_name --
# barracks_buy() always writes NULL, same as epic/legendary already did) item
# family at EACH of gear_templates' 5 tier floors (_BARRACKS_TIER_LEVELS
# below == the same 1/6/11/16/21 required_level schedule Frost/Blood/Storm/
# Sea Lion/Temple use), not just the one tier its rarity used to be pinned
# to. That's 5 tiers x 5 rarities x 4 slots = 100 tier-ladder items, plus the
# 12 untouched cosmetic alternatives (driftwood/coral/aurora) below, = 112
# rows total in the table (vs. the old 32: 5 families x 4 slots, minus epic/
# legendary never having an alt pair).
#
# Before this pass, only ONE tier per rarity existed here (common@1,
# uncommon@6, rare@11, epic@18, legendary@24 -- the last two were a stepped-
# up position within their tier, not the tier's own floor), so e.g. a
# level-20 player could only ever forge legendary gear once they hit 24, with
# nothing new to forge in their own bracket in the meantime. Now every
# bracket has a full common->legendary spread to forge from, same as drops.
#
# combat_power is now IDENTICAL to the equivalent DEFAULT_GEAR_TEMPLATES
# rarity+slot piece for every item here (common 3/2/2/3, uncommon 7/5/5/7,
# rare 15/12/11/14, epic 28/22/20/25, legendary 45/35/32/42 -- weapon/helmet/
# boots/armor) -- so forged gear is never strictly better or worse than an
# equivalent drop. epic/legendary already matched (see the old design note,
# preserved below); common/uncommon/rare's PRE-EXISTING iron/steel/crystal
# items (and their cosmetic alt pairs) get their combat_power corrected down
# to match here too, closing a pre-existing mismatch (iron/steel/crystal
# were 1 CP above their template equivalents on every slot). Non-retroactive:
# combat_power is copied onto each `gear` row at forge time (barracks_buy()),
# not looked up live, so already-forged/equipped copies of these items keep
# whatever CP they were forged with -- only future forges see the correction.
#
# cost scales up with BOTH rarity (unchanged from before -- the existing
# ~2.5-3x per-rarity gold/resource growth) AND tier now (~1.3x per tier
# step within a rarity, anchored so each rarity's pre-existing tier's cost is
# untouched and the other 4 tiers scale off of it). ice_blocks, previously
# only on epic/legendary's single existing tier, now appears on all 5 tiers
# of BOTH those rarities (10 items instead of 2) -- extending the Session 7
# resource-diversification precedent rather than introducing it fresh to
# rarities that never had it.
#
# New tier names follow the existing one-material-name-per-rarity convention
# (Iron/Steel/Crystal/Obsidian/Mythril) but are new names distinct from both
# those and every DEFAULT_GEAR_TEMPLATES set name (Icicle/Bone/Squall/Pup/
# Acolyte etc. are taken): common adds Copper/Bronze/Slate/Basalt, uncommon
# adds Tin/Cobalt/Nickel/Wolfram, rare adds Quartz/Garnet/Topaz/Opal, epic
# adds Onyx/Jade/Amethyst/Sapphire, legendary adds Adamant/Platinum/Titanium/
# Orichalcum.
#
# IMPORTANT: existing/already-deployed databases don't get this from
# DEFAULT_BARRACKS_SHOP alone -- _seed_barracks_shop_if_empty only runs
# against a genuinely empty table. See database.py's init_db() for the
# unconditional-every-boot sync that inserts the missing rows and corrects
# the pre-existing ones' combat_power/required_level on an already-seeded
# database, the same PR #256/Session 9 lesson the old per-rarity sync used to
# teach (a *manual* migration script -- see migrate_barracks_tier_levels.py,
# now doubly obsolete and neutered -- is not enough; someone has to remember
# to run it, and in practice never did).
_BARRACKS_TIER_LEVELS = [1, 6, 11, 16, 21]

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
# `if not os.path.exists(item_path): continue` skip). No alt pair exists for
# epic/legendary (never did, and this pass doesn't add one -- out of scope).
DEFAULT_BARRACKS_SHOP = {
    "common": [
        # Tier 1 (lvl 1) -- Iron
        {"id": "iron_sword", "name": "Iron Sword", "slot": "weapon", "combat_power": 3, "cost": {"gold": 200, "bones": 50}, "required_level": 1},
        {"id": "iron_helmet", "name": "Iron Helmet", "slot": "helmet", "combat_power": 2, "cost": {"gold": 200, "bones": 40}, "required_level": 1},
        {"id": "iron_boots", "name": "Iron Boots", "slot": "boots", "combat_power": 2, "cost": {"gold": 150, "bones": 30}, "required_level": 1},
        {"id": "iron_plate", "name": "Iron Plate", "slot": "armor", "combat_power": 3, "cost": {"gold": 250, "bones": 60}, "required_level": 1},
        # Tier 2 (lvl 6) -- Copper
        {"id": "copper_axe", "name": "Copper Axe", "slot": "weapon", "combat_power": 3, "cost": {"gold": 250, "bones": 70}, "required_level": 6},
        {"id": "copper_cap", "name": "Copper Cap", "slot": "helmet", "combat_power": 2, "cost": {"gold": 250, "bones": 50}, "required_level": 6},
        {"id": "copper_sandals", "name": "Copper Sandals", "slot": "boots", "combat_power": 2, "cost": {"gold": 200, "bones": 40}, "required_level": 6},
        {"id": "copper_vest", "name": "Copper Vest", "slot": "armor", "combat_power": 3, "cost": {"gold": 325, "bones": 80}, "required_level": 6},
        # Tier 3 (lvl 11) -- Bronze
        {"id": "bronze_club", "name": "Bronze Club", "slot": "weapon", "combat_power": 3, "cost": {"gold": 300, "bones": 80}, "required_level": 11},
        {"id": "bronze_helm", "name": "Bronze Helm", "slot": "helmet", "combat_power": 2, "cost": {"gold": 300, "bones": 60}, "required_level": 11},
        {"id": "bronze_boots", "name": "Bronze Boots", "slot": "boots", "combat_power": 2, "cost": {"gold": 225, "bones": 45}, "required_level": 11},
        {"id": "bronze_guard", "name": "Bronze Guard", "slot": "armor", "combat_power": 3, "cost": {"gold": 375, "bones": 90}, "required_level": 11},
        # Tier 4 (lvl 16) -- Slate
        {"id": "slate_mace", "name": "Slate Mace", "slot": "weapon", "combat_power": 3, "cost": {"gold": 400, "bones": 100}, "required_level": 16},
        {"id": "slate_hood", "name": "Slate Hood", "slot": "helmet", "combat_power": 2, "cost": {"gold": 400, "bones": 80}, "required_level": 16},
        {"id": "slate_treads", "name": "Slate Treads", "slot": "boots", "combat_power": 2, "cost": {"gold": 300, "bones": 60}, "required_level": 16},
        {"id": "slate_plate", "name": "Slate Plate", "slot": "armor", "combat_power": 3, "cost": {"gold": 500, "bones": 120}, "required_level": 16},
        # Tier 5 (lvl 21) -- Basalt
        {"id": "basalt_hatchet", "name": "Basalt Hatchet", "slot": "weapon", "combat_power": 3, "cost": {"gold": 525, "bones": 130}, "required_level": 21},
        {"id": "basalt_cap", "name": "Basalt Cap", "slot": "helmet", "combat_power": 2, "cost": {"gold": 525, "bones": 100}, "required_level": 21},
        {"id": "basalt_boots", "name": "Basalt Boots", "slot": "boots", "combat_power": 2, "cost": {"gold": 400, "bones": 80}, "required_level": 21},
        {"id": "basalt_armor", "name": "Basalt Armor", "slot": "armor", "combat_power": 3, "cost": {"gold": 650, "bones": 160}, "required_level": 21},
        # Cosmetic alternative (same tier/CP as Iron, different theme) -- Driftwood
        {"id": "driftwood_club", "name": "Driftwood Club", "slot": "weapon", "combat_power": 3, "cost": {"gold": 200, "fish": 125}, "required_level": 1},
        {"id": "driftwood_cap", "name": "Driftwood Cap", "slot": "helmet", "combat_power": 2, "cost": {"gold": 200, "herbs": 100}, "required_level": 1},
        {"id": "driftwood_sandals", "name": "Driftwood Sandals", "slot": "boots", "combat_power": 2, "cost": {"gold": 150, "fish": 75}, "required_level": 1},
        {"id": "driftwood_vest", "name": "Driftwood Vest", "slot": "armor", "combat_power": 3, "cost": {"gold": 250, "herbs": 150}, "required_level": 1},
    ],
    "uncommon": [
        # Tier 1 (lvl 1) -- Tin
        {"id": "tin_rapier", "name": "Tin Rapier", "slot": "weapon", "combat_power": 7, "cost": {"gold": 375, "bones": 80, "blood_gems": 15}, "required_level": 1},
        {"id": "tin_cap", "name": "Tin Cap", "slot": "helmet", "combat_power": 5, "cost": {"gold": 375, "bones": 60, "blood_gems": 10}, "required_level": 1},
        {"id": "tin_boots", "name": "Tin Boots", "slot": "boots", "combat_power": 5, "cost": {"gold": 300, "bones": 50, "blood_gems": 10}, "required_level": 1},
        {"id": "tin_vest", "name": "Tin Vest", "slot": "armor", "combat_power": 7, "cost": {"gold": 450, "bones": 90, "blood_gems": 20}, "required_level": 1},
        # Tier 2 (lvl 6) -- Steel
        {"id": "steel_sword", "name": "Steel Sword", "slot": "weapon", "combat_power": 7, "cost": {"gold": 500, "bones": 100, "blood_gems": 20}, "required_level": 6},
        {"id": "steel_helmet", "name": "Steel Helmet", "slot": "helmet", "combat_power": 5, "cost": {"gold": 500, "bones": 80, "blood_gems": 15}, "required_level": 6},
        {"id": "steel_boots", "name": "Steel Boots", "slot": "boots", "combat_power": 5, "cost": {"gold": 400, "bones": 70, "blood_gems": 15}, "required_level": 6},
        {"id": "steel_plate", "name": "Steel Plate", "slot": "armor", "combat_power": 7, "cost": {"gold": 600, "bones": 120, "blood_gems": 25}, "required_level": 6},
        # Tier 3 (lvl 11) -- Cobalt
        {"id": "cobalt_axe", "name": "Cobalt Axe", "slot": "weapon", "combat_power": 7, "cost": {"gold": 600, "bones": 120, "blood_gems": 25}, "required_level": 11},
        {"id": "cobalt_helm", "name": "Cobalt Helm", "slot": "helmet", "combat_power": 5, "cost": {"gold": 600, "bones": 90, "blood_gems": 20}, "required_level": 11},
        {"id": "cobalt_greaves", "name": "Cobalt Greaves", "slot": "boots", "combat_power": 5, "cost": {"gold": 475, "bones": 80, "blood_gems": 20}, "required_level": 11},
        {"id": "cobalt_plate", "name": "Cobalt Plate", "slot": "armor", "combat_power": 7, "cost": {"gold": 700, "bones": 140, "blood_gems": 30}, "required_level": 11},
        # Tier 4 (lvl 16) -- Nickel
        {"id": "nickel_mace", "name": "Nickel Mace", "slot": "weapon", "combat_power": 7, "cost": {"gold": 775, "bones": 150, "blood_gems": 30}, "required_level": 16},
        {"id": "nickel_crown", "name": "Nickel Crown", "slot": "helmet", "combat_power": 5, "cost": {"gold": 775, "bones": 120, "blood_gems": 25}, "required_level": 16},
        {"id": "nickel_sandals", "name": "Nickel Sandals", "slot": "boots", "combat_power": 5, "cost": {"gold": 600, "bones": 110, "blood_gems": 25}, "required_level": 16},
        {"id": "nickel_guard", "name": "Nickel Guard", "slot": "armor", "combat_power": 7, "cost": {"gold": 925, "bones": 180, "blood_gems": 40}, "required_level": 16},
        # Tier 5 (lvl 21) -- Wolfram
        {"id": "wolfram_blade", "name": "Wolfram Blade", "slot": "weapon", "combat_power": 7, "cost": {"gold": 1000, "bones": 200, "blood_gems": 40}, "required_level": 21},
        {"id": "wolfram_visor", "name": "Wolfram Visor", "slot": "helmet", "combat_power": 5, "cost": {"gold": 1000, "bones": 160, "blood_gems": 30}, "required_level": 21},
        {"id": "wolfram_treads", "name": "Wolfram Treads", "slot": "boots", "combat_power": 5, "cost": {"gold": 800, "bones": 140, "blood_gems": 30}, "required_level": 21},
        {"id": "wolfram_armor", "name": "Wolfram Armor", "slot": "armor", "combat_power": 7, "cost": {"gold": 1200, "bones": 250, "blood_gems": 50}, "required_level": 21},
        # Cosmetic alternative (same tier/CP as Tin, different theme) -- Coral
        {"id": "coral_blade", "name": "Coral Blade", "slot": "weapon", "combat_power": 7, "cost": {"gold": 500, "fish": 250, "blood_gems": 20}, "required_level": 6},
        {"id": "coral_helm", "name": "Coral Helm", "slot": "helmet", "combat_power": 5, "cost": {"gold": 500, "herbs": 200, "blood_gems": 15}, "required_level": 6},
        {"id": "coral_boots", "name": "Coral Boots", "slot": "boots", "combat_power": 5, "cost": {"gold": 400, "fish": 175, "blood_gems": 15}, "required_level": 6},
        {"id": "coral_guard", "name": "Coral Guard", "slot": "armor", "combat_power": 7, "cost": {"gold": 600, "herbs": 300, "blood_gems": 25}, "required_level": 6},
    ],
    "rare": [
        # Tier 1 (lvl 1) -- Quartz
        {"id": "quartz_rapier", "name": "Quartz Rapier", "slot": "weapon", "combat_power": 15, "cost": {"gold": 975, "blood_gems": 50, "spell_fragments": 25}, "required_level": 1},
        {"id": "quartz_circlet", "name": "Quartz Circlet", "slot": "helmet", "combat_power": 12, "cost": {"gold": 775, "blood_gems": 40, "spell_fragments": 20}, "required_level": 1},
        {"id": "quartz_boots", "name": "Quartz Boots", "slot": "boots", "combat_power": 11, "cost": {"gold": 650, "blood_gems": 30, "spell_fragments": 15}, "required_level": 1},
        {"id": "quartz_vest", "name": "Quartz Vest", "slot": "armor", "combat_power": 14, "cost": {"gold": 1150, "blood_gems": 60, "spell_fragments": 30}, "required_level": 1},
        # Tier 2 (lvl 6) -- Garnet
        {"id": "garnet_scythe", "name": "Garnet Scythe", "slot": "weapon", "combat_power": 15, "cost": {"gold": 1300, "blood_gems": 70, "spell_fragments": 35}, "required_level": 6},
        {"id": "garnet_crown", "name": "Garnet Crown", "slot": "helmet", "combat_power": 12, "cost": {"gold": 1000, "blood_gems": 50, "spell_fragments": 25}, "required_level": 6},
        {"id": "garnet_greaves", "name": "Garnet Greaves", "slot": "boots", "combat_power": 11, "cost": {"gold": 850, "blood_gems": 40, "spell_fragments": 20}, "required_level": 6},
        {"id": "garnet_plate", "name": "Garnet Plate", "slot": "armor", "combat_power": 14, "cost": {"gold": 1550, "blood_gems": 80, "spell_fragments": 40}, "required_level": 6},
        # Tier 3 (lvl 11) -- Crystal
        {"id": "crystal_blade", "name": "Crystal Blade", "slot": "weapon", "combat_power": 15, "cost": {"gold": 1500, "blood_gems": 80, "spell_fragments": 40}, "required_level": 11},
        {"id": "crystal_crown", "name": "Crystal Crown", "slot": "helmet", "combat_power": 12, "cost": {"gold": 1200, "blood_gems": 60, "spell_fragments": 30}, "required_level": 11},
        {"id": "crystal_greaves", "name": "Crystal Greaves", "slot": "boots", "combat_power": 11, "cost": {"gold": 1000, "blood_gems": 50, "spell_fragments": 25}, "required_level": 11},
        {"id": "crystal_armor", "name": "Crystal Armor", "slot": "armor", "combat_power": 14, "cost": {"gold": 1800, "blood_gems": 100, "spell_fragments": 50}, "required_level": 11},
        # Tier 4 (lvl 16) -- Topaz
        {"id": "topaz_saber", "name": "Topaz Saber", "slot": "weapon", "combat_power": 15, "cost": {"gold": 1950, "blood_gems": 100, "spell_fragments": 50}, "required_level": 16},
        {"id": "topaz_diadem", "name": "Topaz Diadem", "slot": "helmet", "combat_power": 12, "cost": {"gold": 1550, "blood_gems": 80, "spell_fragments": 40}, "required_level": 16},
        {"id": "topaz_treads", "name": "Topaz Treads", "slot": "boots", "combat_power": 11, "cost": {"gold": 1300, "blood_gems": 60, "spell_fragments": 30}, "required_level": 16},
        {"id": "topaz_guard", "name": "Topaz Guard", "slot": "armor", "combat_power": 14, "cost": {"gold": 2350, "blood_gems": 130, "spell_fragments": 60}, "required_level": 16},
        # Tier 5 (lvl 21) -- Opal
        {"id": "opal_staff", "name": "Opal Staff", "slot": "weapon", "combat_power": 15, "cost": {"gold": 2550, "blood_gems": 140, "spell_fragments": 70}, "required_level": 21},
        {"id": "opal_halo", "name": "Opal Halo", "slot": "helmet", "combat_power": 12, "cost": {"gold": 2050, "blood_gems": 100, "spell_fragments": 50}, "required_level": 21},
        {"id": "opal_sandals", "name": "Opal Sandals", "slot": "boots", "combat_power": 11, "cost": {"gold": 1700, "blood_gems": 80, "spell_fragments": 40}, "required_level": 21},
        {"id": "opal_robes", "name": "Opal Robes", "slot": "armor", "combat_power": 14, "cost": {"gold": 3050, "blood_gems": 170, "spell_fragments": 80}, "required_level": 21},
        # Cosmetic alternative (same tier/CP as Quartz, different theme) -- Aurora
        {"id": "aurora_blade", "name": "Aurora Blade", "slot": "weapon", "combat_power": 15, "cost": {"gold": 1500, "fish": 200, "spell_fragments": 40}, "required_level": 11},
        {"id": "aurora_diadem", "name": "Aurora Diadem", "slot": "helmet", "combat_power": 12, "cost": {"gold": 1200, "herbs": 150, "spell_fragments": 30}, "required_level": 11},
        {"id": "aurora_boots", "name": "Aurora Boots", "slot": "boots", "combat_power": 11, "cost": {"gold": 1000, "fish": 125, "spell_fragments": 25}, "required_level": 11},
        {"id": "aurora_mail", "name": "Aurora Mail", "slot": "armor", "combat_power": 14, "cost": {"gold": 1800, "herbs": 250, "spell_fragments": 50}, "required_level": 11},
    ],
    "epic": [
        # Tier 1 (lvl 1) -- Onyx
        {"id": "onyx_reaver", "name": "Onyx Reaver", "slot": "weapon", "combat_power": 28, "cost": {"gold": 2000, "blood_gems": 90, "spell_fragments": 40, "fish": 15, "ice_blocks": 90}, "required_level": 1},
        {"id": "onyx_skull", "name": "Onyx Skull", "slot": "helmet", "combat_power": 22, "cost": {"gold": 1600, "blood_gems": 60, "spell_fragments": 30, "herbs": 10, "ice_blocks": 70}, "required_level": 1},
        {"id": "onyx_talons", "name": "Onyx Talons", "slot": "boots", "combat_power": 20, "cost": {"gold": 1350, "blood_gems": 50, "spell_fragments": 25, "fish": 10, "ice_blocks": 60}, "required_level": 1},
        {"id": "onyx_bastion", "name": "Onyx Bastion", "slot": "armor", "combat_power": 25, "cost": {"gold": 2400, "blood_gems": 110, "spell_fragments": 50, "herbs": 15, "ice_blocks": 110}, "required_level": 1},
        # Tier 2 (lvl 6) -- Jade
        {"id": "jade_fang", "name": "Jade Fang", "slot": "weapon", "combat_power": 28, "cost": {"gold": 2600, "blood_gems": 120, "spell_fragments": 50, "fish": 20, "ice_blocks": 120}, "required_level": 6},
        {"id": "jade_coronet", "name": "Jade Coronet", "slot": "helmet", "combat_power": 22, "cost": {"gold": 2100, "blood_gems": 80, "spell_fragments": 40, "herbs": 15, "ice_blocks": 90}, "required_level": 6},
        {"id": "jade_striders", "name": "Jade Striders", "slot": "boots", "combat_power": 20, "cost": {"gold": 1750, "blood_gems": 70, "spell_fragments": 35, "fish": 10, "ice_blocks": 70}, "required_level": 6},
        {"id": "jade_cuirass", "name": "Jade Cuirass", "slot": "armor", "combat_power": 25, "cost": {"gold": 3150, "blood_gems": 140, "spell_fragments": 70, "herbs": 20, "ice_blocks": 150}, "required_level": 6},
        # Tier 3 (lvl 11) -- Amethyst
        {"id": "amethyst_wand", "name": "Amethyst Wand", "slot": "weapon", "combat_power": 28, "cost": {"gold": 3100, "blood_gems": 140, "spell_fragments": 60, "fish": 20, "ice_blocks": 140}, "required_level": 11},
        {"id": "amethyst_circlet", "name": "Amethyst Circlet", "slot": "helmet", "combat_power": 22, "cost": {"gold": 2450, "blood_gems": 100, "spell_fragments": 45, "herbs": 15, "ice_blocks": 100}, "required_level": 11},
        {"id": "amethyst_sandals", "name": "Amethyst Sandals", "slot": "boots", "combat_power": 20, "cost": {"gold": 2100, "blood_gems": 80, "spell_fragments": 40, "fish": 15, "ice_blocks": 90}, "required_level": 11},
        {"id": "amethyst_robes", "name": "Amethyst Robes", "slot": "armor", "combat_power": 25, "cost": {"gold": 3700, "blood_gems": 170, "spell_fragments": 80, "herbs": 25, "ice_blocks": 170}, "required_level": 11},
        # Tier 4 (lvl 16) -- Obsidian
        {"id": "obsidian_blade", "name": "Obsidian Blade", "slot": "weapon", "combat_power": 28, "cost": {"gold": 4000, "blood_gems": 176, "spell_fragments": 82, "fish": 28, "ice_blocks": 185}, "required_level": 16},
        {"id": "obsidian_crest", "name": "Obsidian Crest", "slot": "helmet", "combat_power": 22, "cost": {"gold": 3200, "blood_gems": 128, "spell_fragments": 60, "herbs": 20, "ice_blocks": 134}, "required_level": 16},
        {"id": "obsidian_greaves", "name": "Obsidian Greaves", "slot": "boots", "combat_power": 20, "cost": {"gold": 2700, "blood_gems": 108, "spell_fragments": 52, "fish": 18, "ice_blocks": 113}, "required_level": 16},
        {"id": "obsidian_plate", "name": "Obsidian Plate", "slot": "armor", "combat_power": 25, "cost": {"gold": 4800, "blood_gems": 216, "spell_fragments": 101, "herbs": 34, "ice_blocks": 227}, "required_level": 16},
        # Tier 5 (lvl 21) -- Sapphire
        {"id": "sapphire_trident", "name": "Sapphire Trident", "slot": "weapon", "combat_power": 28, "cost": {"gold": 5200, "blood_gems": 225, "spell_fragments": 110, "fish": 35, "ice_blocks": 250}, "required_level": 21},
        {"id": "sapphire_tiara", "name": "Sapphire Tiara", "slot": "helmet", "combat_power": 22, "cost": {"gold": 4200, "blood_gems": 170, "spell_fragments": 80, "herbs": 25, "ice_blocks": 180}, "required_level": 21},
        {"id": "sapphire_sabatons", "name": "Sapphire Sabatons", "slot": "boots", "combat_power": 20, "cost": {"gold": 3550, "blood_gems": 140, "spell_fragments": 70, "fish": 25, "ice_blocks": 150}, "required_level": 21},
        {"id": "sapphire_aegis", "name": "Sapphire Aegis", "slot": "armor", "combat_power": 25, "cost": {"gold": 6300, "blood_gems": 275, "spell_fragments": 130, "herbs": 45, "ice_blocks": 300}, "required_level": 21},
    ],
    "legendary": [
        # Tier 1 (lvl 1) -- Adamant
        {"id": "adamant_warhammer", "name": "Adamant Warhammer", "slot": "weapon", "combat_power": 45, "cost": {"gold": 4200, "blood_gems": 180, "spell_fragments": 90, "fish": 30, "ice_blocks": 190}, "required_level": 1},
        {"id": "adamant_casque", "name": "Adamant Casque", "slot": "helmet", "combat_power": 35, "cost": {"gold": 3300, "blood_gems": 130, "spell_fragments": 60, "herbs": 20, "ice_blocks": 140}, "required_level": 1},
        {"id": "adamant_greaves", "name": "Adamant Greaves", "slot": "boots", "combat_power": 32, "cost": {"gold": 2800, "blood_gems": 110, "spell_fragments": 50, "fish": 20, "ice_blocks": 120}, "required_level": 1},
        {"id": "adamant_bulwark", "name": "Adamant Bulwark", "slot": "armor", "combat_power": 42, "cost": {"gold": 4950, "blood_gems": 225, "spell_fragments": 100, "herbs": 35, "ice_blocks": 225}, "required_level": 1},
        # Tier 2 (lvl 6) -- Platinum
        {"id": "platinum_rapier", "name": "Platinum Rapier", "slot": "weapon", "combat_power": 45, "cost": {"gold": 5500, "blood_gems": 250, "spell_fragments": 110, "fish": 40, "ice_blocks": 250}, "required_level": 6},
        {"id": "platinum_halo", "name": "Platinum Halo", "slot": "helmet", "combat_power": 35, "cost": {"gold": 4300, "blood_gems": 170, "spell_fragments": 80, "herbs": 30, "ice_blocks": 180}, "required_level": 6},
        {"id": "platinum_striders", "name": "Platinum Striders", "slot": "boots", "combat_power": 32, "cost": {"gold": 3650, "blood_gems": 150, "spell_fragments": 70, "fish": 25, "ice_blocks": 150}, "required_level": 6},
        {"id": "platinum_plate", "name": "Platinum Plate", "slot": "armor", "combat_power": 42, "cost": {"gold": 6500, "blood_gems": 300, "spell_fragments": 140, "herbs": 45, "ice_blocks": 300}, "required_level": 6},
        # Tier 3 (lvl 11) -- Titanium
        {"id": "titanium_cleaver", "name": "Titanium Cleaver", "slot": "weapon", "combat_power": 45, "cost": {"gold": 6500, "blood_gems": 275, "spell_fragments": 130, "fish": 45, "ice_blocks": 300}, "required_level": 11},
        {"id": "titanium_visor", "name": "Titanium Visor", "slot": "helmet", "combat_power": 35, "cost": {"gold": 5100, "blood_gems": 200, "spell_fragments": 100, "herbs": 30, "ice_blocks": 200}, "required_level": 11},
        {"id": "titanium_sabatons", "name": "Titanium Sabatons", "slot": "boots", "combat_power": 32, "cost": {"gold": 4300, "blood_gems": 170, "spell_fragments": 80, "fish": 30, "ice_blocks": 180}, "required_level": 11},
        {"id": "titanium_aegis", "name": "Titanium Aegis", "slot": "armor", "combat_power": 42, "cost": {"gold": 7600, "blood_gems": 350, "spell_fragments": 160, "herbs": 50, "ice_blocks": 350}, "required_level": 11},
        # Tier 4 (lvl 16) -- Orichalcum
        {"id": "orichalcum_spear", "name": "Orichalcum Spear", "slot": "weapon", "combat_power": 45, "cost": {"gold": 8400, "blood_gems": 375, "spell_fragments": 170, "fish": 60, "ice_blocks": 375}, "required_level": 16},
        {"id": "orichalcum_diadem", "name": "Orichalcum Diadem", "slot": "helmet", "combat_power": 35, "cost": {"gold": 6600, "blood_gems": 275, "spell_fragments": 130, "herbs": 40, "ice_blocks": 275}, "required_level": 16},
        {"id": "orichalcum_sandals", "name": "Orichalcum Sandals", "slot": "boots", "combat_power": 32, "cost": {"gold": 5600, "blood_gems": 225, "spell_fragments": 110, "fish": 35, "ice_blocks": 225}, "required_level": 16},
        {"id": "orichalcum_regalia", "name": "Orichalcum Regalia", "slot": "armor", "combat_power": 42, "cost": {"gold": 9900, "blood_gems": 450, "spell_fragments": 200, "herbs": 70, "ice_blocks": 475}, "required_level": 16},
        # Tier 5 (lvl 21) -- Mythril
        {"id": "mythril_blade", "name": "Mythril Blade", "slot": "weapon", "combat_power": 45, "cost": {"gold": 11000, "blood_gems": 480, "spell_fragments": 225, "fish": 75, "ice_blocks": 504}, "required_level": 21},
        {"id": "mythril_diadem", "name": "Mythril Diadem", "slot": "helmet", "combat_power": 35, "cost": {"gold": 8600, "blood_gems": 344, "spell_fragments": 165, "herbs": 55, "ice_blocks": 361}, "required_level": 21},
        {"id": "mythril_sabatons", "name": "Mythril Sabatons", "slot": "boots", "combat_power": 32, "cost": {"gold": 7300, "blood_gems": 292, "spell_fragments": 142, "fish": 48, "ice_blocks": 307}, "required_level": 21},
        {"id": "mythril_plate", "name": "Mythril Plate", "slot": "armor", "combat_power": 42, "cost": {"gold": 13000, "blood_gems": 584, "spell_fragments": 274, "herbs": 91, "ice_blocks": 613}, "required_level": 21},
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
    # required_level now lives on each item itself (a rarity spans all 5
    # tiers, not just one), unlike the old single _BARRACKS_REQUIRED_LEVEL-
    # per-rarity lookup this replaced.
    for rarity, items in DEFAULT_BARRACKS_SHOP.items():
        for item in items:
            db.execute(
                "INSERT OR IGNORE INTO barracks_shop (id, name, slot, rarity, combat_power, cost, event_exclusive, required_level) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (item["id"], item["name"], item["slot"], rarity, item["combat_power"],
                 json.dumps(item["cost"]), int(bool(item.get("event_exclusive", False))),
                 item["required_level"])
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
