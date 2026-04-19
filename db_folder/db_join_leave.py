import aiosqlite
from typing import Optional

class JoinLeaveRepository:
    __TABLE = "join_leave"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db
    
    async def save_join_leave_channel(
        self,
        guild_id : int,
        channel_id: Optional[int],
        role_id: int | None = None,
        welcome_message: str | None = None
    ) -> bool:
        """Сохраняет ID канала, куда надо отправить уведомление при выходе/входе участников на сервер."""

        role_id = role_id or 0
        welcome_message = welcome_message or ""
        await self.db.execute(
            f"""
                INSERT INTO {self.__TABLE} (guild_id, channel_id, mention_role_id, welcome_message)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id)
                DO UPDATE SET
                    channel_id = excluded.channel_id,
                    mention_role_id = excluded.mention_role_id,
                    welcome_message = excluded.welcome_message
            """,
            (guild_id, channel_id, role_id, welcome_message)
        )
        await self.db.commit()
        return True


    async def get_join_leave_channel(self, guild_id):
        """Возвращает сохранённый channel_id для join/leave."""
        cursor = await self.db.execute(
            f"""
                SELECT channel_id, mention_role_id, welcome_message
                FROM {self.__TABLE}
                WHERE guild_id = ?
            """,
            (guild_id,)
        )
        row = await cursor.fetchone()
        channel_id = row[0] if row else None
        role_id = row[1] if row else None
        welcome_message = row[2] if row else None
        return (channel_id, role_id, welcome_message)

