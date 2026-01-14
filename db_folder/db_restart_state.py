import aiosqlite
from typing import Optional

class RestartStateRepository:
    __TABLE = "restart_state"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def save_restart_channel(
        self,
        channel_id: Optional[int]
        ) -> bool:
        """Сохраняет ID канала, куда надо отправить уведомление после рестарта."""

        await self.db.execute(
            """
                UPDATE restart_state
                SET channel_id = ?
                WHERE id = 1
            """,
            (channel_id,)
        )
        await self.db.commit()
        return True


    async def pop_restart_channel(self) -> Optional[int]:
        """Возвращает сохранённый channel_id и очищает поле в БД."""

        cursor = await self.db.execute(
            """
                SELECT channel_id
                FROM restart_state
                WHERE id = 1
            """
        )
        row = cursor.fetchone()
        channel_id = row[0] if row else None
        # очищаем
        cursor.execute(
            """
                UPDATE restart_state
                SET channel_id = NULL
                WHERE id = 1
            """
        )
        await self.db.commit()
        return channel_id

