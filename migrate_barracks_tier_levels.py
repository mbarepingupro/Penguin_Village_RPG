"""DOUBLY OBSOLETE AND NOW ACTIVELY UNSAFE TO RUN (Session 10) -- do not run
this script. barracks_shop no longer has one required_level per rarity: each
rarity now spans all 5 gear tiers (see catalog.DEFAULT_BARRACKS_SHOP and
database.py's init_db() sync), so this script's old by-rarity
"UPDATE ... WHERE rarity=?" logic would flatten every tier of a rarity back
down to a single required_level, corrupting the tier spread. Left in place,
neutered, only so anyone who still has this filename in muscle memory hits a
clear refusal instead of quietly wrecking the database.

Original docstring (Session 9), already superseded once before this:

SUPERSEDED as a required manual step: this script's own UPDATE logic was
baked directly into database.py's init_db() (runs on every app boot, not
just when someone remembers to run this by hand -- that "someone forgets"
gap is exactly what let barracks_shop stay stuck on flat required_level
values in production after this script was first written). That sync has
since been generalized further (Session 10, see init_db()) to also add
missing tier rows and correct combat_power drift, not just required_level.

Historical context: migrate_gear_tiers.py (the combat-gear-level-tiers
session) added required_level to barracks_shop but set it flat by rarity --
common/uncommon/rare all @1, epic @3, legendary @4 -- treating the whole shop
as Tier 1. Session 9 fixed that to one required_level per rarity (common@1,
uncommon@6, rare@11, epic@18, legendary@24). Session 10 replaced that again
with a full 5-tier spread per rarity (1/6/11/16/21), which is what makes this
script's logic actively wrong now rather than merely redundant.
"""


def migrate():
    raise SystemExit(
        "migrate_barracks_tier_levels.py is obsolete and unsafe to run as of "
        "Session 10 -- it would flatten barracks_shop's per-rarity 5-tier "
        "spread back down to one required_level per rarity. "
        "database.py's init_db() already keeps barracks_shop in sync with "
        "catalog.DEFAULT_BARRACKS_SHOP on every app boot; no manual step is "
        "needed or safe here anymore."
    )


if __name__ == "__main__":
    migrate()
