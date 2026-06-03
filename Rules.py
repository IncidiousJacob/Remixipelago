from worlds.generic.Rules import set_rule


def set_rules(world):
    player = world.player
    multiworld = world.multiworld

    for location_name, data in world.active_locations.items():
        character = data["character"]
        difficulty_value = int(data.get("difficulty_value", 0))

        if data["type"] in {"classic_fight", "classic_fight_randomized_cpu"}:
            def rule(state, c=character, d=difficulty_value):
                return (
                    state.has(f"{c} Fighter Pass", player)
                    and state.has("Progressive Difficulty", player, d)
                )
        else:
            def rule(state, c=character):
                return state.has(f"{c} Fighter Pass", player)

        set_rule(multiworld.get_location(location_name, player), rule)

