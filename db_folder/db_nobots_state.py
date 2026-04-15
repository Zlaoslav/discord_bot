import aiosqlite
from services_folder.hlpr_logging import logger

class NobotsStateRepository:
    __TABLE = "nobots_state"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def add_nobots_state(
        self,
        guild_id: int
        ) -> bool:
        """Добавляет сервер в таблицу nobots_state."""

        await self.db.execute(
            f"""
                INSERT INTO {self.__TABLE} (guild_id)
                VALUES (?)
            """,
            (guild_id,)
        )
        await self.db.commit()
        return True

    async def remove_nobots_state(
        self,
        guild_id: int
        ) -> bool:
        """Удаляет сервер из таблицы nobots_state."""

        await self.db.execute(
            f"""
                DELETE FROM {self.__TABLE}
                WHERE guild_id = ?
            """,
            (guild_id,)
        )
        await self.db.commit()
        return True
    
    async def get_nobots_state(
        self,
        guild_id: int
        ) -> bool:
        """Проверяет, включён ли режим nobots для сервера."""

        cursor = await self.db.execute(
            f"""
                SELECT guild_id
                FROM {self.__TABLE}
                WHERE guild_id = ?
            """,
            (guild_id,)
        )
        row = await cursor.fetchone()
        return row is not None and row[0] is not None
