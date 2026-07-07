import random

# ── PLAYER INTERESTS ──────────────────────────────────────────────────────────
# Placeholder list — swap the dict entries when the real wordlist arrives.
# Structure: { key: {"label": str, "emoji": str} }
# No other code references specific keys, so replacing entries is a data change only.
INTEREST_TOPICS = {
    "cooking":     {"label": "Cooking",     "emoji": "🍳"},
    "music":       {"label": "Music",       "emoji": "🎵"},
    "fishing":     {"label": "Fishing",     "emoji": "🎣"},
    "history":     {"label": "History",     "emoji": "📜"},
    "combat":      {"label": "Combat",      "emoji": "⚔️"},
    "fashion":     {"label": "Fashion",     "emoji": "👗"},
    "exploration": {"label": "Exploration", "emoji": "🗺️"},
    "science":     {"label": "Science",     "emoji": "🔬"},
    "nature":      {"label": "Nature",      "emoji": "🌿"},
    "mystery":     {"label": "Mystery",     "emoji": "🔍"},
}

MAX_INTERESTS = 5  # cap per player (flagged: change here to adjust)

SOCIAL_TRAITS = {
    "friendly": {
        "name": "Friendly", "emoji": "🤝",
        "description": "Loves meeting other penguins and spreading warmth",
    },
    "shy": {
        "name": "Shy", "emoji": "🤫",
        "description": "Prefers quiet corners and watching from afar",
    },
    "dramatic": {
        "name": "Dramatic", "emoji": "🎭",
        "description": "Everything is a big deal. EVERYTHING.",
    },
    "flirty": {
        "name": "Flirty", "emoji": "💘",
        "description": "Can't help winking at everyone. Frequent Horny Jail visitor.",
    },
}

INTEREST_TRAITS = {
    "curious": {
        "name": "Curious", "emoji": "🔍",
        "description": "Always poking around and asking questions",
    },
    "religious": {
        "name": "Religious", "emoji": "🙏",
        "description": "Finds meaning in meditation and the Cursed Temple",
    },
    "greedy": {
        "name": "Greedy", "emoji": "💰",
        "description": "Counts everything. Twice. Hoards shiny objects.",
    },
    "fancy": {
        "name": "Fancy", "emoji": "🎨",
        "description": "Fashion is life. Judges outfits. Poses constantly.",
    },
}

QUIRK_TRAITS = {
    "clumsy": {
        "name": "Clumsy", "emoji": "🤕",
        "description": "Trips over everything. Even flat snow.",
    },
    "lucky": {
        "name": "Lucky", "emoji": "🍀",
        "description": "Good things just... happen. Annoyingly often.",
    },
    "sleepy": {
        "name": "Sleepy", "emoji": "😴",
        "description": "Could fall asleep anywhere. Has fallen asleep everywhere.",
    },
    "hungry": {
        "name": "Hungry", "emoji": "🐟",
        "description": "Always thinking about fish. Always.",
    },
    "musical": {
        "name": "Musical", "emoji": "🎵",
        "description": "Hums constantly. Sometimes in tune.",
    },
    "paranoid": {
        "name": "Paranoid", "emoji": "👀",
        "description": "The snowmen are watching. They're always watching.",
    },
}

ALL_TRAITS = {**SOCIAL_TRAITS, **INTEREST_TRAITS, **QUIRK_TRAITS}

CATEGORY_EMOJIS = {
    "social":   "💬",
    "solo":     "🐧",
    "explore":  "🗺️",
    "conflict": "⚡",
    "jail":     "🔒",
    "village":  "🏘️",
    "quirk":    "✨",
}

AUTONOMOUS_ACTIONS = [
    # ── FRIENDLY ──
    {"template": "{penguin} visited {other}'s igloo and brought cookies 🍪",
     "weights": {"friendly": 5, "shy": 0, "dramatic": 1, "flirty": 1},
     "requires_other": True, "category": "social"},
    {"template": "{penguin} organized a snowball fight in the village square",
     "weights": {"friendly": 5, "dramatic": 3, "shy": 0, "curious": 2},
     "requires_other": False, "category": "social"},
    {"template": "{penguin} complimented {other}'s hat",
     "weights": {"friendly": 4, "fancy": 3, "shy": 1, "flirty": 2},
     "requires_other": True, "category": "social"},
    {"template": "{penguin} shared their fish with {other} at the pond",
     "weights": {"friendly": 5, "hungry": 2, "greedy": 0, "shy": 1},
     "requires_other": True, "category": "social"},
    {"template": "{penguin} started a book club. Nobody came. {penguin} read alone happily.",
     "weights": {"friendly": 3, "shy": 4, "curious": 3, "dramatic": 1},
     "requires_other": False, "category": "social"},

    # ── SHY ──
    {"template": "{penguin} watched the sunset from behind a tree 🌅",
     "weights": {"shy": 5, "friendly": 1, "dramatic": 0, "religious": 2},
     "requires_other": False, "category": "solo"},
    {"template": "{penguin} left an anonymous gift at {other}'s igloo",
     "weights": {"shy": 5, "friendly": 3, "greedy": 0, "flirty": 2},
     "requires_other": True, "category": "social"},
    {"template": "{penguin} waved at {other} from across the village but they didn't see",
     "weights": {"shy": 5, "friendly": 2, "clumsy": 2, "dramatic": 0},
     "requires_other": True, "category": "social"},
    {"template": "{penguin} found a quiet spot and drew pictures in the snow",
     "weights": {"shy": 5, "curious": 2, "fancy": 2, "dramatic": 0},
     "requires_other": False, "category": "solo"},
    {"template": "{penguin} hid behind the Penguin Hotel when they saw a group approaching",
     "weights": {"shy": 5, "paranoid": 3, "friendly": 0, "dramatic": 0},
     "requires_other": False, "category": "solo"},

    # ── DRAMATIC ──
    {"template": "{penguin} accused {other} of stealing their fish (they didn't) 🐟",
     "weights": {"dramatic": 5, "greedy": 3, "friendly": 0, "paranoid": 3},
     "requires_other": True, "category": "conflict"},
    {"template": "{penguin} made a dramatic speech about the future of the village",
     "weights": {"dramatic": 5, "religious": 2, "shy": 0, "curious": 1},
     "requires_other": False, "category": "solo"},
    {"template": "{penguin} slammed the door of the Penguin Hotel and yelled 'I'M FINE'",
     "weights": {"dramatic": 5, "friendly": 0, "shy": 0, "flirty": 2},
     "requires_other": False, "category": "solo"},
    {"template": "{penguin} challenged {other} to a staring contest. {penguin} blinked first.",
     "weights": {"dramatic": 5, "clumsy": 2, "shy": 0},
     "requires_other": True, "category": "social"},
    {"template": "{penguin} started a rumor that the Penguin Bank is haunted 👻",
     "weights": {"dramatic": 5, "paranoid": 3, "curious": 2, "religious": 2},
     "requires_other": False, "category": "village"},

    # ── FLIRTY ──
    {"template": "{penguin} winked at {other} near the frozen pond 💘",
     "weights": {"flirty": 5, "friendly": 2, "shy": 0, "dramatic": 2},
     "requires_other": True, "category": "social"},
    {"template": "{penguin} sent a love letter to {other}. It was... a lot.",
     "weights": {"flirty": 5, "dramatic": 3, "shy": 0, "fancy": 2},
     "requires_other": True, "category": "social"},
    {"template": "{penguin} got sent to Horny Jail. Again. 🔒",
     "weights": {"flirty": 5, "dramatic": 2, "clumsy": 1, "friendly": 0},
     "requires_other": False, "category": "jail"},
    {"template": "{penguin} practiced pickup lines on a snowman",
     "weights": {"flirty": 5, "clumsy": 3, "shy": 2, "dramatic": 2},
     "requires_other": False, "category": "solo"},
    {"template": "{penguin} left a rose at {other}'s igloo door 🌹",
     "weights": {"flirty": 4, "shy": 3, "friendly": 2, "fancy": 2},
     "requires_other": True, "category": "social"},

    # ── CURIOUS ──
    {"template": "{penguin} explored the edge of the frozen pond and found a strange rock",
     "weights": {"curious": 5, "shy": 2, "greedy": 2, "lucky": 3},
     "requires_other": False, "category": "explore"},
    {"template": "{penguin} asked {other} 47 questions about their day",
     "weights": {"curious": 5, "friendly": 3, "shy": 0, "dramatic": 1},
     "requires_other": True, "category": "social"},
    {"template": "{penguin} discovered a secret path behind the Cursed Temple 🗺️",
     "weights": {"curious": 5, "religious": 2, "lucky": 3, "paranoid": 1},
     "requires_other": False, "category": "explore"},
    {"template": "{penguin} tried to figure out what's inside the Penguin Bank vault",
     "weights": {"curious": 5, "greedy": 4, "paranoid": 2, "dramatic": 1},
     "requires_other": False, "category": "explore"},
    {"template": "{penguin} spent an hour watching ants carry crumbs and took notes 📝",
     "weights": {"curious": 5, "shy": 2, "sleepy": 0, "fancy": 0},
     "requires_other": False, "category": "solo"},

    # ── RELIGIOUS ──
    {"template": "{penguin} meditated at the Cursed Temple for three hours 🧘",
     "weights": {"religious": 5, "shy": 3, "dramatic": 0, "sleepy": 2},
     "requires_other": False, "category": "solo"},
    {"template": "{penguin} wrote a prayer for the village's prosperity ✨",
     "weights": {"religious": 5, "friendly": 2, "shy": 2, "fancy": 1},
     "requires_other": False, "category": "solo"},
    {"template": "{penguin} tried to convert {other} to the ways of the Cursed Temple",
     "weights": {"religious": 5, "dramatic": 3, "friendly": 2, "shy": 0},
     "requires_other": True, "category": "social"},
    {"template": "{penguin} had a vision that the village would grow tenfold 🔮",
     "weights": {"religious": 5, "dramatic": 3, "curious": 2, "paranoid": 2},
     "requires_other": False, "category": "village"},
    {"template": "{penguin} lit a candle at the Cursed Temple and hummed softly 🕯️",
     "weights": {"religious": 5, "musical": 3, "shy": 2, "fancy": 1},
     "requires_other": False, "category": "solo"},

    # ── GREEDY ──
    {"template": "{penguin} counted their gold three times and found the same number each time",
     "weights": {"greedy": 5, "paranoid": 3, "curious": 2, "dramatic": 1},
     "requires_other": False, "category": "solo"},
    {"template": "{penguin} tried to charge {other} for walking near their igloo",
     "weights": {"greedy": 5, "dramatic": 3, "friendly": 0, "flirty": 0},
     "requires_other": True, "category": "conflict"},
    {"template": "{penguin} found a gold coin on the ground and did a victory dance 💰",
     "weights": {"greedy": 5, "lucky": 4, "dramatic": 2, "musical": 2},
     "requires_other": False, "category": "solo"},
    {"template": "{penguin} offered to 'invest' {other}'s gold. {other} politely declined.",
     "weights": {"greedy": 5, "dramatic": 2, "friendly": 1, "curious": 1},
     "requires_other": True, "category": "social"},
    {"template": "{penguin} started a tab at Club Soda and 'forgot' to pay",
     "weights": {"greedy": 5, "dramatic": 2, "clumsy": 2, "lucky": 2},
     "requires_other": False, "category": "village"},

    # ── FANCY ──
    {"template": "{penguin} spent 3 hours trying on hats at the Boutique 🎩",
     "weights": {"fancy": 5, "greedy": 1, "shy": 1, "dramatic": 2},
     "requires_other": False, "category": "solo"},
    {"template": "{penguin} judged {other}'s outfit. Silently. Disapprovingly.",
     "weights": {"fancy": 5, "dramatic": 3, "shy": 2, "friendly": 0},
     "requires_other": True, "category": "social"},
    {"template": "{penguin} posed dramatically in front of the frozen pond 📸",
     "weights": {"fancy": 5, "dramatic": 4, "flirty": 3, "shy": 0},
     "requires_other": False, "category": "solo"},
    {"template": "{penguin} organized an impromptu fashion show at the Boutique",
     "weights": {"fancy": 5, "dramatic": 3, "friendly": 2, "flirty": 2},
     "requires_other": False, "category": "village"},
    {"template": "{penguin} told {other} that vertical stripes are 'so last era'",
     "weights": {"fancy": 5, "dramatic": 3, "flirty": 1, "friendly": 0},
     "requires_other": True, "category": "social"},

    # ── QUIRKS ──
    {"template": "{penguin} tripped over absolutely nothing and faceplanted in the snow",
     "weights": {"clumsy": 5, "dramatic": 2, "shy": 1, "fancy": 0},
     "requires_other": False, "category": "quirk"},
    {"template": "{penguin} accidentally knocked over {other}'s snowman. Oops.",
     "weights": {"clumsy": 5, "friendly": 1, "dramatic": 2, "shy": 2},
     "requires_other": True, "category": "quirk"},
    {"template": "{penguin} slipped on ice and slid all the way across the village square",
     "weights": {"clumsy": 5, "dramatic": 3, "lucky": 2, "fancy": 0},
     "requires_other": False, "category": "quirk"},
    {"template": "{penguin} found a four-leaf clover growing through the snow 🍀",
     "weights": {"lucky": 5, "curious": 3, "religious": 2, "greedy": 1},
     "requires_other": False, "category": "quirk"},
    {"template": "{penguin} accidentally walked into the right building at the right time and got free fish",
     "weights": {"lucky": 5, "clumsy": 3, "hungry": 2, "greedy": 2},
     "requires_other": False, "category": "quirk"},
    {"template": "{penguin} fell asleep on a bench in the village square. Nobody moved them. 😴",
     "weights": {"sleepy": 5, "shy": 2, "friendly": 1, "dramatic": 0},
     "requires_other": False, "category": "quirk"},
    {"template": "{penguin} fell asleep during {other}'s story. {other} kept talking anyway.",
     "weights": {"sleepy": 5, "shy": 2, "friendly": 1, "dramatic": 0},
     "requires_other": True, "category": "quirk"},
    {"template": "{penguin} napped at the Cursed Temple and had a prophetic dream",
     "weights": {"sleepy": 4, "religious": 4, "curious": 2, "dramatic": 2},
     "requires_other": False, "category": "quirk"},
    {"template": "{penguin} ate fish for breakfast, lunch, dinner, and two snacks 🐟",
     "weights": {"hungry": 5, "greedy": 2, "friendly": 1, "fancy": 0},
     "requires_other": False, "category": "quirk"},
    {"template": "{penguin} asked {other} if they were going to finish that fish",
     "weights": {"hungry": 5, "friendly": 2, "greedy": 3, "shy": 0},
     "requires_other": True, "category": "quirk"},
    {"template": "{penguin} reviewed every restaurant in the village. There are none. Reviewed the snow.",
     "weights": {"hungry": 5, "fancy": 3, "dramatic": 3, "curious": 2},
     "requires_other": False, "category": "quirk"},
    {"template": "{penguin} hummed a tune while walking through the village 🎵",
     "weights": {"musical": 5, "friendly": 2, "fancy": 1, "shy": 1},
     "requires_other": False, "category": "quirk"},
    {"template": "{penguin} started a jam session at Club Soda. It was... interesting.",
     "weights": {"musical": 5, "dramatic": 3, "friendly": 2, "clumsy": 2},
     "requires_other": False, "category": "village"},
    {"template": "{penguin} composed a ballad about {other}. It didn't rhyme.",
     "weights": {"musical": 5, "flirty": 3, "dramatic": 2, "clumsy": 2},
     "requires_other": True, "category": "social"},
    {"template": "{penguin} heard a suspicious noise and investigated for 45 minutes. It was the wind.",
     "weights": {"paranoid": 5, "curious": 3, "dramatic": 2, "shy": 1},
     "requires_other": False, "category": "quirk"},
    {"template": "{penguin} is convinced {other} is hiding something. They're not.",
     "weights": {"paranoid": 5, "dramatic": 3, "curious": 2, "greedy": 1},
     "requires_other": True, "category": "quirk"},
    {"template": "{penguin} triple-locked their igloo door and checked it five times",
     "weights": {"paranoid": 5, "greedy": 3, "shy": 2, "dramatic": 2},
     "requires_other": False, "category": "quirk"},

    # ── INTEREST-FLAVORED (generic — {interest} filled at text-generation time) ──
    # These only fire when the penguin has at least one selected interest.
    {"template": "{penguin} spent the afternoon lost in thoughts about {interest}",
     "weights": {"curious": 2, "shy": 2},
     "requires_other": False, "requires_interest": True, "category": "solo"},
    {"template": "{penguin} cornered {other} and wouldn't stop talking about {interest}",
     "weights": {"friendly": 2, "dramatic": 2, "curious": 2},
     "requires_other": True, "requires_interest": True, "category": "social"},
    {"template": "{penguin} started a village club for fans of {interest}. Attendance: 1.",
     "weights": {"friendly": 2, "dramatic": 2, "shy": 0},
     "requires_other": False, "requires_interest": True, "category": "village"},
    {"template": "{penguin} wrote a long essay about {interest} and left it on a bench",
     "weights": {"curious": 3, "dramatic": 2, "musical": 1},
     "requires_other": False, "requires_interest": True, "category": "solo"},
    {"template": "{penguin} challenged {other} to settle a debate about {interest}",
     "weights": {"dramatic": 3, "curious": 2, "friendly": 1},
     "requires_other": True, "requires_interest": True, "category": "social"},
]


def pick_autonomous_action(penguin, all_penguins):
    traits      = [penguin.get("trait_social"), penguin.get("trait_interest"), penguin.get("trait_quirk")]
    social_mode = penguin.get("social_mode") or "social"
    others      = [p for p in all_penguins if p["username"] != penguin["username"]]
    has_interests = bool(penguin.get("interests"))

    scored = []
    for action in AUTONOMOUS_ACTIONS:
        requires_other    = action.get("requires_other", False)
        requires_interest = action.get("requires_interest", False)
        if requires_other and not others:
            continue
        if requires_interest and not has_interests:
            continue

        score = sum(action["weights"].get(t, 0) for t in traits if t) or 1

        if social_mode == "homebody":
            if requires_other:
                score = max(1, score // 4)   # drastically reduce social
            else:
                score = int(score * 1.5)     # boost solo
        elif social_mode == "social":
            if requires_other:
                score = int(score * 1.3)     # slightly boost social
        elif social_mode == "focused":
            if requires_other:
                score = int(score * 1.2)     # slightly boost social (target handled in pick_other)

        scored.append((action, score))

    if not scored:
        return random.choice(AUTONOMOUS_ACTIONS)

    total = sum(s for _, s in scored)
    roll  = random.uniform(0, total)
    cumulative = 0
    for action, score in scored:
        cumulative += score
        if roll <= cumulative:
            return action
    return scored[-1][0]


def pick_other_penguin(penguin, all_penguins):
    others = [p for p in all_penguins if p["username"] != penguin["username"]]
    if not others:
        return None
    social_mode   = penguin.get("social_mode") or "social"
    social_target = penguin.get("social_target")
    if social_mode == "focused" and social_target:
        target = next((p for p in others if p["username"] == social_target), None)
        if target and random.random() < 0.60:
            return target
    return random.choice(others)


def generate_action_text(action, penguin, other_penguin=None):
    pname = penguin.get("penguin_name") or penguin["username"]
    text = action["template"].replace("{penguin}", pname)
    if action.get("requires_other") and "{other}" in text and other_penguin:
        oname = other_penguin.get("penguin_name") or other_penguin["username"]
        text = text.replace("{other}", oname)
    if action.get("requires_interest") and "{interest}" in text:
        interests = penguin.get("interests") or []
        if interests:
            chosen = random.choice(interests)
            topic  = INTEREST_TOPICS.get(chosen)
            label  = f"{topic['emoji']} {topic['label']}" if topic else chosen
        else:
            label = "something"
        text = text.replace("{interest}", label)
    return text
