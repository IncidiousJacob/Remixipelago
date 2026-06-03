import os

from BaseClasses import Tutorial
from worlds.AutoWorld import WebWorld, World

from .Items import (
    SmashRemixItem,
    item_table,
    FIGHTER_PASS_ITEMS,
    CHARACTERS,
)
from .Locations import (
    SmashRemixLocation,
    location_table,
    location_name_to_id,
    CHARACTER_ID_TO_NAME,
    CHARACTER_NAME_TO_ID,
    DIFFICULTY_NAME_BY_VALUE,
    CLASSIC_FIGHTS,
    CLASSIC_FIGHT_STAGE_IDS,
)
from .Options import SmashRemixOptions
from .Rules import set_rules
from .Patch import make_patch

# Importing Client.py registers the BizHawk ROM handler.
from . import Client


DIFFICULTY_KEY_TO_VALUE = {
    "very_easy": 0,
    "easy": 1,
    "normal": 2,
    "hard": 3,
    "very_hard": 4,
}


def launch_smash_remix_patch(*args: str) -> None:
    from Patch import create_rom_file
    from Utils import messagebox, open_file

    if not args:
        messagebox("Smash Remix", "No .apsr patch file was selected.", error=True)
        return

    for patch_file in args:
        try:
            _meta, output_rom = create_rom_file(patch_file)
        except Exception as exc:
            messagebox("Smash Remix patch failed", str(exc), error=True)
            raise
        else:
            open_file(output_rom)


try:
    from worlds.LauncherComponents import Component, SuffixIdentifier, Type, components, launch_subprocess

    components.append(Component(
        "Smash Remix Client",
        component_type=Type.CLIENT,
        func=launch_subprocess,
        script_name="BizHawkClient",
        game_name="Smash Remix",
        description="Connect Smash Remix through BizHawk.",
    ))

    components.append(Component(
        "Smash Remix Patch",
        component_type=Type.CLIENT,
        func=launch_smash_remix_patch,
        file_identifier=SuffixIdentifier(".apsr"),
        game_name="Smash Remix",
        description="Apply a Smash Remix .apsr patch file.",
    ))
except Exception:
    pass


class SmashRemixWeb(WebWorld):
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide to setting up Smash Remix for Archipelago.",
        "English",
        "setup_en.md",
        "setup/en",
        ["Jacob Dock", "ChatGPT"]
    )]


class SmashRemixWorld(World):
    """Smash Remix 2.0.1 APWorld with Fighter Passes, stock locks, and difficulty checks."""

    game = "Smash Remix"
    author = "Jacob Dock"
    options_dataclass = SmashRemixOptions
    options: SmashRemixOptions
    web = SmashRemixWeb()

    item_name_to_id = {name: data[0] for name, data in item_table.items()}
    location_name_to_id = location_name_to_id

    required_client_version = (0, 6, 7)

    def _choose_starting_character(self) -> str:
        if self.options.starting_character.is_random:
            return self.random.choice(CHARACTERS)
        return self.options.starting_character.character_name

    def _get_starting_character_name(self) -> str:
        return getattr(self, "selected_starting_character", self.options.starting_character.character_name)

    def _get_enabled_difficulty_values(self):
        selected = getattr(self.options.difficulty_checks, "value", None)
        if not selected:
            return {0, 1, 2, 3, 4}

        values = set()
        for key in selected:
            value = DIFFICULTY_KEY_TO_VALUE.get(str(key))
            if value is not None:
                values.add(value)
        return values or {0}

    def _is_randomizing_classic_cpu_characters(self) -> bool:
        return bool(self.options.randomize_classic_cpu_characters.value)

    def _build_classic_cpu_randomizer_table(self) -> dict[str, list[int]]:
        """Build deterministic per-slot CPU character values for the BizHawk client."""
        if not self._is_randomizing_classic_cpu_characters():
            return {}

        # Smash Remix can load the full known roster as Classic CPU opponents.
        cpu_character_ids = list(CHARACTER_ID_TO_NAME.keys())
        if not cpu_character_ids:
            return {}

        table: dict[str, list[int]] = {}
        for character_name in CHARACTERS:
            player_char_id = CHARACTER_NAME_TO_ID[character_name]
            for difficulty_value in sorted(self._get_enabled_difficulty_values()):
                for fight in CLASSIC_FIGHTS:
                    if fight == "Master Hand":
                        continue
                    stage_id = CLASSIC_FIGHT_STAGE_IDS[fight]
                    table[f"{player_char_id}:{stage_id}:{difficulty_value}"] = [
                        self.random.choice(cpu_character_ids),
                        self.random.choice(cpu_character_ids),
                        self.random.choice(cpu_character_ids),
                    ]
        return table

    def generate_early(self):
        include_bonus = bool(self.options.include_bonus_stages.value)
        enabled_difficulty_values = self._get_enabled_difficulty_values()
        starting_character = self._choose_starting_character()
        self.selected_starting_character = starting_character
        self.classic_cpu_randomizer_table = self._build_classic_cpu_randomizer_table()
        goal_difficulty_value = int(self.options.goal_difficulty.value)

        if not enabled_difficulty_values:
            raise Exception(
                "Smash Remix option error: difficulty_checks must include at least one difficulty."
            )

        if goal_difficulty_value not in enabled_difficulty_values:
            raise Exception(
                "Smash Remix option error: goal_difficulty must be one of the difficulties listed in "
                "difficulty_checks. Add the goal difficulty to difficulty_checks or choose a different "
                "goal_difficulty."
            )

        # The goal is X characters beating Master Hand on the goal difficulty.
        max_possible_classic_completions = len(CHARACTERS)
        required_classic_completions = int(self.options.required_classic_completions.value)
        if required_classic_completions > max_possible_classic_completions:
            raise Exception(
                "Smash Remix option error: required_classic_completions is higher than the number "
                f"of characters available. Requested {required_classic_completions}, but only "
                f"{max_possible_classic_completions} characters exist."
            )

        self.active_locations = {}
        for name, data in location_table.items():
            if data["type"] == "bonus_btt" and not include_bonus:
                continue

            if data["type"] == "classic_fight" and self._is_randomizing_classic_cpu_characters():
                continue

            if data["type"] == "classic_fight_randomized_cpu" and not self._is_randomizing_classic_cpu_characters():
                continue

            # Only include Classic fight checks for exact YAML-selected difficulties.
            # This matches the Smash64 APWorld behavior.
            if data["type"] in {"classic_fight", "classic_fight_randomized_cpu"} and data.get("difficulty_value", 0) not in enabled_difficulty_values:
                continue

            self.active_locations[name] = data

    def create_regions(self):
        from BaseClasses import Region, Entrance

        if not hasattr(self, "active_locations"):
            self.generate_early()

        menu = Region("Menu", self.player, self.multiworld)
        menu.exits.append(Entrance(self.player, "Start Game", menu))

        classic = Region("Classic Mode", self.player, self.multiworld)
        for location_name, data in self.active_locations.items():
            classic.locations.append(SmashRemixLocation(self.player, location_name, data["code"], classic))

        self.multiworld.regions += [menu, classic]
        menu.exits[0].connect(classic)

    def create_item(self, name: str):
        code, classification = item_table[name]
        return SmashRemixItem(name, classification, code, self.player)

    def create_items(self):
        if not hasattr(self, "active_locations"):
            self.generate_early()

        starting_character = self._get_starting_character_name()
        starting_item_name = f"{starting_character} Fighter Pass"

        self.multiworld.push_precollected(self.create_item(starting_item_name))

        # Goal tokens are locked onto Master Hand locations, just like Smash64.
        # Only goal_difficulty Master Hand clears award Classic Mode Clear so the
        # goal is "beat Master Hand with X characters" on the chosen goal difficulty.
        goal_difficulty_value = int(self.options.goal_difficulty.value)
        locked_goal_location_count = 0
        for location_name, data in self.active_locations.items():
            if (
                data["type"] in {"classic_fight", "classic_fight_randomized_cpu"}
                and data["fight"] == "Master Hand"
                and int(data.get("difficulty_value", 0)) == goal_difficulty_value
            ):
                self.multiworld.get_location(location_name, self.player).place_locked_item(
                    self.create_item("Classic Mode Clear")
                )
                locked_goal_location_count += 1

        character_item_count = 0
        for item_name in FIGHTER_PASS_ITEMS:
            if item_name == starting_item_name:
                continue
            self.multiworld.itempool.append(self.create_item(item_name))
            character_item_count += 1

        # Start Classic Mode capped by YAML. The in-game selector stores stocks as:
        # 0 = 1 stock, 1 = 2 stocks, 2 = 3 stocks, 3 = 4 stocks, 4 = 5 stocks.
        # Each Progressive Max Stocks item raises the allowed cap by one until 5.
        starting_max_stocks = int(self.options.starting_max_stocks.value)
        progressive_max_stocks_count = max(0, 5 - starting_max_stocks)
        for _ in range(progressive_max_stocks_count):
            self.multiworld.itempool.append(self.create_item("Progressive Max Stocks"))

        # Difficulty checks can be sparse. Precollect enough Progressive Difficulty
        # to make the lowest selected difficulty legal from the start, then place
        # enough progressives to unlock up to the highest selected difficulty.
        enabled_difficulty_values = self._get_enabled_difficulty_values()
        starting_difficulty_cap = min(enabled_difficulty_values)
        max_selected_difficulty = max(enabled_difficulty_values)

        for _ in range(starting_difficulty_cap):
            self.multiworld.push_precollected(self.create_item("Progressive Difficulty"))

        progressive_difficulty_count = max_selected_difficulty - starting_difficulty_cap
        for _ in range(progressive_difficulty_count):
            self.multiworld.itempool.append(self.create_item("Progressive Difficulty"))

        # Every item placed at a location must have an integer code for the hosted server.
        # Do not create filler with code=None, or uploaded .archipelago files can crash
        # WebHostLib's LocationStore with: TypeError: an integer is required.
        stock_thief_count = int(self.options.stock_thief_count.value)
        filler_count = (
            len(self.active_locations)
            - locked_goal_location_count
            - character_item_count
            - progressive_max_stocks_count
            - progressive_difficulty_count
            - stock_thief_count
        )
        if filler_count < 0:
            raise Exception(
                "Not enough Smash Remix locations to place the requested item pool. "
                f"Need {-filler_count} more filler slots. Lower stock_thief_count, "
                "enable more difficulty_checks, or enable bonus stages."
            )

        for _ in range(stock_thief_count):
            self.multiworld.itempool.append(self.create_item("Stock Thief"))

        filler_item_names = ["One-Up", "Extra Stock"]
        for _ in range(filler_count):
            self.multiworld.itempool.append(self.create_item(self.random.choice(filler_item_names)))

    def get_filler_item_name(self) -> str:
        return self.random.choice(["One-Up", "Extra Stock", "Stock Thief"])

    def set_rules(self):
        if not hasattr(self, "active_locations"):
            self.generate_early()
        set_rules(self)
        self.multiworld.completion_condition[self.player] = lambda state: state.has(
            "Classic Mode Clear",
            self.player,
            int(self.options.required_classic_completions.value),
        )

    @classmethod
    def stage_generate_output(cls, multiworld, output_directory: str):
        for player in multiworld.get_game_players(cls.game):
            world = multiworld.worlds[player]
            make_patch(world, output_directory)

    def generate_output(self, output_directory: str):
        make_patch(self, output_directory)

    def fill_slot_data(self):
        if not hasattr(self, "active_locations"):
            self.generate_early()

        enabled_difficulty_values = self._get_enabled_difficulty_values()
        goal_difficulty = int(self.options.goal_difficulty.value)

        return {
            "rom_header": "SMASH REMIX",
            "rom_code": "NALE",
            "rom_md5": "2b2d6b295106c54216b7fc7a2f14346e",
            "rom_sha1": "13716381ed5e29be2606e0f4724b18fd00789d04",
            "classic_only": True,
            "fighter_passes_enabled": True,
            "fighter_pass_items": FIGHTER_PASS_ITEMS,
            "starting_character": self._get_starting_character_name(),
            "starting_character_randomized": bool(self.options.starting_character.is_random),
            "required_classic_completions": int(self.options.required_classic_completions.value),
            "include_bonus_stages": bool(self.options.include_bonus_stages.value),
            "starting_max_stocks": int(self.options.starting_max_stocks.value),
            "difficulty_checks": sorted(enabled_difficulty_values),
            "auto_check_lower_difficulties": bool(self.options.auto_check_lower_difficulties.value),
            "randomize_classic_cpu_characters": bool(self.options.randomize_classic_cpu_characters.value),
            "classic_cpu_randomizer_table": getattr(self, "classic_cpu_randomizer_table", {}),
            "starting_difficulty_cap": min(enabled_difficulty_values),
            "max_difficulty_checks": max(enabled_difficulty_values),
            "goal_difficulty": goal_difficulty,
            "goal_difficulty_name": DIFFICULTY_NAME_BY_VALUE.get(goal_difficulty, "Very Easy"),
            "stock_thief_count": int(self.options.stock_thief_count.value),
            "smash_cash_per_fight_win": 10,
            "smash_cash_master_hand_reward": 50,
            "smash_cash_server_tag": "SmashCash",
            "smash_cash_toggle_command": "/Money",
            "smash_cash_stock_cost": 50,
            "smash_cash_heal_costs": {"heal5": 5, "heal10": 10, "heal20": 20, "heal50": 50},
            "p1_character_select_address": 0x138F0B,
            "p1_classic_character_address": 0x0A4B3B,
            "max_stocks_select_address": 0x138FBB,
            "difficulty_select_address": 0x138FB7,
            "character_id_to_name": CHARACTER_ID_TO_NAME,
            "classic_fights": CLASSIC_FIGHTS,
            "active_location_count": len(self.active_locations),
        }
