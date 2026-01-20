import aiosqlite
from typing import Optional

class JoinLeaveRepository:
    __TABLE = "join_leave"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db
    
    async def save_join_leave_channel(self, channel_id: Optional[int], guild_id : int, role_id: int | None = None) -> bool:
        """Сохраняет ID канала, куда надо отправить уведомление при выходе/входе участников на сервер."""

        role_id = role_id or 0
        await self.db.execute(
            f"""
                UPDATE {self.__TABLE}
                SET channel_id = ?, mention_role_id = ?
                WHERE guild_id = ? 
            """,
            (channel_id, guild_id, role_id)
        )
        await self.db.commit()
        return True


    async def get_join_leave_channel(self, guild_id):
        """Возвращает сохранённый channel_id для join/leave."""
        cursor = await self.db.execute(
            f"""
                SELECT channel_id, role_id
                FROM {self.__TABLE}
                WHERE guild_id = ?
            """,
            (guild_id,)
        )
        row = await cursor.fetchone()
        channel_id = row[0] if row else None
        role_id = row[1] if row else None
        return (channel_id, role_id)


