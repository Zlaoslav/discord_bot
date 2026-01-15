import aiosqlite
from typing import Optional

class RoleReactionsRepository:
    __TABLE = "role_reactions"
    
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def save_role_reaction(
        self,
        message_id: int,
        channel_id: int,
        emoji: str,
        role_id: int
        ) -> bool:
        """Сохраняет информацию о role_reaction в БД."""

        await self.db.execute(
            f"""
                INSERT OR REPLACE INTO {self.__TABLE} (message_id, channel_id, emoji, role_id)
                VALUES (?, ?, ?, ?)
            """,
            (
                message_id,
                channel_id,
                emoji,
                role_id
            )
        )

        await self.db.commit()
        return True
        

    async def get_role_reaction(
        self,
        message_id: int,
        emoji: str
        ) -> Optional[tuple]:
        """Получает информацию о role_reaction: (message_id, channel_id, emoji, role_id)."""

        cursor = await self.db.execute(
            f"""
                SELECT message_id, channel_id, emoji, role_id
                FROM {self.__TABLE}
                WHERE message_id = ? AND emoji = ?
            """,
            (
                message_id,
                emoji
            )
        )

        row = await cursor.fetchone()
        return row

    async def get_all_role_reactions_for_message(
        self,
        message_id: int
        ) -> list:
        """Получает все role_reactions для сообщения."""

        cursor = await self.db.execute(
            f"""
                SELECT message_id, channel_id, emoji, role_id
                FROM {self.__TABLE}
                WHERE message_id = ?
            """,
            (message_id)
        )

        rows = await cursor.fetchall()
        return rows

    async def delete_role_reaction(
        self,
        message_id: int
        ) -> bool:
        """Удаляет role_reaction из БД по ID сообщения."""

        await self.db.execute(
            f"""
                DELETE FROM {self.__TABLE}
                WHERE message_id = ?
            """, (message_id)
        )

        await self.db.commit()
        return True
