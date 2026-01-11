import aiosqlite
from typing import Optional

class LevelAlertsRepository:
    __TABLE = "level_alerts"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def save_level_alerts_channel(
        self,
        guild_id: int,
        channel_id: Optional[int]
        ) -> bool:
        """Сохраняет канал для уведомлений о повышении уровня для гильдии (передайте None чтобы очистить)."""
        await self.db.execute(
            f"""INSERT OR REPLACE
            INTO {self.__TABLE} 
            (guild_id, channel_id)
            VALUES (?, ?)
            """,
            (guild_id, channel_id)
        )
        await self.db.commit()
        return True


    async def get_level_alerts_channel(
        self,
        guild_id: int
        ) -> Optional[int]:
        """Возвращает channel_id для уведомлений о повышении уровня для гильдии или None."""

        cursor = await self.db.execute(
            f"""
                SELECT channel_id
                FROM level_alerts
                WHERE guild_id = ?
            """,
            (guild_id)
        )

        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else None
