import aiosqlite
from typing import Optional
import json

class TempvoiceRepository:
    __TABLE = "tempvoice"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db


    async def save_tempvoice_trigger(
        self,
        guild_id: int,
        trigger_channel_id: int
        ) -> bool:

        # default settings
        default_settings = {
            "prefix": "TempVoice ",
            "user_limit": 0,
            "bitrate": None,
            "slowmode": 0,
            "chat_enabled": True,
            "locked": False,
            "allowed_users": [],
            "allowed_roles": [],
            "blocked_users": [],
            "blocked_roles": [],
            "trusted_users": []
        }
        # allow trigger_channel_id==0 to mean "global / no specific trigger"
        trig = int(trigger_channel_id) if trigger_channel_id is not None else 0
        await self.db.execute(
            f"""
                INSERT OR REPLACE INTO {self.__TABLE}
                (guild_id, trigger_channel_id, settings, current_map)
                VALUES (?, ?, ?, ?)
            """,
            (
                guild_id,
                trig,
                json.dumps(default_settings, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False)
            )
        )
        await self.db.commit()
        return True


    async def remove_tempvoice_trigger(
        self,
        trigger_channel_id: int
        ) -> None:
        await self.db.execute(
            f"""
                DELETE FROM {self.__TABLE}
                WHERE trigger_channel_id = ?
            """,
            (trigger_channel_id,)
        )
        
        await self.db.commit()
        return True


    async def get_tempvoice_by_trigger(
        self,
        trigger_channel_id: int
        ) -> Optional[dict]:

        cursor = await self.db.execute(
            f"""
                SELECT id, guild_id, trigger_channel_id, panel_message_id, settings, current_map
                FROM {self.__TABLE}
                WHERE trigger_channel_id = ?
            """,
            (trigger_channel_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        tid, guild_id, trig_id, panel_id, settings_json, map_json = row
        try:
            settings = json.loads(settings_json or "{}")
        except Exception:
            settings = {}
        try:
            current_map = json.loads(map_json or "{}")
        except Exception:
            current_map = {}
        return {"id": tid, "guild_id": guild_id, "trigger_channel_id": trig_id, "panel_message_id": panel_id, "settings": settings, "current_map": current_map}

    async def get_tempvoice_by_guild(
        self,
        guild_id: int
        ) -> list[dict]:

        cursor = await self.db.execute(
            f"""
                SELECT id, guild_id, trigger_channel_id, panel_message_id, settings, current_map
                FROM {self.__TABLE}
                WHERE guild_id = ?
            """,
            (guild_id,)
        )
        rows = await cursor.fetchall()

        out = []
        for row in rows:
            tid, guild_id, trig_id, panel_id, settings_json, map_json = row
            try:
                settings = json.loads(settings_json or "{}")
            except Exception:
                settings = {}
            try:
                current_map = json.loads(map_json or "{}")
            except Exception:
                current_map = {}
            out.append({"id": tid, "guild_id": guild_id, "trigger_channel_id": trig_id, "panel_message_id": panel_id, "settings": settings, "current_map": current_map})
        return out

    async def get_all_tempvoices(self) -> list[dict]:
        """Return all tempvoice records as list of dicts."""

        cursor = await self.db.execute(
            f"""
                SELECT id, guild_id, trigger_channel_id, panel_message_id, settings, current_map
                FROM {self.__TABLE}
            """
        )
        rows = await cursor.fetchall()
        out = []
        for row in rows:
            tid, guild_id, trig_id, panel_id, settings_json, map_json = row
            try:
                settings = json.loads(settings_json or "{}")
            except Exception:
                settings = {}
            try:
                current_map = json.loads(map_json or "{}")
            except Exception:
                current_map = {}
            out.append({"id": tid, "guild_id": guild_id, "trigger_channel_id": trig_id, "panel_message_id": panel_id, "settings": settings, "current_map": current_map})
        return out

    async def update_tempvoice_settings(
        self,
        trigger_channel_id: int,
        settings: dict
        ) -> bool:

        await self.db.execute(
            f"""
                UPDATE {self.__TABLE}
                SET settings = ?
                WHERE trigger_channel_id = ?
            """,
            (
                json.dumps(settings, ensure_ascii=False),
                trigger_channel_id
            )
        )

        await self.db.commit()
        return True

    async def update_tempvoice_map(
        self,
        trigger_channel_id: int,
        current_map: dict
        ) -> bool:

        await self.db.execute(
            f"""
                UPDATE {self.__TABLE}
                SET current_map = ?
                WHERE trigger_channel_id = ?
            """, 
            (
                json.dumps(current_map, ensure_ascii=False),
                trigger_channel_id
            )
        )
        
        await self.db.commit()
        return True

    async def set_panel_message_id(
        self,
        trigger_channel_id: int,
        message_id: Optional[int]
        ) -> None:
        
        await self.db.execute(
            f"""
                UPDATE {self.__TABLE}
                SET panel_message_id = ?
                WHERE trigger_channel_id = ?
            """,
            (
                message_id,
                trigger_channel_id
            )
        )
        
        await self.db.commit()
        return True
