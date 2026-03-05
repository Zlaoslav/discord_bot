import aiosqlite

class AnnouncementsRepository:
    __TABLE = "auto_announcements"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def add(
        self,
        guild_id: int,
        channel_id: int
    ) -> bool:
        """Добавить канал для конкретной гильдии"""

        await self.db.execute(
            f"""
                INSERT INTO {self.__TABLE} (guild_id, channel_id)
                VALUES (?, ?)
                ON CONFLICT (guild_id, channel_id) DO NOTHING
            """,
            (guild_id, channel_id)
        )
        await self.db.commit()
        return True


    async def delete(
        self,
        guild_id: int,
        channel_id: int
    ) -> bool:
        """Удаляет канал из конкретной гильдии"""

        await self.db.execute(
            f"""
                DELETE FROM {self.__TABLE}
                WHERE guild_id = ? AND channel_id = ?
            """,
            (guild_id, channel_id)
        )

        await self.db.commit()
        return True


    async def is_auto_announcement(
        self,
        guild_id: int,
        channel_id: int
    ) -> bool:
        """Проверяет, является ли канал авто-анонсом в конкретной гильдии"""

        cursor = await self.db.execute(
            f"""
                SELECT EXISTS(
                    SELECT 1
                    FROM {self.__TABLE}
                    WHERE guild_id = ? AND channel_id = ?
                )
            """,
            (guild_id, channel_id)
        )

        result = await cursor.fetchone()
        await cursor.close()
        return result[0] == 1


    async def get_by_guild(
        self,
        guild_id: int
    ) -> list[int]:
        """Получить все channel_id для гильдии"""

        cursor = await self.db.execute(
            f"""
                SELECT channel_id
                FROM {self.__TABLE}
                WHERE guild_id = ?
            """,
            (guild_id,)
        )

        rows = await cursor.fetchall()
        await cursor.close()

        return [row[0] for row in rows]