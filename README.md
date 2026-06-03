# Smash Remix APWorld

This Smash Remix 2.0.1 APWorld is focused on per-character Classic Mode checks, with Fighter Pass items now included.

## Included checks

Each listed character has these Classic Mode locations:

1. Defeat Link
2. Defeat Yoshi Team
3. Complete Break the Targets
4. Defeat Fox
5. Defeat Mario Bros.
6. Complete Board the Platforms
7. Defeat Pikachu
8. Defeat Giant DK
9. Complete Race to the Finish
10. Defeat Kirby Team
11. Defeat Samus
12. Defeat Metal Mario
13. Defeat Fighting Polygon Team
14. Defeat Master Hand
15. Clear Classic Mode

## Fighter Pass items

The item pool includes one progression Fighter Pass for every supported character:

Mario, Fox, DK, Samus, Luigi, Link, Yoshi, Captain Falcon, Kirby, Pikachu,
Jigglypuff, Ness, Falco, Ganondorf, Young Link, Dr. Mario, Wario, Bowser,
Wolf, Conker, Mewtwo, Marth, Sonic, Sheik, Marina, King Dedede, Goemon,
Banjo & Kazooie, Crash, and Peach.

For this build, the passes are in the pool but do not yet restrict location logic. This keeps generation simple while the BizHawk client is being wired. The client can use these items later to lock character selection.

## Known RAM addresses

- `0x138F0B`: character select screen value.
- `0x22AAB8`: actual in-game Player 1 character value.

The next step is wiring the BizHawk client to the base-game Classic Mode progress/result addresses.


## Patch output

This APWorld now produces a standard Archipelago patch file with the extension `.apsr`. The ROM is only needed when applying/opening the patch, not when generating the multiworld.

For now, the `.apsr` patch is a no-ROM-changes patch against Smash Remix 2.0.1. That means it mainly carries the generated player/server metadata, like other ROM patch based AP games. Future ROM edits can be added in `Patch.py` before the patch is written.

You no longer need this before generation. Optional fallback if the patch file picker is not available:

```yaml
smash_remix_options:
  rom_file: "C:/path/to/Smash Remix 2.0.1.z64"
```

Expected ROM MD5: `2b2d6b295106c54216b7fc7a2f14346e`
