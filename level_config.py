LEVEL_DATA = {
    1:  {"gathering_bonus": 0,   "reward": None},
    2:  {"gathering_bonus": 5,   "reward": None},
    3:  {"gathering_bonus": 5,   "reward": {"cosmetics": ["Basic Scarf"], "title": "Newcomer"}},
    4:  {"gathering_bonus": 5,   "reward": None},
    5:  {"gathering_bonus": 5,   "reward": {"cosmetics": ["Wooden Bucket Hat"], "gold": 100}},
    6:  {"gathering_bonus": 5,   "reward": None},
    7:  {"gathering_bonus": 5,   "reward": {"cosmetics": ["Striped Socks"], "title": "Settler"}},
    8:  {"gathering_bonus": 5,   "reward": None},
    9:  {"gathering_bonus": 5,   "reward": {"cosmetics": ["Lantern Accessory"]}},
    10: {"gathering_bonus": 5,   "reward": {"cosmetics": ["Village Bandana", "Golden Scarf"], "title": "Villager", "gold": 1000, "max_energy": 20}, "big_milestone": True},
    11: {"gathering_bonus": 5,   "reward": None},
    12: {"gathering_bonus": 5,   "reward": {"cosmetics": ["Adventurer's Cape"]}},
    13: {"gathering_bonus": 5,   "reward": None},
    14: {"gathering_bonus": 5,   "reward": {"cosmetics": ["Explorer's Goggles"], "title": "Explorer"}},
    15: {"gathering_bonus": 5,   "reward": {"cosmetics": ["Crystal Pendant"], "gold": 500}},
    16: {"gathering_bonus": 5,   "reward": None},
    17: {"gathering_bonus": 5,   "reward": {"cosmetics": ["Cozy Sneakers"]}},
    18: {"gathering_bonus": 5,   "reward": None},
    19: {"gathering_bonus": 5,   "reward": {"cosmetics": ["Feathered Hat"], "title": "Pathfinder"}},
    20: {"gathering_bonus": 5,   "reward": {"cosmetics": ["Royal Cape", "Mayor's Apprentice Hat"], "title": "Veteran", "gold": 3000, "max_energy": 20}, "big_milestone": True},
    21: {"gathering_bonus": 5,   "reward": None},
    22: {"gathering_bonus": 5,   "reward": {"cosmetics": ["Shadow Cloak"]}},
    23: {"gathering_bonus": 5,   "reward": None},
    24: {"gathering_bonus": 5,   "reward": {"cosmetics": ["Ancient Amulet"], "title": "Sage"}},
    25: {"gathering_bonus": 5,   "reward": {"cosmetics": ["Fluffy Slippers"], "gold": 1000}},
    26: {"gathering_bonus": 5,   "reward": None},
    27: {"gathering_bonus": 5,   "reward": {"cosmetics": ["Starlight Scarf"]}},
    28: {"gathering_bonus": 5,   "reward": None},
    29: {"gathering_bonus": 5,   "reward": {"cosmetics": ["Phoenix Feather"], "title": "Elder"}},
    30: {"gathering_bonus": 5,   "reward": {"cosmetics": ["Prestige Crown", "Emperor's Cape"], "title": "Legend", "gold": 5000, "max_energy": 20, "prestige_unlock": True}, "big_milestone": True},
}


def get_total_gathering_bonus(level):
    """Returns total cumulative gathering bonus % for a given level."""
    total = 0
    for lvl in range(1, level + 1):
        total += LEVEL_DATA.get(lvl, {}).get("gathering_bonus", 0)
    return total


def get_next_milestone(level):
    """Returns (next_level, level_data) for the next level that has a reward."""
    for lvl in range(level + 1, 31):
        if LEVEL_DATA.get(lvl, {}).get("reward"):
            return lvl, LEVEL_DATA[lvl]
    return None, None
