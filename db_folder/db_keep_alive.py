import aiosqlite
from services_folder.hlpr_logging import logger
import time

class KeepAliveRepository:
    __TABLE = "keep_alive"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def add_keep_alive(
        self,
        ) -> bool:
        """Добавляет сегодня в таблицу keep_alive."""
        msk = time.gmtime(time.time() + 3 * 3600)
        date = time.strftime("%Y-%m-%d", msk)
        await self.db.execute(
            f"""
                INSERT INTO {self.__TABLE} (date)
                VALUES (?)
                ON CONFLICT(date) DO NOTHING
            """,
            (date,)
        )
        await self.db.commit()
        return True


    async def get_keep_alive(
        self,
        date: str
        ) -> bool:
        """Проверяет, есть ли дата в таблице keep_alive."""

        cursor = await self.db.execute(
            f"""
                SELECT date
                FROM {self.__TABLE}
                WHERE date = ?
            """,
            (date,)
        )
        row = await cursor.fetchone()
        return row is not None and row[0] is not None


    async def check_keep_alive(
        self,
        days: int = 30
        ) -> bool:
        """Проверяет, есть ли хотя бы одна дата за последние {days} дней в таблице keep_alive."""
        if days <= 0:
            raise ValueError("days must be greater than 0")
        for i in range(days):
            check_date = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 3 * 3600 - i * 24 * 3600))
            if await self.get_keep_alive(check_date):
                return True
        return False
