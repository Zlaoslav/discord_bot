import datetime


class DailyRequestsRepository:
    __TABLE = "user_daily_requests"

    def __init__(self, db):
        self.db = db

    async def get_count(
        self,
        user_id: int,
        date: str | None = None
    ) -> int:
        """Возвращает количество запросов пользователя за указанную дату (по умолчанию сегодня)."""
        date = date or datetime.date.today().isoformat()

        cursor = await self.db.execute(
            f"""
            SELECT count
            FROM {self.__TABLE}
            WHERE user_id = ? AND date = ?
            """,
            (user_id, date)
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0


    async def increment(self, user_id: int) -> int:
        """Увеличивает счётчик запросов пользователя за сегодня и возвращает новое значение."""

        date = datetime.date.today().isoformat()

        cursor = await self.db.execute(
            f"""
            SELECT count
            FROM {self.__TABLE}
            WHERE user_id = ? AND date = ?
            """,
            (user_id, date)
        )
        row = await cursor.fetchone()

        if row:
            new = row[0] + 1
            await self.db.execute(
                f"""
                UPDATE {self.__TABLE}
                SET count = ?
                WHERE user_id = ? AND date = ?
                """,
                (new, user_id, date)
            )
        else:
            new = 1
            await self.db.execute(
                f"""
                INSERT INTO {self.__TABLE}
                (user_id, date, count)
                VALUES (?, ?, ?)
                """,
                (user_id, date, new)
            )

        await self.db.commit()
        return new
