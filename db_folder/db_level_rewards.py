import aiosqlite

class LevelRewardsRepository:
    __TABLE = "level_rewards"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def set_reward(
        self,
        guild_id: int,
        level: int,
        role_id: int | None
    ) -> bool:

        if not role_id:
            await self.db.execute(
                f"""
                DELETE FROM {self.__TABLE}
                WHERE guild_id = ? AND level = ?
                """,
                (guild_id, level)
            )
        else:
            await self.db.execute(
                f"""
                INSERT INTO {self.__TABLE} (guild_id, level, role)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, level)
                DO UPDATE SET role = excluded.role
                """,
                (guild_id, level, role_id)
            )

        await self.db.commit()
        return True

    async def get_rewards(self, guild_id: int) -> list[tuple[int, int]]:
        cursor = await self.db.execute(
            f"""
            SELECT level, role
            FROM {self.__TABLE}
            WHERE guild_id = ?
            """,
            (guild_id,)
        )
        return await cursor.fetchall()
