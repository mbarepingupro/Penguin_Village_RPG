"""SUPERSEDED as a required manual step (Session 9): this script's own UPDATE
logic is now baked directly into database.py's init_db() (runs on every
app boot, not just when someone remembers to run this by hand -- that
"someone forgets" gap is exactly what let barracks_shop stay stuck on flat
required_level values in production after this script was first written).
Kept for reference / a one-off manual nudge if ever needed; not required
for correctness anymore.

Original docstring -- one-time DATA migration: spread barracks_shop's
required_level across the 5 gear tiers instead of the old flat per-rarity
gate.

Context: migrate_gear_tiers.py (the combat-gear-level-tiers session) added
required_level to barracks_shop but set it flat by rarity -- common/
uncommon/rare all @1, epic @3, legendary @4 -- treating the whole shop as
Tier 1. That undersold barracks_shop's own progression: each material
family (iron/driftwood, steel/coral, crystal/aurora, obsidian, mythril) is
pinned to exactly one rarity, so it maps 1:1 onto one of the 5 gear tiers
the same way gear_templates' 26 sets do. This script re-derives the correct
values from catalog.py's updated _BARRACKS_REQUIRED_LEVEL (the live source
of truth _seed_barracks_shop_if_empty now seeds a fresh DB with):
    common    (iron/driftwood)  -> Tier 1 required_level 1
    uncommon  (steel/coral)     -> Tier 2 required_level 6
    rare      (crystal/aurora)  -> Tier 3 required_level 11
    epic      (obsidian)        -> Tier 4 required_level 18
    legendary (mythril)         -> Tier 5 required_level 24

gear_templates is untouched -- its 4 standalone (set_name IS NULL) rows
already had the correct required_level=1 (they're common-only, no tier
spread applies) and were never part of this gap.

A genuinely fresh database never needs this: catalog.py's
_seed_barracks_shop_if_empty() seeds straight from the corrected
_BARRACKS_REQUIRED_LEVEL the first time barracks_shop is empty. This script
is only for a database that already has the OLD flat values seeded (that
seed guard means barracks_shop was never re-seeded automatically).

Idempotent -- safe to run more than once: each UPDATE is a plain
by-rarity assignment.

Run with: python migrate_barracks_tier_levels.py
"""
import sqlite3

import catalog
import database


def migrate():
    database.init_db()  # ensure required_level column (and the table itself) exists
    db = sqlite3.connect(database.DATABASE, timeout=30)
    db.row_factory = sqlite3.Row

    updated = 0
    for rarity, required_level in catalog._BARRACKS_REQUIRED_LEVEL.items():
        cur = db.execute(
            "UPDATE barracks_shop SET required_level=? WHERE rarity=? AND required_level!=?",
            (required_level, rarity, required_level)
        )
        updated += cur.rowcount

    db.commit()

    print("=" * 60)
    print("BARRACKS TIER-LEVEL MIGRATION RESULTS")
    print("=" * 60)
    print(f"  rows changed: {updated}")
    for rarity, required_level in catalog._BARRACKS_REQUIRED_LEVEL.items():
        rows = db.execute(
            "SELECT id, required_level FROM barracks_shop WHERE rarity=? ORDER BY id", (rarity,)
        ).fetchall()
        ok = all(r["required_level"] == required_level for r in rows)
        print(f"  {rarity:10s} -> required_level={required_level:2d}  "
              f"({len(rows)} rows)  [{'OK' if ok else 'MISMATCH'}]")
        if not ok:
            db.close()
            raise SystemExit(f"Not all {rarity} rows ended up at required_level={required_level}.")
    print("=" * 60)
    db.close()
    print("All rows verified OK.")


if __name__ == "__main__":
    migrate()
