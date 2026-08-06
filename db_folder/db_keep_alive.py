from datetime import datetime, timedelta, timezone

import aiosqlite


class KeepAliveRepository:
    __TABLE = "keep_alive"

    MSK = timezone(timedelta(hours=3))

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def add_keep_alive(self) -> bool:
        """Добавляет сегодняшнюю дату в таблицу keep_alive."""
        today = datetime.now(self.MSK).date().isoformat()

        await self.db.execute(
            f"""
            INSERT INTO {self.__TABLE} (date)
            VALUES (?)
            ON CONFLICT(date) DO NOTHING
            """,
            (today,),
        )
        await self.db.commit()
        return True

    async def get_keep_alive(self, date: str) -> bool:
        """Проверяет, есть ли указанная дата в таблице keep_alive."""
        cursor = await self.db.execute(
            f"""
            SELECT 1
            FROM {self.__TABLE}
            WHERE date = ?
            LIMIT 1
            """,
            (date,),
        )
        return await cursor.fetchone() is not None

    async def check_keep_alive(self, days: int = 30) -> bool:
        """Проверяет, есть ли запись за последние days дней."""
        if days <= 0:
            raise ValueError("days must be greater than 0")

        start_date = (
            datetime.now(self.MSK).date() - timedelta(days=days - 1)
        ).isoformat()

        cursor = await self.db.execute(
            f"""
            SELECT 1
            FROM {self.__TABLE}
            WHERE date >= ?
            LIMIT 1
            """,
            (start_date,),
        )
        return await cursor.fetchone() is not None