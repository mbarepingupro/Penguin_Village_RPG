"""One-time DATA migration for Session 8: combat gear level tiers.

Replaces the 4 old combat sets (Frost Guardian, Blood Reaper, Temple Mystic,
Penguin Emperor) with the 26 new tiered sets now baked into catalog.py's
DEFAULT_GEAR_TEMPLATES/DEFAULT_SET_BONUSES, and backfills required_level on
existing barracks_shop rows by rarity. The required_level COLUMN itself is
added additively by database.py's init_db() (_add_col, same pattern as every
other schema addition) -- this script only replaces/updates data, on the
assumption the schema migration already ran (init_db() is called here too,
so running this script alone is enough).

A genuinely fresh database never needs this: database.py seeds straight from
the new DEFAULT_* dicts the first time gear_templates/set_bonuses are empty
(see catalog.py's _seed_*_if_empty). This script is only for a database that
already has the OLD 4-set data from Session 7's original seed (migrate_catalog_
tables.py) sitting in gear_templates/set_bonuses -- that seed guard means
those tables were never empty, so they were never re-seeded automatically.

Idempotent -- safe to run more than once: old rows are deleted by set_name
before insert, new rows use INSERT OR IGNORE (id-based), and the
barracks_shop UPDATE is a plain conditional assignment.

Run with: python migrate_gear_tiers.py
"""
import sqlite3

import catalog
import database

OLD_SET_NAMES = ["Frost Guardian", "Blood Reaper", "Temple Mystic", "Penguin Emperor"]


def migrate():
    database.init_db()  # ensure required_level columns (and the tables themselves) exist
    db = sqlite3.connect(database.DATABASE, timeout=30)

    before_gear = db.execute("SELECT COUNT(*) FROM gear_templates").fetchone()[0]
    before_sb   = db.execute("SELECT COUNT(*) FROM set_bonuses").fetchone()[0]

    placeholders = ",".join("?" for _ in OLD_SET_NAMES)
    db.execute(f"DELETE FROM gear_templates WHERE set_name IN ({placeholders})", OLD_SET_NAMES)
    db.execute(f"DELETE FROM set_bonuses WHERE set_name IN ({placeholders})", OLD_SET_NAMES)

    gear_rows = 0
    for rarity, items in catalog.DEFAULT_GEAR_TEMPLATES.items():
        for item in items:
            gid = f"{catalog._slugify(item['name'])}_{item['slot']}_{rarity}"
            db.execute(
                "INSERT OR IGNORE INTO gear_templates "
                "(id, name, slot, rarity, set_name, combat_power, required_level) "
                "VALUES (?,?,?,?,?,?,?)",
                (gid, item["name"], item["slot"], rarity, item["set_name"],
                 item["combat_power"], item.get("required_level", 1))
            )
            gear_rows += 1

    sb_rows = 0
    for set_name, sb in catalog.DEFAULT_SET_BONUSES.items():
        db.execute(
            "INSERT OR IGNORE INTO set_bonuses "
            "(set_name, pieces_needed, bonus_2pc_cp, bonus_2pc_desc, bonus_3pc_cp, bonus_3pc_desc, "
            "secret_cosmetic_required, secret_cp, secret_desc) VALUES (?,?,?,?,?,?,?,?,?)",
            (set_name, sb["pieces_needed"],
             sb["2pc"]["combat_power_bonus"], sb["2pc"]["description"],
             sb["3pc"]["combat_power_bonus"], sb["3pc"]["description"],
             sb["secret"]["cosmetic_required"], sb["secret"]["combat_power_bonus"], sb["secret"]["description"])
        )
        sb_rows += 1

    db.execute("UPDATE barracks_shop SET required_level=3 WHERE rarity='epic' AND required_level!=3")
    db.execute("UPDATE barracks_shop SET required_level=4 WHERE rarity='legendary' AND required_level!=4")

    db.commit()

    after_gear = db.execute("SELECT COUNT(*) FROM gear_templates").fetchone()[0]
    after_sb   = db.execute("SELECT COUNT(*) FROM set_bonuses").fetchone()[0]
    db.close()

    print("=" * 60)
    print("GEAR TIER MIGRATION RESULTS")
    print("=" * 60)
    print(f"  gear_templates: {before_gear} -> {after_gear} rows "
          f"(deleted {len(OLD_SET_NAMES)} old sets' rows, inserted {gear_rows} new-catalog rows)")
    print(f"  set_bonuses:    {before_sb} -> {after_sb} rows "
          f"(deleted {len(OLD_SET_NAMES)} old sets, inserted {sb_rows} new sets)")
    print("=" * 60)
    # Not a hard assertion on the exact total: a DB with admin-added custom
    # catalog rows (via the Mayor Items tab) beyond the old 4 sets is valid
    # and this migration must not touch those -- so the after-count can
    # legitimately exceed gear_rows/sb_rows. Flag it only if fewer than
    # expected made it in, which would mean an insert silently no-opped.
    if after_gear < gear_rows:
        raise SystemExit(f"Only {after_gear} gear_templates rows present, expected at least {gear_rows}.")
    if after_sb < sb_rows:
        raise SystemExit(f"Only {after_sb} set_bonuses rows present, expected at least {sb_rows}.")
    print("Row counts verified OK.")


if __name__ == "__main__":
    migrate()
