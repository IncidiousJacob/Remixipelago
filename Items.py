from BaseClasses import Item, ItemClassification

BASE_ID = 8760000

CHARACTERS = [
    "Mario",
    "Fox",
    "DK",
    "Samus",
    "Luigi",
    "Link",
    "Yoshi",
    "Captain Falcon",
    "Kirby",
    "Pikachu",
    "Jigglypuff",
    "Ness",
    "Falco",
    "Ganondorf",
    "Young Link",
    "Dr. Mario",
    "Wario",
    "Bowser",
    "Wolf",
    "Conker",
    "Mewtwo",
    "Marth",
    "Sonic",
    "Sheik",
    "Marina",
    "King Dedede",
    "Goemon",
    "Banjo & Kazooie",
    "Crash",
    "Peach",
]

FIGHTER_PASS_ITEMS = [f"{character} Fighter Pass" for character in CHARACTERS]

ONE_UP_ID = BASE_ID
PROGRESSIVE_MAX_STOCKS_ID = BASE_ID + 100
EXTRA_STOCK_ID = BASE_ID + 101
STOCK_THIEF_ID = BASE_ID + 102
PROGRESSIVE_DIFFICULTY_ID = BASE_ID + 103
CLASSIC_MODE_CLEAR_ID = BASE_ID + 998
VICTORY_ID = BASE_ID + 999

item_table = {
    "One-Up": (ONE_UP_ID, ItemClassification.filler),
    "Progressive Max Stocks": (PROGRESSIVE_MAX_STOCKS_ID, ItemClassification.progression),
    "Extra Stock": (EXTRA_STOCK_ID, ItemClassification.filler),
    "Stock Thief": (STOCK_THIEF_ID, ItemClassification.trap),
    "Progressive Difficulty": (PROGRESSIVE_DIFFICULTY_ID, ItemClassification.progression),
    "Classic Mode Clear": (CLASSIC_MODE_CLEAR_ID, ItemClassification.progression),
    "Victory": (VICTORY_ID, ItemClassification.progression),
}

for index, item_name in enumerate(FIGHTER_PASS_ITEMS, start=1):
    item_table[item_name] = (BASE_ID + index, ItemClassification.progression)


class SmashRemixItem(Item):
    game = "Smash Remix"
