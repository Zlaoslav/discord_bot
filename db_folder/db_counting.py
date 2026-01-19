import aiosqlite
from typing import Optional

class CountingRepository:
    __TABLE = "counting"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db
    
    async def set_counter_channel(
        self,
        guild_id: int,
        channel_id: Optional[int],
        start_value: int = 1
    ) -> bool:
        """Установить (или переназначить) канал счётчика. Один канал на 1 гильдию"""

        await self.db.execute(
            f"""
                INSERT INTO {self.__TABLE} (guild_id, channel_id, next_expected)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id)
                DO UPDATE SET
                    channel_id = excluded.channel_id,
                    next_expected = excluded.next_expected
            """,
            (guild_id, channel_id, start_value)
        )
        await self.db.commit()
        return True


    async def unset_counter_channel(
        self,
        guild_id: int
    ) -> bool:
        """Отключить канал счётчика (делает channel_id NULL)."""

        await self.db.execute(
            f"""
                UPDATE {self.__TABLE}
                SET channel_id = NULL
                WHERE guild_id = ?
            """,
            (guild_id,)
        )

        await self.db.commit()
        return True

    async def get_counter_state(
        self,
        guild_id: int
    ) -> Optional[tuple[int, int]]:
        """
        Возвращает (channel_id, next_expected) или None, если channel_id NULL.
        """

        cursor = await self.db.execute(
            f"""
                SELECT channel_id, next_expected
                FROM {self.__TABLE}
                WHERE guild_id = ?
            """,
            (guild_id,)
        )
        row = await cursor.fetchone()

        if not row:
            return None
        channel_id, next_expected = row
        if channel_id is None:
            return None
        return (int(channel_id), int(next_expected))



    async def inc_counter(
        self,
        guild_id
    ) -> bool:
        """Увеличить next_expected на 1."""

        await self.db.execute(
            f"""UPDATE {self.__TABLE}
            SET next_expected = next_expected + 1
            WHERE id = ?
            """,
            (guild_id,)
        )
        
        await self.db.commit()
        return True
