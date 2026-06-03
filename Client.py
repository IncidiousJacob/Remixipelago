from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Set
import logging
import time

from NetUtils import ClientStatus

import worlds._bizhawk as bizhawk
from worlds._bizhawk.client import BizHawkClient

from .Locations import (
    CHARACTER_ID_TO_NAME,
    CHARACTER_NAME_TO_ID,
    DIFFICULTY_NAME_BY_VALUE,
    CLASSIC_FIGHTS,
    CLASSIC_FIGHT_STAGE_IDS,
    CLASSIC_FIGHT_NAME_BY_STAGE_ID,
    location_id_by_character_stage_and_difficulty,
    randomized_cpu_location_id_by_character_stage_and_difficulty,
    location_id_by_btt_character_id,
    master_hand_location_ids,
    master_hand_location_ids_by_difficulty,
)
from .Items import (
    BASE_ID as ITEM_BASE_ID,
    item_table,
    FIGHTER_PASS_ITEMS,
    PROGRESSIVE_MAX_STOCKS_ID,
    EXTRA_STOCK_ID,
    STOCK_THIEF_ID,
    PROGRESSIVE_DIFFICULTY_ID,
)

logger = logging.getLogger("BizHawkClient")

if TYPE_CHECKING:
    from worlds._bizhawk.context import BizHawkClientContext


# Same memory addresses as the Smash64 APWorld.
ADDR_GAME_STATE = 0x000A4AD0
ADDR_STAGE_ID = 0x000A4B19
ADDR_P1_CHARACTER_SELECT = 0x00138F0B
# Base-game CSS byte still mirrors the cursor/selected value in many Smash Remix menus.
# Writing both CSS bytes makes the lock actually redirect selection without touching live fighter state.
ADDR_P1_CHARACTER_SELECT_BASE = 0x0020A8CB
ADDR_P1_CLASSIC_CHARACTER = 0x000A4B3B  # read-only in Smash Remix; writing this can crash extended fighters
ADDR_BTT_CHARACTER = 0x000A4B09           # read-only in Smash Remix; writing can crash extended fighters
ADDR_P1_STOCKS = 0x000A4B43
ADDR_P1_DAMAGE = 0x0026805E
ADDR_MAX_STOCKS_SELECT = 0x00138FBB
ADDR_DIFFICULTY_SELECT = 0x00138FB7

# Classic CPU character bytes, same addresses as the Smash64 APWorld.
CLASSIC_CPU_SETUP_CHARACTER_ADDRS = (0x000A4BAF, 0x000A4C23, 0x000A4C97)
CLASSIC_CPU_SLOT_CHARACTER_ADDRS = (0x000A4BAC, 0x000A4C20, 0x000A4C94)
CLASSIC_SELECTED_CHARACTER_ADDR = 0x000A4B0A
CLASSIC_1P_MODE_CHARACTER_ADDR = 0x000A4AE7
SCREEN_CURRENT_ADDR = 0x000A4AD3
SCREEN_1P_CHARACTER_SELECT = 0x11
SCREEN_STAGE_INTRO = 0x0E
SCREEN_WIN = 0x30
SCREEN_STAGE_CLEAR = 0x33
CLASSIC_CPU_RANDOMIZE_BURST_TICKS = 180
CLASSIC_CPU_MENU_VALUE = 0x1C
# Smash Remix crashes if Classic CPU bytes are randomized for special internal
# fights that use nonstandard actor/team setup.
CLASSIC_CPU_RANDOMIZE_EXCLUDED_FIGHTS = {"Fighting Polygon Team", "Master Hand"}

SMASH_CASH_PER_FIGHT_WIN = 10
SMASH_CASH_MASTER_HAND_BONUS = 40  # total Master Hand reward becomes 50
SMASH_CASH_TAG = "SmashCash"
SMASH_CASH_STOCK_COST = 50
SMASH_CASH_HEAL_5_COST = 5
SMASH_CASH_HEAL_10_COST = 10
SMASH_CASH_HEAL_20_COST = 20
SMASH_CASH_HEAL_50_COST = 50

STATE_IN_BATTLE = 0x01
STATE_LOADING = 0x0E
STATE_RESULTS = 0x33
STATE_BTT = 0x35

CHARACTER_SELECT_VALUE_BY_NAME = CHARACTER_NAME_TO_ID
CHARACTER_NAME_BY_SELECT_VALUE = CHARACTER_ID_TO_NAME
CHARACTER_BY_ITEM_ID = {
    ITEM_BASE_ID + index: character
    for index, character in enumerate(CHARACTER_SELECT_VALUE_BY_NAME.keys(), start=1)
}


def _slot_data_starting_character(ctx: "BizHawkClientContext") -> str:
    slot_data = getattr(ctx, "slot_data", None) or {}
    starting_character = slot_data.get("starting_character", "Mario")
    if starting_character == "Random":
        return "Mario"
    return starting_character


def _smash_remix_cash_handler(ctx: "BizHawkClientContext"):
    handler = getattr(ctx, "client_handler", None)
    if handler is None or not hasattr(handler, "spend_smash_cash"):
        return None
    return handler


def _smash_remix_handler(ctx: "BizHawkClientContext"):
    handler = getattr(ctx, "client_handler", None)
    if handler is None or not hasattr(handler, "get_unlocked_character_names"):
        return None
    return handler


def cmd_smashcash(self) -> None:
    """Show Smash Cash balance and spend commands."""
    from CommonClient import logger as client_logger

    handler = _smash_remix_cash_handler(self.ctx)
    if handler is None:
        client_logger.info("Smash Remix client is not active yet. Load the patched ROM first.")
        return

    client_logger.info(f"Smash Cash is {'ON' if handler.smash_cash_enabled else 'OFF'}")
    client_logger.info(f"Smash Cash balance: {handler.smash_cash}")
    client_logger.info("Earn +10 Smash Cash for each Classic fight win, or +50 for Master Hand.")
    client_logger.info("Spend commands: /cash_stock, /cash_heal5, /cash_heal10, /cash_heal20, /cash_heal50")
    client_logger.info("Toggle command: /Money")


def cmd_money(self) -> None:
    """Toggle Smash Cash on/off and sync the SmashCash server tag."""
    from CommonClient import logger as client_logger

    handler = _smash_remix_cash_handler(self.ctx)
    if handler is None:
        client_logger.info("Smash Remix client is not active yet. Load the patched ROM first.")
        return

    handler.smash_cash_enabled = not bool(handler.smash_cash_enabled)
    handler.smash_cash_tag_sent = False
    client_logger.info(f"Smash Cash {'ON' if handler.smash_cash_enabled else 'OFF'}")
    client_logger.info("Server tag will update on the next BizHawk watcher tick.")


def cmd_smashcash_stock(self) -> None:
    """Spend 50 Smash Cash to gain one stock in the current/next Classic fight."""
    handler = _smash_remix_cash_handler(self.ctx)
    if handler is not None:
        handler.spend_smash_cash("stock", 1, SMASH_CASH_STOCK_COST)


def cmd_smashcash_heal5(self) -> None:
    """Spend 5 Smash Cash to heal 5 percent damage."""
    handler = _smash_remix_cash_handler(self.ctx)
    if handler is not None:
        handler.spend_smash_cash("heal", 5, SMASH_CASH_HEAL_5_COST)


def cmd_smashcash_heal10(self) -> None:
    """Spend 10 Smash Cash to heal 10 percent damage."""
    handler = _smash_remix_cash_handler(self.ctx)
    if handler is not None:
        handler.spend_smash_cash("heal", 10, SMASH_CASH_HEAL_10_COST)


def cmd_smashcash_heal20(self) -> None:
    """Spend 20 Smash Cash to heal 20 percent damage."""
    handler = _smash_remix_cash_handler(self.ctx)
    if handler is not None:
        handler.spend_smash_cash("heal", 20, SMASH_CASH_HEAL_20_COST)


def cmd_smashcash_heal50(self) -> None:
    """Spend 50 Smash Cash to heal 50 percent damage."""
    handler = _smash_remix_cash_handler(self.ctx)
    if handler is not None:
        handler.spend_smash_cash("heal", 50, SMASH_CASH_HEAL_50_COST)


def cmd_character(self) -> None:
    """List unlocked and locked Smash Remix characters."""
    from CommonClient import logger as client_logger

    handler = _smash_remix_handler(self.ctx)
    if handler is None:
        client_logger.info("Smash Remix client is not active yet. Load the patched ROM first.")
        return

    unlocked_names = handler.get_unlocked_character_names(self.ctx)
    unlocked = [name for name in CHARACTER_SELECT_VALUE_BY_NAME.keys() if name in unlocked_names]
    locked = [name for name in CHARACTER_SELECT_VALUE_BY_NAME.keys() if name not in unlocked_names]

    client_logger.info(f"Unlocked characters ({len(unlocked)}/{len(CHARACTER_SELECT_VALUE_BY_NAME)}): "
                       f"{', '.join(unlocked) if unlocked else 'none'}")
    client_logger.info(f"Locked characters: {', '.join(locked) if locked else 'none'}")


def cmd_goal(self) -> None:
    """Show Smash Remix Classic Mode goal progress."""
    from CommonClient import logger as client_logger

    handler = _smash_remix_handler(self.ctx)
    if handler is None:
        client_logger.info("Smash Remix client is not active yet. Load the patched ROM first.")
        return

    slot_data = getattr(self.ctx, "slot_data", None) or {}
    required = int(slot_data.get("required_classic_completions", 8) or 8)
    goal_difficulty = int(slot_data.get("goal_difficulty", 0) or 0)
    goal_difficulty_name = DIFFICULTY_NAME_BY_VALUE.get(goal_difficulty, f"Unknown {goal_difficulty}")

    checked = set(getattr(self.ctx, "checked_locations", set()) or set())
    checked.update(getattr(self.ctx, "locations_checked", set()) or set())
    checked.update(getattr(handler, "local_checked_locations", set()) or set())

    goal_master_hand_ids = master_hand_location_ids_by_difficulty.get(goal_difficulty, set())
    goal_clears = len(goal_master_hand_ids.intersection(checked))

    client_logger.info(
        f"Classic Mode clears on {goal_difficulty_name}: {goal_clears}/{required} "
        f"({'complete' if goal_clears >= required else 'incomplete'})"
    )
    if goal_clears < required:
        remaining = required - goal_clears
        client_logger.info(f"Need {remaining} more Master Hand clear{'s' if remaining != 1 else ''} on {goal_difficulty_name}.")
    else:
        client_logger.info("Goal requirement met.")


def install_smash_remix_command_processor(ctx: "BizHawkClientContext") -> None:
    commands = getattr(getattr(ctx, "command_processor", None), "commands", None)
    if commands is None:
        return

    commands["smashcash"] = cmd_smashcash
    commands["cash"] = cmd_smashcash
    commands["Money"] = cmd_money
    commands["money"] = cmd_money
    commands["cash_stock"] = cmd_smashcash_stock
    commands["cash_heal5"] = cmd_smashcash_heal5
    commands["cash_heal10"] = cmd_smashcash_heal10
    commands["cash_heal20"] = cmd_smashcash_heal20
    commands["cash_heal50"] = cmd_smashcash_heal50
    commands["character"] = cmd_character
    commands["characters"] = cmd_character
    commands["goal"] = cmd_goal


class SmashRemixBizHawkClient(BizHawkClient):
    game = "Smash Remix"
    system = "N64"
    patch_suffix = ".apsr"

    def __init__(self) -> None:
        super().__init__()
        self._prev_game_state: Optional[int] = None
        self._snapshot_stage: Optional[int] = None
        self._snapshot_character: Optional[int] = None
        self._snapshot_difficulty: Optional[int] = None
        self._snapshot_btt_char: Optional[int] = None
        self.last_classic_fight_char: Optional[int] = None
        self.classic_cpu_randomize_key: Optional[tuple[int, int, int]] = None
        self.classic_cpu_randomize_values: Optional[list[int]] = None
        self.classic_cpu_randomize_ticks = 0
        self.classic_cpu_player_key: Optional[tuple[int, int]] = None
        self.classic_cpu_next_fight_index = 0
        self.local_checked_locations: Set[int] = set()
        self.goal_sent = False

        self.last_locked_character_value: Optional[int] = None
        self.last_classic_locked_character_value: Optional[int] = None
        self.last_unlocked_character_names: Set[str] = set()
        self._last_logged_unlocked_character_names: Set[str] = set()
        self.last_locked_hover_display_value: Optional[int] = None
        self.last_locked_hover_display_time: float = 0.0
        self._last_logged_locked_character_value: Optional[int] = None

        self.last_max_stock_cap_value: Optional[int] = None
        self.last_difficulty_cap_value: Optional[int] = None
        self.last_selected_difficulty_value: Optional[int] = None
        self.last_menu_difficulty_value: Optional[int] = None
        self.processed_received_item_count: Optional[int] = None
        self.pending_stock_delta = 0
        self.pending_damage_heal = 0
        self.smash_cash = 0
        self.smash_cash_enabled = True
        self.smash_cash_tag_sent = False

    async def validate_rom(self, ctx: "BizHawkClientContext") -> bool:
        try:
            title_raw = (await bizhawk.read(ctx.bizhawk_ctx, [(0x20, 20, "ROM")]))[0]
            code_raw = (await bizhawk.read(ctx.bizhawk_ctx, [(0x3B, 4, "ROM")]))[0]
        except bizhawk.RequestFailedError:
            return False

        title = title_raw.decode("ascii", errors="ignore").strip("\0 ")
        code = code_raw.decode("ascii", errors="ignore")

        if "SMASH REMIX" not in title and code != "NALE":
            return False

        ctx.game = self.game
        ctx.client_handler = self
        ctx.items_handling = 0b111
        ctx.want_slot_data = True
        ctx.watcher_timeout = 0.016

        self._prev_game_state = None
        self._snapshot_stage = None
        self._snapshot_character = None
        self._snapshot_difficulty = None
        self._snapshot_btt_char = None
        self.last_classic_fight_char = None
        self.classic_cpu_randomize_key = None
        self.classic_cpu_randomize_values = None
        self.classic_cpu_randomize_ticks = 0
        self.classic_cpu_player_key = None
        self.classic_cpu_next_fight_index = 0
        self.local_checked_locations = set()
        self.goal_sent = False
        self.last_locked_character_value = None
        self.last_classic_locked_character_value = None
        self.last_unlocked_character_names = set()
        self._last_logged_unlocked_character_names = set()
        self.last_locked_hover_display_value = None
        self.last_locked_hover_display_time = 0.0
        self._last_logged_locked_character_value = None
        self.last_max_stock_cap_value = None
        self.last_difficulty_cap_value = None
        self.last_selected_difficulty_value = None
        self.last_menu_difficulty_value = None
        self.processed_received_item_count = None
        self.pending_stock_delta = 0
        self.pending_damage_heal = 0
        self.smash_cash = 0
        self.smash_cash_enabled = True
        self.smash_cash_tag_sent = False
        return True

    async def _burst_write_u8(self, ctx: "BizHawkClientContext", address: int, value: int, repeats: int = 12) -> int:
        packet = (address, bytes([value & 0xFF]), "RDRAM")
        for _ in range(repeats):
            await bizhawk.write(ctx.bizhawk_ctx, [packet])
        return (await bizhawk.read(ctx.bizhawk_ctx, [(address, 1, "RDRAM")]))[0][0]

    async def _send_location_check_once(self, ctx: "BizHawkClientContext", location_id: int) -> bool:
        already_checked = set(getattr(ctx, "checked_locations", set()) or set())
        already_checked.update(getattr(ctx, "locations_checked", set()) or set())
        if location_id not in self.local_checked_locations and location_id not in already_checked:
            self.local_checked_locations.add(location_id)
            await ctx.send_msgs([{"cmd": "LocationChecks", "locations": [location_id]}])
            return True
        return False

    def award_smash_cash(self, amount: int, reason: str = "") -> None:
        if not self.smash_cash_enabled:
            return
        self.smash_cash = max(0, int(self.smash_cash) + int(amount))
        if reason:
            logger.info(f"Smash Cash +{amount} ({reason}). Balance: {self.smash_cash}")
        else:
            logger.info(f"Smash Cash +{amount}. Balance: {self.smash_cash}")

    def spend_smash_cash(self, effect_type: str, amount: int, cost: int) -> bool:
        from CommonClient import logger as client_logger

        if not self.smash_cash_enabled:
            client_logger.info("Smash Cash is OFF. Use /Money to turn it on.")
            return False

        if self.smash_cash < cost:
            client_logger.info(f"Not enough Smash Cash. Need {cost}, have {self.smash_cash}.")
            return False

        self.smash_cash -= cost
        if effect_type == "stock":
            self.pending_stock_delta += int(amount)
            client_logger.info(
                f"Spent {cost} Smash Cash for +{amount} stock. Balance: {self.smash_cash}. "
                "It will apply during the current/next Classic fight."
            )
            return True

        if effect_type == "heal":
            self.pending_damage_heal += int(amount)
            client_logger.info(
                f"Spent {cost} Smash Cash to heal {amount}% damage. Balance: {self.smash_cash}. "
                "It will apply during the current/next Classic fight."
            )
            return True

        client_logger.info(f"Unknown Smash Cash effect: {effect_type}")
        self.smash_cash += cost
        return False

    async def _write_p1_percent_damage(self, ctx: "BizHawkClientContext", value: int, repeats: int = 8) -> None:
        value = max(0, min(255, int(value)))
        packet = (ADDR_P1_DAMAGE, bytes([value]), "RDRAM")
        for _ in range(repeats):
            await bizhawk.write(ctx.bizhawk_ctx, [packet])

    async def sync_smash_cash_tag(self, ctx: "BizHawkClientContext") -> None:
        # Advertise this client feature to the server/room only while enabled.
        desired_tags = set(getattr(ctx, "tags", set()) or set())
        if self.smash_cash_enabled:
            desired_tags.add(SMASH_CASH_TAG)
        else:
            desired_tags.discard(SMASH_CASH_TAG)

        current_tags = set(getattr(ctx, "tags", set()) or set())
        if current_tags != desired_tags or not self.smash_cash_tag_sent:
            ctx.tags = desired_tags
            if getattr(ctx, "server", None) and getattr(ctx.server, "socket", None) and not ctx.server.socket.closed:
                await ctx.send_msgs([{"cmd": "ConnectUpdate", "tags": list(desired_tags)}])
            self.smash_cash_tag_sent = True

    def _extract_network_item_id(self, network_item) -> Optional[int]:
        try:
            return int(network_item.item)
        except Exception:
            pass

        if isinstance(network_item, dict):
            try:
                return int(network_item.get("item"))
            except Exception:
                return None

        if isinstance(network_item, (list, tuple)) and network_item:
            try:
                return int(network_item[0])
            except Exception:
                return None

        return None

    def _character_from_received_item(self, ctx: "BizHawkClientContext", item_id: int) -> Optional[str]:
        # Same method as the working Smash64 APWorld, expanded to the Remix roster:
        # Fighter Pass item ids are BASE_ID + character index in the stable
        # character order. Do not rely on item_names lookup or ReceivedItems
        # packet parsing for the normal path.
        character = CHARACTER_BY_ITEM_ID.get(int(item_id))
        if character is not None:
            return character

        # Compatibility fallback: ask AP's item-name table and parse "X Fighter Pass".
        item_name = None
        item_names = getattr(ctx, "item_names", None)
        if item_names is not None:
            for method_name in ("lookup_in_game", "lookup_in_slot", "lookup_in_world"):
                method = getattr(item_names, method_name, None)
                if method is None:
                    continue
                try:
                    if method_name == "lookup_in_slot":
                        item_name = method(item_id, getattr(ctx, "slot", None))
                    else:
                        item_name = method(item_id)
                except Exception:
                    item_name = None
                if item_name:
                    break

        if isinstance(item_name, str) and item_name.endswith(" Fighter Pass"):
            candidate = item_name[:-len(" Fighter Pass")]
            if candidate in CHARACTER_SELECT_VALUE_BY_NAME:
                return candidate

        return None

    def get_unlocked_character_names(self, ctx: "BizHawkClientContext") -> Set[str]:
        # Direct copy of the proven Smash64 pattern, with the Remix roster:
        # starting character from slot_data + every received Fighter Pass.
        unlocked: Set[str] = set()

        starting_character = _slot_data_starting_character(ctx)
        if starting_character in CHARACTER_SELECT_VALUE_BY_NAME:
            unlocked.add(starting_character)

        for network_item in getattr(ctx, "items_received", []):
            try:
                item_id = int(network_item.item)
            except Exception:
                continue
            character = self._character_from_received_item(ctx, item_id)
            if character is not None:
                unlocked.add(character)

        if not unlocked:
            unlocked.add("Mario")

        return unlocked

    async def _clamp_character_byte(
        self,
        ctx: "BizHawkClientContext",
        address: int,
        fallback_value: int,
        unlocked_values: Set[int],
    ) -> Optional[int]:
        current_value = (await bizhawk.read(ctx.bizhawk_ctx, [(address, 1, "RDRAM")]))[0][0]
        if current_value in CHARACTER_NAME_BY_SELECT_VALUE and current_value not in unlocked_values:
            await self._burst_write_u8(ctx, address, fallback_value)
            return current_value
        return None

    async def _display_locked_hover_message(
        self,
        ctx: "BizHawkClientContext",
        current_value: int,
        unlocked_values: Set[int],
    ) -> None:
        # Disabled for Smash Remix. The selector byte can hold stale locked
        # values during fights and transitions, causing LOCKED overlay spam.
        self.last_locked_hover_display_value = None
        return

    async def enforce_character_locks(self, ctx: "BizHawkClientContext") -> None:
        # Same unlock detection as the working Smash64-expanded build, but do
        # not spam LOCKED overlays and do not write during fights/loading/results.
        unlocked_names = self.get_unlocked_character_names(ctx)
        unlocked_values = {
            CHARACTER_SELECT_VALUE_BY_NAME[name]
            for name in unlocked_names
            if name in CHARACTER_SELECT_VALUE_BY_NAME
        }
        if not unlocked_values:
            return

        starting_character = _slot_data_starting_character(ctx)
        fallback_value = CHARACTER_SELECT_VALUE_BY_NAME.get(starting_character)
        if fallback_value not in unlocked_values:
            fallback_value = min(unlocked_values)

        self.last_unlocked_character_names = set(unlocked_names)

        if getattr(self, "_last_logged_unlocked_character_names", None) != unlocked_names:
            logger.info(
                "Smash Remix unlocked characters: "
                + (", ".join(sorted(unlocked_names)) if unlocked_names else "none")
            )
            self._last_logged_unlocked_character_names = set(unlocked_names)

        game_state, current_css_value = [x[0] for x in await bizhawk.read(ctx.bizhawk_ctx, [
            (ADDR_GAME_STATE, 1, "RDRAM"),
            (ADDR_P1_CHARACTER_SELECT, 1, "RDRAM"),
        ])]

        # Between Classic fights this selector byte can be stale. Do not display
        # LOCKED or clamp while the game is in active Classic flow states.
        if game_state in {STATE_IN_BATTLE, STATE_LOADING, STATE_RESULTS, STATE_BTT}:
            self.last_locked_character_value = None
            self.last_classic_locked_character_value = None
            return

        locked_css = await self._clamp_character_byte(
            ctx,
            ADDR_P1_CHARACTER_SELECT,
            fallback_value,
            unlocked_values,
        )
        self.last_locked_character_value = locked_css

        # Do not clamp ADDR_P1_CLASSIC_CHARACTER in Smash Remix. Writing Remix
        # character IDs there can trigger TL exception crashes.
        self.last_classic_locked_character_value = None

        if locked_css is not None:
            if getattr(self, "_last_logged_locked_character_value", None) != locked_css:
                locked_name = CHARACTER_NAME_BY_SELECT_VALUE.get(locked_css, f"ID {locked_css}")
                fallback_name = CHARACTER_NAME_BY_SELECT_VALUE.get(fallback_value, f"ID {fallback_value}")
                logger.info(f"Smash Remix character locked: {locked_name} -> {fallback_name}")
                self._last_logged_locked_character_value = locked_css
        else:
            self._last_logged_locked_character_value = None

    def _get_progressive_count(self, ctx: "BizHawkClientContext", item_id: int) -> int:
        count = 0
        for network_item in getattr(ctx, "items_received", []):
            try:
                if int(network_item.item) == item_id:
                    count += 1
            except Exception:
                continue
        return count

    async def handle_progressive_max_stocks(self, ctx: "BizHawkClientContext") -> None:
        slot_data = getattr(ctx, "slot_data", None) or {}
        starting_max_stocks = int(slot_data.get("starting_max_stocks", 1) or 1)
        cap = max(0, min(4, (starting_max_stocks - 1) + self._get_progressive_count(ctx, PROGRESSIVE_MAX_STOCKS_ID)))
        self.last_max_stock_cap_value = cap

        current_select = (await bizhawk.read(ctx.bizhawk_ctx, [(ADDR_MAX_STOCKS_SELECT, 1, "RDRAM")]))[0][0]
        if 0 <= current_select <= 4 and current_select > cap:
            await self._burst_write_u8(ctx, ADDR_MAX_STOCKS_SELECT, cap, repeats=12)

    def _get_enabled_difficulty_values(self, ctx: "BizHawkClientContext") -> Set[int]:
        slot_data = getattr(ctx, "slot_data", None) or {}
        raw_values = slot_data.get("difficulty_checks", None)
        if raw_values is None:
            return {0, 1, 2, 3, 4}

        values = set()
        for value in raw_values:
            try:
                difficulty_value = int(value)
            except (TypeError, ValueError):
                continue
            if 0 <= difficulty_value <= 4:
                values.add(difficulty_value)
        return values or {0}

    def _get_difficulty_cap_value(self, ctx: "BizHawkClientContext") -> int:
        slot_data = getattr(ctx, "slot_data", None) or {}
        base_cap = int(slot_data.get("starting_difficulty_cap", 0) or 0)
        count = self._get_progressive_count(ctx, PROGRESSIVE_DIFFICULTY_ID)
        return max(0, min(4, base_cap + count))

    def _get_allowed_difficulty_for_selector(self, ctx: "BizHawkClientContext") -> int:
        enabled = sorted(self._get_enabled_difficulty_values(ctx))
        cap = self._get_difficulty_cap_value(ctx)
        unlocked_enabled = [value for value in enabled if value <= cap]
        if unlocked_enabled:
            return max(unlocked_enabled)
        return min(enabled)

    async def handle_progressive_difficulty(self, ctx: "BizHawkClientContext") -> None:
        max_allowed = self._get_difficulty_cap_value(ctx)
        self.last_difficulty_cap_value = max_allowed

        enabled = self._get_enabled_difficulty_values(ctx)
        target_select = self._get_allowed_difficulty_for_selector(ctx)

        game_state, current_select = [x[0] for x in await bizhawk.read(ctx.bizhawk_ctx, [
            (ADDR_GAME_STATE, 1, "RDRAM"),
            (ADDR_DIFFICULTY_SELECT, 1, "RDRAM"),
        ])]

        in_classic_gameplay_state = game_state in {STATE_IN_BATTLE, STATE_LOADING, STATE_RESULTS, STATE_BTT}

        # Outside Classic gameplay, this byte is the real selector. Remember it.
        if not in_classic_gameplay_state:
            if 0 <= current_select <= 4 and current_select in enabled and current_select <= max_allowed:
                self.last_selected_difficulty_value = current_select
                self.last_menu_difficulty_value = current_select
            elif 0 <= current_select <= 4 and (current_select not in enabled or current_select > max_allowed):
                await self._burst_write_u8(ctx, ADDR_DIFFICULTY_SELECT, target_select, repeats=12)
                self.last_selected_difficulty_value = target_select
                self.last_menu_difficulty_value = target_select
        else:
            # During Remix Classic flow, 0x138FB7 can read back as 0 even when the
            # player selected a higher difficulty. Do not let that stale 0 erase
            # the remembered menu difficulty. Only accept a non-zero gameplay
            # value when it is legal.
            if (
                0 < current_select <= 4
                and current_select in enabled
                and current_select <= max_allowed
            ):
                self.last_selected_difficulty_value = current_select

        if self.last_selected_difficulty_value is None:
            self.last_selected_difficulty_value = self.last_menu_difficulty_value

        if self.last_selected_difficulty_value is None:
            self.last_selected_difficulty_value = target_select

    def _is_classic_cpu_randomizer_enabled(self, ctx: "BizHawkClientContext") -> bool:
        slot_data = getattr(ctx, "slot_data", None) or {}
        return bool(slot_data.get("randomize_classic_cpu_characters", False))

    def _get_active_classic_location_map(self, ctx: "BizHawkClientContext"):
        if self._is_classic_cpu_randomizer_enabled(ctx):
            return randomized_cpu_location_id_by_character_stage_and_difficulty
        return location_id_by_character_stage_and_difficulty

    def _clamp_classic_cpu_character_value(self, value: int) -> int:
        value = int(value)
        if value not in CHARACTER_NAME_BY_SELECT_VALUE:
            return 0
        return value

    def _get_classic_cpu_randomizer_values(
        self,
        ctx: "BizHawkClientContext",
        char_id: int,
        stage_id: int,
        difficulty_value: int,
    ) -> Optional[list[int]]:
        slot_data = getattr(ctx, "slot_data", None) or {}
        table = slot_data.get("classic_cpu_randomizer_table", {}) or {}
        raw_values = table.get(f"{int(char_id)}:{int(stage_id)}:{int(difficulty_value)}")
        if not raw_values:
            return None

        values: list[int] = []
        for raw in list(raw_values)[:3]:
            try:
                value = self._clamp_classic_cpu_character_value(int(raw))
            except (TypeError, ValueError):
                continue
            if value in CHARACTER_NAME_BY_SELECT_VALUE:
                values.append(value)

        if not values:
            return None
        while len(values) < 3:
            values.append(values[-1])
        return values[:3]

    def _get_classic_cpu_randomizer_values_for_fight_index(
        self,
        ctx: "BizHawkClientContext",
        char_id: int,
        difficulty_value: int,
        fight_index: int,
    ) -> Optional[list[int]]:
        if fight_index < 0 or fight_index >= len(CLASSIC_FIGHTS):
            return None
        fight_name = CLASSIC_FIGHTS[fight_index]
        if fight_name == "Master Hand":
            return None
        stage_id = CLASSIC_FIGHT_STAGE_IDS.get(fight_name)
        if stage_id is None:
            return None
        return self._get_classic_cpu_randomizer_values(ctx, char_id, stage_id, difficulty_value)

    async def _write_classic_cpu_characters(self, ctx: "BizHawkClientContext", values: list[int], repeats: int = 1) -> None:
        clamped_values = [self._clamp_classic_cpu_character_value(value) for value in values[:3]]
        if not clamped_values:
            return
        while len(clamped_values) < 3:
            clamped_values.append(clamped_values[-1])

        writes = []
        for addr_group in (CLASSIC_CPU_SETUP_CHARACTER_ADDRS, CLASSIC_CPU_SLOT_CHARACTER_ADDRS):
            writes.extend(
                (address, bytes([int(value) & 0xFF]), "RDRAM")
                for address, value in zip(addr_group, clamped_values[:3])
            )
        for _ in range(max(1, int(repeats))):
            await bizhawk.write(ctx.bizhawk_ctx, writes)

    def _cpu_slots_are_menu_values(self, cpu_values: list[int]) -> bool:
        return bool(cpu_values) and int(cpu_values[0]) == CLASSIC_CPU_MENU_VALUE

    def _is_cpu_randomizer_fight_excluded_by_name(self, fight_name: str | None) -> bool:
        return fight_name in CLASSIC_CPU_RANDOMIZE_EXCLUDED_FIGHTS

    def _is_cpu_randomizer_fight_index_excluded(self, fight_index: int) -> bool:
        if fight_index < 0 or fight_index >= len(CLASSIC_FIGHTS):
            return True
        return self._is_cpu_randomizer_fight_excluded_by_name(CLASSIC_FIGHTS[fight_index])

    def _clear_classic_cpu_randomizer(self) -> None:
        self.classic_cpu_randomize_key = None
        self.classic_cpu_randomize_values = None
        self.classic_cpu_randomize_ticks = 0

    async def _prime_classic_cpu_randomizer_for_next_fight(
        self,
        ctx: "BizHawkClientContext",
        char_id: int,
        difficulty_value: int,
        fight_index: int,
        repeats: int = 8,
    ) -> None:
        if not self._is_classic_cpu_randomizer_enabled(ctx):
            return
        if self._is_cpu_randomizer_fight_index_excluded(int(fight_index)):
            self._clear_classic_cpu_randomizer()
            return
        values = self._get_classic_cpu_randomizer_values_for_fight_index(ctx, char_id, difficulty_value, fight_index)
        if values is None:
            return
        self.classic_cpu_next_fight_index = fight_index
        self.classic_cpu_randomize_key = (int(char_id), int(fight_index), int(difficulty_value))
        self.classic_cpu_randomize_values = values
        self.classic_cpu_randomize_ticks = max(self.classic_cpu_randomize_ticks, int(repeats), 1)

    async def _advance_classic_cpu_randomizer_after_fight_win(
        self,
        ctx: "BizHawkClientContext",
        char_id: int,
        difficulty_value: int,
        cleared_stage_id: int,
    ) -> None:
        fight_name = CLASSIC_FIGHT_NAME_BY_STAGE_ID.get(cleared_stage_id)
        if fight_name not in CLASSIC_FIGHTS:
            return
        next_fight_index = CLASSIC_FIGHTS.index(fight_name) + 1
        while (
            next_fight_index < len(CLASSIC_FIGHTS)
            and self._is_cpu_randomizer_fight_index_excluded(next_fight_index)
        ):
            next_fight_index += 1
        if next_fight_index >= len(CLASSIC_FIGHTS):
            self.classic_cpu_randomize_key = None
            self.classic_cpu_randomize_values = None
            self.classic_cpu_randomize_ticks = 0
            return
        await self._prime_classic_cpu_randomizer_for_next_fight(
            ctx, char_id, difficulty_value, next_fight_index, repeats=CLASSIC_CPU_RANDOMIZE_BURST_TICKS
        )

    async def handle_classic_cpu_randomizer(self, ctx: "BizHawkClientContext") -> None:
        if not self._is_classic_cpu_randomizer_enabled(ctx):
            self.classic_cpu_randomize_key = None
            self.classic_cpu_randomize_values = None
            self.classic_cpu_randomize_ticks = 0
            self.classic_cpu_player_key = None
            self.classic_cpu_next_fight_index = 0
            return

        read_values = await bizhawk.read(ctx.bizhawk_ctx, [
            (ADDR_GAME_STATE, 1, "RDRAM"),
            (ADDR_STAGE_ID, 1, "RDRAM"),
            (ADDR_P1_CLASSIC_CHARACTER, 1, "RDRAM"),
            (SCREEN_CURRENT_ADDR, 1, "RDRAM"),
            (CLASSIC_SELECTED_CHARACTER_ADDR, 1, "RDRAM"),
            (CLASSIC_1P_MODE_CHARACTER_ADDR, 1, "RDRAM"),
            *[(address, 1, "RDRAM") for address in CLASSIC_CPU_SETUP_CHARACTER_ADDRS],
            *[(address, 1, "RDRAM") for address in CLASSIC_CPU_SLOT_CHARACTER_ADDRS],
        ])
        game_state = read_values[0][0]
        stage_id = read_values[1][0]
        char_id = read_values[2][0]
        screen_id = read_values[3][0]
        selected_char_id = read_values[4][0]
        one_p_mode_char_id = read_values[5][0]
        cpu_values = [entry[0] for entry in read_values[6:]]

        # Smash Remix is much more fragile than base Smash 64 during bonus/loading/result
        # states. Do not write Classic CPU bytes while Break the Targets / bonus
        # screens are active or while the game is between fights. This was causing
        # TL exception crashes on the Target bonus screen.
        if game_state in {STATE_BTT, STATE_LOADING, STATE_RESULTS}:
            return
        if screen_id not in {SCREEN_1P_CHARACTER_SELECT, SCREEN_STAGE_INTRO} and stage_id not in CLASSIC_FIGHT_NAME_BY_STAGE_ID:
            return

        current_fight_name = CLASSIC_FIGHT_NAME_BY_STAGE_ID.get(stage_id)
        if self._is_cpu_randomizer_fight_excluded_by_name(current_fight_name):
            self._clear_classic_cpu_randomizer()
            return

        if screen_id == SCREEN_1P_CHARACTER_SELECT:
            if selected_char_id in CHARACTER_NAME_BY_SELECT_VALUE:
                char_id = selected_char_id
            elif one_p_mode_char_id in CHARACTER_NAME_BY_SELECT_VALUE:
                char_id = one_p_mode_char_id

        difficulty_value = self.last_selected_difficulty_value
        enabled_difficulties = self._get_enabled_difficulty_values(ctx)
        if difficulty_value not in enabled_difficulties:
            difficulty_value = self._get_allowed_difficulty_for_selector(ctx)
        if difficulty_value not in enabled_difficulties or char_id not in CHARACTER_NAME_BY_SELECT_VALUE:
            self.classic_cpu_randomize_key = None
            self.classic_cpu_randomize_values = None
            self.classic_cpu_randomize_ticks = 0
            return

        player_key = (int(char_id), int(difficulty_value))
        if self.classic_cpu_player_key != player_key:
            self.classic_cpu_player_key = player_key
            self.classic_cpu_next_fight_index = 0
            await self._prime_classic_cpu_randomizer_for_next_fight(
                ctx, char_id, difficulty_value, 0, repeats=CLASSIC_CPU_RANDOMIZE_BURST_TICKS
            )

        if game_state == STATE_IN_BATTLE and stage_id in CLASSIC_FIGHT_NAME_BY_STAGE_ID:
            fight_name = CLASSIC_FIGHT_NAME_BY_STAGE_ID.get(stage_id)
            if fight_name in CLASSIC_FIGHTS:
                next_index = min(CLASSIC_FIGHTS.index(fight_name) + 1, len(CLASSIC_FIGHTS) - 1)
                while next_index < len(CLASSIC_FIGHTS) and self._is_cpu_randomizer_fight_index_excluded(next_index):
                    next_index += 1
                self.classic_cpu_next_fight_index = min(next_index, len(CLASSIC_FIGHTS) - 1)
        elif stage_id in CLASSIC_FIGHT_NAME_BY_STAGE_ID:
            fight_name = CLASSIC_FIGHT_NAME_BY_STAGE_ID.get(stage_id)
            if fight_name in CLASSIC_FIGHTS and not self._is_cpu_randomizer_fight_excluded_by_name(fight_name):
                fight_index = CLASSIC_FIGHTS.index(fight_name)
                key = (int(char_id), int(fight_index), int(difficulty_value))
                if self.classic_cpu_randomize_key != key or self.classic_cpu_randomize_values is None:
                    await self._prime_classic_cpu_randomizer_for_next_fight(
                        ctx, char_id, difficulty_value, fight_index, repeats=CLASSIC_CPU_RANDOMIZE_BURST_TICKS
                    )

        if self.classic_cpu_randomize_ticks <= 0 or not self.classic_cpu_randomize_values:
            return

        safe_to_write_cpu_bytes = (
            screen_id in {SCREEN_1P_CHARACTER_SELECT, SCREEN_STAGE_INTRO}
            or (stage_id in CLASSIC_FIGHT_NAME_BY_STAGE_ID and self._cpu_slots_are_menu_values(cpu_values))
        )
        if safe_to_write_cpu_bytes:
            await self._write_classic_cpu_characters(ctx, self.classic_cpu_randomize_values, repeats=1)

    def _is_classic_fight_state(self, game_state: int, stage_id: int) -> bool:
        return game_state == STATE_IN_BATTLE and stage_id in CLASSIC_FIGHT_NAME_BY_STAGE_ID

    async def handle_stock_items(self, ctx: "BizHawkClientContext") -> None:
        items_received = list(getattr(ctx, "items_received", []))
        if self.processed_received_item_count is None:
            self.processed_received_item_count = 0

        for network_item in items_received[self.processed_received_item_count:]:
            try:
                item_id = int(network_item.item)
            except Exception:
                continue
            if item_id == EXTRA_STOCK_ID:
                self.pending_stock_delta += 1
            elif item_id == STOCK_THIEF_ID:
                self.pending_stock_delta -= 1

        self.processed_received_item_count = len(items_received)

        game_state, stage_id = [x[0] for x in await bizhawk.read(ctx.bizhawk_ctx, [
            (ADDR_GAME_STATE, 1, "RDRAM"),
            (ADDR_STAGE_ID, 1, "RDRAM"),
        ])]
        if not self._is_classic_fight_state(game_state, stage_id):
            return

        if self.pending_damage_heal > 0:
            current_damage = (await bizhawk.read(ctx.bizhawk_ctx, [(ADDR_P1_DAMAGE, 1, "RDRAM")]))[0][0]
            heal_amount = int(self.pending_damage_heal)
            new_damage = max(0, current_damage - heal_amount)
            await self._write_p1_percent_damage(ctx, new_damage, repeats=12)
            logger.info(f"Applied Smash Cash heal: {current_damage}% -> {new_damage}%")
            self.pending_damage_heal = 0

        if self.pending_stock_delta == 0:
            return

        current_stocks = (await bizhawk.read(ctx.bizhawk_ctx, [(ADDR_P1_STOCKS, 1, "RDRAM")]))[0][0]
        if current_stocks == 0xFF:
            return

        if self.pending_stock_delta > 0:
            new_stocks = max(0, min(4, current_stocks + self.pending_stock_delta))
            await self._burst_write_u8(ctx, ADDR_P1_STOCKS, new_stocks, repeats=12)
            logger.info(f"Applied Smash Cash/stock item: stocks {current_stocks} -> {new_stocks}")
            self.pending_stock_delta = 0
        elif self.pending_stock_delta < 0:
            if 1 <= current_stocks <= 4:
                new_stocks = current_stocks - 1
                await self._burst_write_u8(ctx, ADDR_P1_STOCKS, new_stocks, repeats=12)
            self.pending_stock_delta += 1

    async def _force_btt_character_from_last_classic_fight(
        self,
        ctx: "BizHawkClientContext",
        current_btt_char: int,
    ) -> int:
        # Smash64 can safely force the BTT character byte, but Smash Remix can
        # crash on load if extended character IDs are written into Classic/BTT
        # state bytes. Keep this read-only and only use the last normal Classic
        # fighter as a fallback for check attribution.
        if self.last_classic_fight_char in CHARACTER_NAME_BY_SELECT_VALUE:
            return self.last_classic_fight_char
        return current_btt_char

    async def handle_classic_stage_checks(self, ctx: "BizHawkClientContext") -> None:
        game_state, stage_id, char_id, difficulty_value, btt_char_id = [x[0] for x in await bizhawk.read(ctx.bizhawk_ctx, [
            (ADDR_GAME_STATE, 1, "RDRAM"),
            (ADDR_STAGE_ID, 1, "RDRAM"),
            (ADDR_P1_CLASSIC_CHARACTER, 1, "RDRAM"),
            (ADDR_DIFFICULTY_SELECT, 1, "RDRAM"),
            (ADDR_BTT_CHARACTER, 1, "RDRAM"),
        ])]

        if game_state == STATE_IN_BATTLE and self._prev_game_state != STATE_IN_BATTLE:
            self._snapshot_stage = stage_id
            self._snapshot_character = char_id if char_id in CHARACTER_NAME_BY_SELECT_VALUE else None

            enabled_difficulties = self._get_enabled_difficulty_values(ctx)

            # Prefer the remembered menu difficulty. In Smash Remix the raw
            # difficulty byte often becomes 0 during battle/results, which caused
            # only Very Easy checks to send. If the raw byte is a legal non-zero
            # value at battle start, use it as a fresh correction.
            remembered_difficulty = self.last_selected_difficulty_value
            if (
                0 < difficulty_value <= 4
                and difficulty_value in enabled_difficulties
                and difficulty_value <= self._get_difficulty_cap_value(ctx)
            ):
                remembered_difficulty = difficulty_value
                self.last_selected_difficulty_value = difficulty_value

            if remembered_difficulty not in enabled_difficulties:
                remembered_difficulty = self.last_menu_difficulty_value

            if remembered_difficulty not in enabled_difficulties:
                remembered_difficulty = self._get_allowed_difficulty_for_selector(ctx)

            self._snapshot_difficulty = remembered_difficulty

            if char_id in CHARACTER_NAME_BY_SELECT_VALUE and stage_id in CLASSIC_FIGHT_NAME_BY_STAGE_ID:
                self.last_classic_fight_char = char_id

            char_name = CHARACTER_NAME_BY_SELECT_VALUE.get(self._snapshot_character, "Unknown")
            difficulty_name = DIFFICULTY_NAME_BY_VALUE.get(self._snapshot_difficulty, "Unknown")
            fight_name = CLASSIC_FIGHT_NAME_BY_STAGE_ID.get(stage_id, f"stage {stage_id:02X}")
            logger.info(
                f"Smash Remix Classic battle detected: {char_name} / {difficulty_name} / {fight_name} "
                f"(raw difficulty={difficulty_value}, remembered={self.last_selected_difficulty_value})"
            )

        if game_state == STATE_RESULTS and self._prev_game_state != STATE_RESULTS:
            if (
                self._snapshot_stage is not None
                and self._snapshot_character is not None
                and self._snapshot_difficulty is not None
            ):
                enabled_difficulties = self._get_enabled_difficulty_values(ctx)
                if self._snapshot_difficulty in enabled_difficulties:
                    active_location_map = self._get_active_classic_location_map(ctx)
                    location_id = active_location_map.get((
                        self._snapshot_character,
                        self._snapshot_stage,
                        self._snapshot_difficulty,
                    ))
                    if location_id is not None:
                        await self._send_location_check_once(ctx, location_id)
                        await self._advance_classic_cpu_randomizer_after_fight_win(
                            ctx, self._snapshot_character, self._snapshot_difficulty, self._snapshot_stage
                        )

                    slot_data = getattr(ctx, "slot_data", None) or {}
                    if bool(slot_data.get("auto_check_lower_difficulties", False)):
                        for lower_difficulty in sorted(enabled_difficulties):
                            if lower_difficulty >= self._snapshot_difficulty:
                                continue
                            lower_location_id = self._get_active_classic_location_map(ctx).get((
                                self._snapshot_character,
                                self._snapshot_stage,
                                lower_difficulty,
                            ))
                            if lower_location_id is not None:
                                await self._send_location_check_once(ctx, lower_location_id)

                    if self._snapshot_stage in CLASSIC_FIGHT_NAME_BY_STAGE_ID:
                        fight_name = CLASSIC_FIGHT_NAME_BY_STAGE_ID.get(self._snapshot_stage, "Classic fight")
                        reward = SMASH_CASH_PER_FIGHT_WIN
                        if fight_name == "Master Hand":
                            reward += SMASH_CASH_MASTER_HAND_BONUS
                        self.award_smash_cash(reward, f"{fight_name} win")

            self._snapshot_stage = None
            self._snapshot_character = None
            self._snapshot_difficulty = None

        slot_data = getattr(ctx, "slot_data", None) or {}
        include_bonus_stages = bool(slot_data.get("include_bonus_stages", True))
        if include_bonus_stages:
            if game_state == STATE_BTT:
                btt_char_id = await self._force_btt_character_from_last_classic_fight(ctx, btt_char_id)
                if self._prev_game_state != STATE_BTT:
                    self._snapshot_btt_char = btt_char_id
                elif self._snapshot_btt_char is None:
                    self._snapshot_btt_char = btt_char_id

            if self._prev_game_state == STATE_BTT and game_state != STATE_BTT:
                if self._snapshot_btt_char is not None:
                    location_id = location_id_by_btt_character_id.get(self._snapshot_btt_char)
                    if location_id is not None:
                        await self._send_location_check_once(ctx, location_id)
                self._snapshot_btt_char = None
        else:
            self._snapshot_btt_char = None

        # Important: update the previous state from the same RAM snapshot this
        # handler actually processed. A later re-read in game_watcher can catch
        # a transition that this handler did not process yet, which skips result
        # checks entirely.
        self._prev_game_state = game_state

    async def check_goal(self, ctx: "BizHawkClientContext") -> None:
        if self.goal_sent:
            return

        slot_data = getattr(ctx, "slot_data", None) or {}
        required = int(slot_data.get("required_classic_completions", 8) or 8)
        goal_difficulty = int(slot_data.get("goal_difficulty", 0) or 0)

        checked = set(getattr(ctx, "checked_locations", set()) or set())
        checked.update(getattr(ctx, "locations_checked", set()) or set())
        checked.update(self.local_checked_locations)

        goal_master_hand_ids = master_hand_location_ids_by_difficulty.get(goal_difficulty, set())
        goal_clears = len(goal_master_hand_ids.intersection(checked))
        if goal_clears >= required:
            await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
            self.goal_sent = True

    async def on_package(self, ctx: "BizHawkClientContext", cmd: str, args: dict) -> None:
        # Unlocks use the same proven Smash64 path from ctx.items_received.
        # When ReceivedItems arrives, just force the unlocked-character log to refresh.
        if cmd == "ReceivedItems" and args.get("items"):
            self._last_logged_unlocked_character_names = set()

    async def game_watcher(self, ctx: "BizHawkClientContext") -> None:
        try:
            install_smash_remix_command_processor(ctx)
            await self.sync_smash_cash_tag(ctx)
            await self.handle_progressive_difficulty(ctx)
            await self.handle_progressive_max_stocks(ctx)
            await self.handle_stock_items(ctx)
            await self.handle_classic_cpu_randomizer(ctx)
            await self.handle_classic_stage_checks(ctx)
            await self.enforce_character_locks(ctx)
            await self.check_goal(ctx)
        except bizhawk.RequestFailedError:
            pass
