import aiosqlite
from typing import Optional

class DeadminRolesRepository:
    __TABLE = "deadmin_roles"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def save_deadmin_roles(self, guild_id: int, user_id: int, roles: list[int]) -> bool:
        roles_str = ",".join(map(str, roles))

        await self.db.execute(
            f"""
            INSERT INTO {self.__TABLE} (guild_id, user_id, roles)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET roles = excluded.roles
            """,
            (guild_id, user_id, roles_str)
        )
        await self.db.commit()
        return True

    async def pop_deadmin_roles(self, guild_id: int, user_id: int) -> Optional[list[int]]:
        cursor = await self.db.execute(
            f"""
            SELECT roles
            FROM {self.__TABLE}
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id)
        )
        row = await cursor.fetchone()

        if not row or not row[0]:
            return None

        roles = [int(r) for r in row[0].split(",")]

        # очищаем
        await self.db.execute(
            f"""
            DELETE FROM {self.__TABLE}
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id)
        )
        await self.db.commit()

        return roles

    async def is_deadmined(self, guild_id: int, user_id: int) -> bool:
        cursor = await self.db.execute(
            f"""
            SELECT 1
            FROM {self.__TABLE}
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id)
        )
        return await cursor.fetchone() is not None
    __TABLE = "deadmin_roles"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def save_deadmin_roles(
        self,
        guild_id: int,
        user_id: int,
        roles: list[int]
    ) -> bool:
        """Сохраняет роли пользователя (создаёт или обновляет запись)."""

        roles_str = ",".join(map(str, roles))

        await self.db.execute(
            f"""
            INSERT INTO {self.__TABLE} (guild_id, user_id, roles)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET roles = excluded.roles
            """,
            (guild_id, user_id, roles_str)
        )

        await self.db.commit()
        return True


    async def pop_deadmin_roles(
        self,
        guild_id: int,
        user_id: int
    ) -> Optional[list[int]]:
        """Возвращает роли и УДАЛЯЕТ запись из БД."""

        cursor = await self.db.execute(
            f"""
            SELECT roles
            FROM {self.__TABLE}
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id)
        )

        row = await cursor.fetchone()

        if not row or not row[0]:
            return None

        # безопасный парсинг
        roles = [int(r) for r in row[0].split(",") if r]

        await self.db.execute(
            f"""
            DELETE FROM {self.__TABLE}
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id)
        )

        await self.db.commit()

        return roles

    async def is_deadmined(self, guild_id: int, user_id: int) -> bool:
        """Проверяет, есть ли сохранённые роли для данного пользователя."""

        cursor = await self.db.execute(
            f"""
                SELECT roles
                FROM {self.__TABLE}
                WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id)
        )
        row = await cursor.fetchone()
        return row is not None and row[0] is not None