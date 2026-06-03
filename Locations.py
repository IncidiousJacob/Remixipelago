from BaseClasses import Location

BASE_ID = 8761000

CHARACTER_ID_TO_NAME = {
    0: "Mario",
    1: "Fox",
    2: "DK",
    3: "Samus",
    4: "Luigi",
    5: "Link",
    6: "Yoshi",
    7: "Captain Falcon",
    8: "Kirby",
    9: "Pikachu",
    10: "Jigglypuff",
    11: "Ness",
    29: "Falco",
    30: "Ganondorf",
    31: "Young Link",
    32: "Dr. Mario",
    33: "Wario",
    52: "Bowser",
    55: "Wolf",
    56: "Conker",
    57: "Mewtwo",
    58: "Marth",
    59: "Sonic",
    62: "Sheik",
    63: "Marina",
    64: "King Dedede",
    65: "Goemon",
    68: "Banjo & Kazooie",
    72: "Crash",
    73: "Peach",
}

CHARACTER_NAME_TO_ID = {name: value for value, name in CHARACTER_ID_TO_NAME.items()}
CHARACTERS = list(CHARACTER_ID_TO_NAME.values())

DIFFICULTIES = ["Very Easy", "Easy", "Normal", "Hard", "Very Hard"]
DIFFICULTY_VALUE_BY_NAME = {name: index for index, name in enumerate(DIFFICULTIES)}
DIFFICULTY_NAME_BY_VALUE = {value: name for name, value in DIFFICULTY_VALUE_BY_NAME.items()}

CLASSIC_FIGHTS = [
    "Link",
    "Yoshi Team",
    "Fox",
    "Mario Bros.",
    "Pikachu",
    "Giant DK",
    "Kirby Team",
    "Samus",
    "Metal Mario",
    "Fighting Polygon Team",
    "Master Hand",
]

CLASSIC_FIGHT_STAGE_IDS = {
    "Mario Bros.": 0x00,
    "Fox": 0x01,
    "Giant DK": 0x02,
    "Samus": 0x03,
    "Link": 0x04,
    "Yoshi Team": 0x0C,
    "Kirby Team": 0x06,
    "Pikachu": 0x07,
    "Metal Mario": 0x0D,
    "Fighting Polygon Team": 0x0E,
    "Master Hand": 0x10,
}

CLASSIC_FIGHT_NAME_BY_STAGE_ID = {
    value: name for name, value in CLASSIC_FIGHT_STAGE_IDS.items()
}

CLASSIC_FIGHT_GENERIC_NAME_BY_NAME = {
    fight: f"Fight {index} Win"
    for index, fight in enumerate(CLASSIC_FIGHTS, start=1)
}

BONUS_FIGHTS = ["Break the Targets"]

CLASSIC_CHECKS = [
    f"{difficulty} Defeat {fight}"
    for difficulty in DIFFICULTIES
    for fight in CLASSIC_FIGHTS
] + [
    f"{difficulty} {CLASSIC_FIGHT_GENERIC_NAME_BY_NAME[fight]}"
    for difficulty in DIFFICULTIES
    for fight in CLASSIC_FIGHTS
] + BONUS_FIGHTS

location_table = {}
_next_id = BASE_ID

for character in CHARACTERS:
    character_id = CHARACTER_NAME_TO_ID[character]
    for difficulty in DIFFICULTIES:
        difficulty_value = DIFFICULTY_VALUE_BY_NAME[difficulty]
        for fight in CLASSIC_FIGHTS:
            stage_id = CLASSIC_FIGHT_STAGE_IDS[fight]
            normal_location_name = f"{character}: {difficulty} Defeat {fight}"
            generic_location_name = f"{character}: {difficulty} {CLASSIC_FIGHT_GENERIC_NAME_BY_NAME[fight]}"

            location_table[normal_location_name] = {
                "code": _next_id,
                "normal_name": normal_location_name,
                "generic_name": generic_location_name,
                "character": character,
                "character_id": character_id,
                "difficulty": difficulty,
                "difficulty_value": difficulty_value,
                "fight": fight,
                "stage_id": stage_id,
                "type": "classic_fight",
            }
            _next_id += 1

            location_table[generic_location_name] = {
                "code": _next_id,
                "normal_name": normal_location_name,
                "generic_name": generic_location_name,
                "character": character,
                "character_id": character_id,
                "difficulty": difficulty,
                "difficulty_value": difficulty_value,
                "fight": fight,
                "stage_id": stage_id,
                "type": "classic_fight_randomized_cpu",
            }
            _next_id += 1

    for fight in BONUS_FIGHTS:
        location_table[f"{character}: {fight}"] = {
            "code": _next_id,
            "character": character,
            "character_id": character_id,
            "fight": fight,
            "type": "bonus_btt",
        }
        _next_id += 1

location_name_to_id = {name: data["code"] for name, data in location_table.items()}

location_id_by_character_stage_and_difficulty = {
    (data["character_id"], data["stage_id"], data["difficulty_value"]): data["code"]
    for data in location_table.values()
    if data["type"] == "classic_fight"
}

randomized_cpu_location_id_by_character_stage_and_difficulty = {
    (data["character_id"], data["stage_id"], data["difficulty_value"]): data["code"]
    for data in location_table.values()
    if data["type"] == "classic_fight_randomized_cpu"
}

location_id_by_btt_character_id = {
    data["character_id"]: data["code"]
    for data in location_table.values()
    if data["type"] == "bonus_btt"
}

master_hand_location_ids = {
    data["code"]
    for data in location_table.values()
    if data["type"] in {"classic_fight", "classic_fight_randomized_cpu"} and data["fight"] == "Master Hand"
}

master_hand_location_ids_by_difficulty = {
    difficulty_value: {
        data["code"]
        for data in location_table.values()
        if data["type"] in {"classic_fight", "classic_fight_randomized_cpu"}
        and data["fight"] == "Master Hand"
        and data["difficulty_value"] == difficulty_value
    }
    for difficulty_value in DIFFICULTY_VALUE_BY_NAME.values()
}


class SmashRemixLocation(Location):
    game = "Smash Remix"
