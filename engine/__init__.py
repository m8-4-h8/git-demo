"""Frontend-independent game core for the Ironsworn bot.

This package holds ALL game logic. It must never import anything from
``telegram`` (or any other frontend). Everything here is composed of pure,
fully unit-testable functions so the engine can be driven from a Telegram bot,
a CLI, tests, or any future frontend without modification.
"""

from engine.character import (
    Character,
    bounds_for,
    new_character,
    reset_momentum,
    set_field,
    stat_value,
)
from engine.core import greeting
from engine.oracles import (
    Answer,
    Odds,
    YesNoResult,
    ask_yes_no,
    draw_from,
    list_tables,
    random_table,
    table_title,
)
from engine.progress import (
    PROGRESS_MAX,
    PROGRESS_MIN,
    Rank,
    advance,
    parse_rank,
    progress_per_hit,
)
from engine.moves import (
    MOVES,
    CharacterDelta,
    MoveCategory,
    MoveResult,
    MoveSpec,
    apply_effects,
    moves_in,
    resolve_move,
)
from engine.rolls import (
    ActionRoll,
    Outcome,
    burn_momentum,
    progress_roll,
    roll_action,
)
from engine.tracks import (
    Track,
    TrackType,
    clear_progress,
    complete,
    end_encounter,
    parse_track_type,
)
from engine.tracks import mark_progress as mark_track_progress
from engine.vows import FulfillmentResult, Vow, fulfillment_roll, forsake
from engine.vows import mark_progress as mark_vow_progress

__all__ = [
    "greeting",
    "roll_action",
    "burn_momentum",
    "progress_roll",
    "ActionRoll",
    "Outcome",
    "ask_yes_no",
    "draw_from",
    "random_table",
    "table_title",
    "list_tables",
    "Odds",
    "Answer",
    "YesNoResult",
    "Character",
    "new_character",
    "stat_value",
    "set_field",
    "bounds_for",
    "reset_momentum",
    # progress mechanics
    "Rank",
    "progress_per_hit",
    "advance",
    "parse_rank",
    "PROGRESS_MIN",
    "PROGRESS_MAX",
    # vows
    "Vow",
    "FulfillmentResult",
    "mark_vow_progress",
    "fulfillment_roll",
    "forsake",
    # progress tracks
    "Track",
    "TrackType",
    "mark_track_progress",
    "end_encounter",
    "complete",
    "clear_progress",
    "parse_track_type",
    # moves
    "MOVES",
    "MoveCategory",
    "MoveSpec",
    "MoveResult",
    "CharacterDelta",
    "moves_in",
    "resolve_move",
    "apply_effects",
]
