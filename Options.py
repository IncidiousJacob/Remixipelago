from Options import Choice, Range, PerGameCommonOptions, StartInventoryPool, Toggle, OptionSet
from dataclasses import dataclass


class StartingCharacter(Choice):
    """Character available at the start. That character's Fighter Pass is precollected.

    Use random to choose one supported Smash Remix character during generation.
    """
    display_name = "Starting Character"

    option_mario = 0
    option_fox = 1
    option_dk = 2
    option_samus = 3
    option_luigi = 4
    option_link = 5
    option_yoshi = 6
    option_captain_falcon = 7
    option_kirby = 8
    option_pikachu = 9
    option_jigglypuff = 10
    option_ness = 11
    option_falco = 12
    option_ganondorf = 13
    option_young_link = 14
    option_dr_mario = 15
    option_wario = 16
    option_bowser = 17
    option_wolf = 18
    option_conker = 19
    option_mewtwo = 20
    option_marth = 21
    option_sonic = 22
    option_sheik = 23
    option_marina = 24
    option_king_dedede = 25
    option_goemon = 26
    option_banjo_kazooie = 27
    option_crash = 28
    option_peach = 29
    option_random = 30

    default = 0

    @property
    def character_name(self) -> str:
        return {
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
            12: "Falco",
            13: "Ganondorf",
            14: "Young Link",
            15: "Dr. Mario",
            16: "Wario",
            17: "Bowser",
            18: "Wolf",
            19: "Conker",
            20: "Mewtwo",
            21: "Marth",
            22: "Sonic",
            23: "Sheik",
            24: "Marina",
            25: "King Dedede",
            26: "Goemon",
            27: "Banjo & Kazooie",
            28: "Crash",
            29: "Peach",
            30: "Random",
        }[int(self.value)]

    @property
    def is_random(self) -> bool:
        return int(self.value) == 30


class RequiredClassicCompletions(Range):
    """How many different characters must beat Master Hand on the goal difficulty to finish the seed."""
    display_name = "Required Classic Completions"
    range_start = 1
    range_end = 30
    default = 8


class IncludeBonusStages(Toggle):
    """Whether Break the Targets checks are included."""
    display_name = "Include Bonus Stages"
    default = 1


class StartingMaxStocks(Range):
    """Maximum Classic stock setting available at the start. Progressive Max Stocks items raise this up to 5 stocks."""
    display_name = "Starting Max Stocks"
    range_start = 1
    range_end = 5
    default = 1


class DifficultyChecks(OptionSet):
    """Classic difficulties that have AP checks and are allowed on the difficulty selector."""
    display_name = "Difficulty Checks"
    valid_keys = {"very_easy", "easy", "normal", "hard", "very_hard"}
    default = {"very_easy", "easy", "normal", "hard", "very_hard"}


class AutoCheckLowerDifficulties(Toggle):
    """Clearing a fight on a difficulty also sends the same fight for lower selected difficulties."""
    display_name = "Auto Check Lower Difficulties"
    default = 0


class GoalDifficulty(Choice):
    """Classic difficulty that Master Hand clears must be on to count toward the goal."""
    display_name = "Goal Difficulty"
    option_very_easy = 0
    option_easy = 1
    option_normal = 2
    option_hard = 3
    option_very_hard = 4
    default = 0

    @property
    def difficulty_name(self) -> str:
        return {
            0: "Very Easy",
            1: "Easy",
            2: "Normal",
            3: "Hard",
            4: "Very Hard",
        }[int(self.value)]




class RandomizeClassicCpuCharacters(Toggle):
    """When enabled, the client randomizes Classic Mode CPU character bytes for each fight. Classic fight location names become generic Fight 1 Win, Fight 2 Win, etc. instead of naming the vanilla opponent."""
    display_name = "Randomize Classic CPU Characters"
    default = 0


class StockThiefCount(Range):
    """Number of Stock Thief trap items in the pool."""
    display_name = "Stock Thief Count"
    range_start = 0
    range_end = 20
    default = 5


@dataclass
class SmashRemixOptions(PerGameCommonOptions):
    start_inventory_from_pool: StartInventoryPool
    starting_character: StartingCharacter
    required_classic_completions: RequiredClassicCompletions
    include_bonus_stages: IncludeBonusStages
    starting_max_stocks: StartingMaxStocks
    difficulty_checks: DifficultyChecks
    auto_check_lower_difficulties: AutoCheckLowerDifficulties
    goal_difficulty: GoalDifficulty
    randomize_classic_cpu_characters: RandomizeClassicCpuCharacters
    stock_thief_count: StockThiefCount
