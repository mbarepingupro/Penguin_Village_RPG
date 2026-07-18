"""HISTORICAL -- this script's job is done and it can no longer run.

It originally seeded barracks_shop, boutique_items, gear_templates, and
set_bonuses (created in database.py's init_db()) from app.py's BARRACKS_SHOP,
BOUTIQUE_ITEMS, GEAR_TEMPLATES, and SET_BONUSES dict literals, as a verified-
correct foundation before any route switched over to reading from the new
tables. That switchover has since happened (every call site now reads via
catalog.py's load_*() functions instead), and the dict literals this script
depended on were removed from app.py in the same pass -- `import app` here
will succeed (the module still exists), but `appmod.BARRACKS_SHOP` etc. no
longer exist, so migrate() will raise AttributeError if invoked. Kept in the
repo as a record of exactly how the tables were originally seeded, not as a
runnable tool.
"""
import json
import re
import sqlite3

import database
import app as appmod

DATABASE = database.DATABASE


def _slugify(text):
    """Lowercase, non-alphanumeric runs -> single underscore, trimmed."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _gear_template_id(name, slot, rarity):
    """GEAR_TEMPLATES entries have no stable id in app.py (a fresh item_id is
    generated per drop instead) -- derive one as slugify(name)_slot_rarity so
    each row gets a stable, deterministic PK."""
    return f"{_slugify(name)}_{slot}_{rarity}"


def migrate():
    database.init_db()  # ensure the target tables exist, idempotent
    db = sqlite3.connect(DATABASE, timeout=30)

    counts = {}

    # ── barracks_shop ──────────────────────────────────────────────────────
    barracks_rows = 0
    for rarity, items in appmod.BARRACKS_SHOP.items():
        for item in items:
            db.execute(
                "INSERT OR REPLACE INTO barracks_shop "
                "(id, name, slot, rarity, combat_power, cost, event_exclusive) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    item["id"], item["name"], item["slot"], rarity,
                    item["combat_power"], json.dumps(item["cost"]),
                    int(bool(item.get("event_exclusive", False))),
                )
            )
            barracks_rows += 1
    counts["barracks_shop"] = (barracks_rows, sum(len(v) for v in appmod.BARRACKS_SHOP.values()))

    # ── boutique_items ─────────────────────────────────────────────────────
    boutique_rows = 0
    for category, items in appmod.BOUTIQUE_ITEMS.items():
        for item in items:
            db.execute(
                "INSERT OR REPLACE INTO boutique_items "
                "(id, name, category, slot, price, tier, event_exclusive) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    item["id"], item["name"], category, item["slot"],
                    item["price"], item["tier"],
                    int(bool(item.get("event_exclusive", False))),
                )
            )
            boutique_rows += 1
    counts["boutique_items"] = (boutique_rows, sum(len(v) for v in appmod.BOUTIQUE_ITEMS.values()))

    # ── gear_templates ─────────────────────────────────────────────────────
    gear_rows = 0
    for rarity, items in appmod.GEAR_TEMPLATES.items():
        for item in items:
            gid = _gear_template_id(item["name"], item["slot"], rarity)
            db.execute(
                "INSERT OR REPLACE INTO gear_templates "
                "(id, name, slot, rarity, set_name, combat_power) "
                "VALUES (?,?,?,?,?,?)",
                (gid, item["name"], item["slot"], rarity, item["set_name"], item["combat_power"])
            )
            gear_rows += 1
    counts["gear_templates"] = (gear_rows, sum(len(v) for v in appmod.GEAR_TEMPLATES.values()))

    # ── set_bonuses ────────────────────────────────────────────────────────
    set_bonus_rows = 0
    for set_name, sb in appmod.SET_BONUSES.items():
        db.execute(
            "INSERT OR REPLACE INTO set_bonuses "
            "(set_name, pieces_needed, bonus_2pc_cp, bonus_2pc_desc, "
            "bonus_3pc_cp, bonus_3pc_desc, secret_cosmetic_required, secret_cp, secret_desc) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                set_name, sb["pieces_needed"],
                sb["2pc"]["combat_power_bonus"], sb["2pc"]["description"],
                sb["3pc"]["combat_power_bonus"], sb["3pc"]["description"],
                sb["secret"]["cosmetic_required"],
                sb["secret"]["combat_power_bonus"], sb["secret"]["description"],
            )
        )
        set_bonus_rows += 1
    counts["set_bonuses"] = (set_bonus_rows, len(appmod.SET_BONUSES))

    db.commit()

    # ── verify: row count in each table matches the source dict's item count ──
    print("=" * 60)
    print("MIGRATION RESULTS")
    print("=" * 60)
    all_ok = True
    for table, (inserted, source_count) in counts.items():
        db_count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        ok = (db_count == source_count == inserted)
        all_ok = all_ok and ok
        status = "OK" if ok else "MISMATCH"
        print(f"  {table:16s} source={source_count:3d}  inserted={inserted:3d}  "
              f"db_rows={db_count:3d}  [{status}]")
    print("=" * 60)

    db.close()

    if not all_ok:
        raise SystemExit("Row count verification FAILED -- see MISMATCH line(s) above.")
    print("All row counts verified OK.")
    return counts


if __name__ == "__main__":
    migrate()
