"""SQLite-backed AI Game Master state (async, via aiosqlite).

One campaign per chat, so the state is keyed by ``chat_id`` only (like progress
tracks). The campaign-level fields (scenario, current scene, recent scene
history, NPC memory) are stored; JSON-typed fields are encoded here. This layer
holds no game rules and does not import ``gm`` — it deals in plain dicts.
"""

from __future__ import annotations

import json

from storage._db import connect

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS gm_state (
    chat_id INTEGER NOT NULL,
    scenario_title TEXT NOT NULL,
    scenario_goal TEXT NOT NULL,
    current_scene TEXT NOT NULL,
    scene_history TEXT NOT NULL,
    npc_memory TEXT NOT NULL,
    PRIMARY KEY (chat_id)
)
"""


class GMStateStore:
    """Async SQLite store for the per-chat GM campaign state."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def init(self) -> None:
        """Create the gm_state table if it does not exist."""
        async with connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE)
            await db.commit()

    async def get(self, chat_id: int) -> dict | None:
        """Return the chat's campaign state, or None if there is no campaign."""
        async with connect(self._db_path) as db:
            async with db.execute(
                "SELECT scenario_title, scenario_goal, current_scene, "
                "scene_history, npc_memory FROM gm_state WHERE chat_id = ?",
                (chat_id,),
            ) as cursor:
                row = await cursor.fetchone()
        if row is None:
            return None
        title, goal, scene, history_json, npc_json = row
        return {
            "scenario_title": title,
            "scenario_goal": goal,
            "current_scene": scene,
            "scene_history": json.loads(history_json),
            "npc_memory": json.loads(npc_json),
        }

    async def save(
        self,
        chat_id: int,
        *,
        scenario_title: str,
        scenario_goal: str,
        current_scene: str,
        scene_history: list[str],
        npc_memory: dict[str, str],
    ) -> None:
        """Insert or replace the chat's campaign state."""
        async with connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO gm_state "
                "(chat_id, scenario_title, scenario_goal, current_scene, "
                "scene_history, npc_memory) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(chat_id) DO UPDATE SET "
                "scenario_title = excluded.scenario_title, "
                "scenario_goal = excluded.scenario_goal, "
                "current_scene = excluded.current_scene, "
                "scene_history = excluded.scene_history, "
                "npc_memory = excluded.npc_memory",
                (chat_id, scenario_title, scenario_goal, current_scene,
                 json.dumps(scene_history), json.dumps(npc_memory)),
            )
            await db.commit()

    async def delete(self, chat_id: int) -> None:
        """Remove the chat's campaign (end the GM session)."""
        async with connect(self._db_path) as db:
            await db.execute("DELETE FROM gm_state WHERE chat_id = ?", (chat_id,))
            await db.commit()
