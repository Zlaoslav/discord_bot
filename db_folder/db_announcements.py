import aiosqlite

class AnnouncementsRepository:
    __TABLE = "auto_announcements"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db
    
    async def add(
        self,
        channel_id: int
    ) -> bool:
        """Добавить канал по айди"""

        await self.db.execute(
            f"""
                INSERT INTO {self.__TABLE}
                WHERE channel_id = ?
                ON CONFLICT (channel_id) DO NOTHING
            """,
            (channel_id,)
        )
        await self.db.commit()
        return True


    async def delete(
        self,
        channel_id: int
    ) -> bool:
        """Удаляет канал из базы данных"""

        await self.db.execute(
            f"""
                DELETE FROM {self.__TABLE}
                WHERE channel_id = ?
            """,
            (channel_id,)
        )

        await self.db.commit()
        return True

    async def is_auto_announcement(
        self,
        channel_id: int
    ) -> bool:
        cursor = await self.db.execute(f"""SELECT EXISTS(SELECT 1 FROM {self.__TABLE} WHERE channel_id = ?);""", (channel_id,))
        result = await cursor.fetchone()
        return result[0] == 1