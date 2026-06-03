from __future__ import annotations

from typing import BinaryIO, Optional, cast
import hashlib
import os

import Utils
from worlds.Files import APProcedurePatch, APTokenMixin


SMASH_REMIX_MD5 = "2b2d6b295106c54216b7fc7a2f14346e"
SMASH_REMIX_SHA1 = "13716381ed5e29be2606e0f4724b18fd00789d04"
EXPECTED_ROM_NAMES = (
    "Smash Remix 2.0.1.z64",
    "smash_remix_2.0.1.z64",
    "Smash Remix.z64",
)


class SmashRemixPatch(APProcedurePatch, APTokenMixin):
    """Archipelago patch container for Smash Remix.

    This is currently a no-ROM-changes procedure patch. Unlike APDeltaPatch,
    it does not need the clean ROM while generating the multiworld. The ROM is
    only requested when the player opens/applies the .apsr patch file.
    """

    hash = SMASH_REMIX_MD5
    game = "Smash Remix"
    patch_file_ending = ".apsr"
    result_file_ending = ".z64"
    procedure = [("apply_tokens", ["token_data.bin"])]

    @classmethod
    def get_source_data(cls) -> bytes:
        with open(get_base_rom_path(), "rb") as stream:
            return read_rom(stream)

    def write_contents(self, opened_zipfile) -> None:
        # Empty token data means the output ROM is an exact copy of the clean
        # Smash Remix ROM. Later ROM edits can be added with self.write_token().
        self.write_file("token_data.bin", self.get_token_binary())
        super().write_contents(opened_zipfile)


def _verify_rom_path(path: str) -> str:
    with open(path, "rb") as rom:
        digest = hashlib.md5(rom.read()).hexdigest()
    if digest != SMASH_REMIX_MD5:
        raise Exception(
            f"Smash Remix ROM has MD5 {digest}, expected {SMASH_REMIX_MD5}. "
            "Use the exact Smash Remix 2.0.1 .z64 ROM."
        )
    return path


def _ask_for_rom_path() -> Optional[str]:
    """Open a file picker when applying the patch through the AP Launcher.

    This keeps generation from needing a rom_file option. If the patcher is run
    in a headless environment, the dialog may not be available and we simply
    fall back to the normal error message.
    """

    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="Select clean Smash Remix 2.0.1 ROM",
            filetypes=[("Nintendo 64 ROM", "*.z64 *.n64 *.v64"), ("All files", "*.*")],
        )
        root.destroy()
        return path or None
    except Exception:
        return None


def get_base_rom_path(file_name: Optional[str] = None) -> str:
    """Find the user's clean Smash Remix 2.0.1 ROM.

    This function is only called while applying/opening the generated .apsr
    patch, not during multiworld generation.

    Optional setup if the file picker is not available:

        smash_remix_options:
          rom_file: "C:/path/to/Smash Remix 2.0.1.z64"
    """

    if not file_name:
        options = Utils.get_options()
        file_name = cast(str, options.get("smash_remix_options", {}).get("rom_file", ""))

    candidates = []
    if file_name:
        candidates.append(file_name)
        candidates.append(Utils.user_path(file_name))

    for name in EXPECTED_ROM_NAMES:
        candidates.append(name)
        candidates.append(Utils.user_path(name))

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return _verify_rom_path(candidate)

    selected_path = _ask_for_rom_path()
    if selected_path:
        return _verify_rom_path(selected_path)

    raise FileNotFoundError(
        "Could not find Smash Remix 2.0.1.z64. Open the .apsr patch again and "
        "select your clean Smash Remix 2.0.1 ROM, place it next to Archipelago "
        "as 'Smash Remix 2.0.1.z64', or add this to host.yaml/options.yaml: "
        'smash_remix_options: {rom_file: "C:/path/to/Smash Remix 2.0.1.z64"}'
    )


def read_rom(stream: BinaryIO) -> bytes:
    return stream.read()


def make_patch(world, output_directory: str) -> str:
    """Create a standard AP patch output for this player without needing a ROM."""

    base_name = world.multiworld.get_out_file_name_base(world.player)
    patch_path = os.path.join(output_directory, f"{base_name}{SmashRemixPatch.patch_file_ending}")

    patch = SmashRemixPatch(
        path=patch_path,
        player=world.player,
        player_name=world.multiworld.player_name[world.player],
    )
    patch.write()
    return patch_path
