import aiosqlite

class LevelUsersRepository:
    __TABLE = "level_users"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def get_xp(
        self,
        guild_id: int,
        user_id: int
        ) -> int:
        """Возвращает опыт по айди гильдии и айди участника если нет то 0."""

        cursor = await self.db.execute(
            f"""
                SELECT xp
                FROM {self.__TABLE}
                WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id)
        )

        row = cursor.fetchone()
        return row[0] if row else 0

    async def add_xp(
        self,
        guild_id: int,
        user_id: int,
        amount: int
        ) -> bool:


        await self.db.execute(
            f"""
            INSERT INTO {self.__TABLE} (guild_id, user_id, xp)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET xp = xp + excluded.xp;
            """,
            (guild_id, user_id, amount)
        )
        await self.db.commit()
        return True

    async def get_voice_time(
        self,
        guild_id: int,
        user_id: int
        ) -> int:
        """Возвращает время войса по айди гильдии и айди участника если нет то 0."""

        cursor = await self.db.execute(
            f"""
            SELECT voice_time
            FROM {self.__TABLE}
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id)
        )

        row = cursor.fetchone()
        return row[0] if row else 0

    async def add_voice_time(
        self,
        guild_id: int,
        user_id: int,
        amount: int
        ) -> bool:


        await self.db.execute(
            f"""
            INSERT INTO {self.__TABLE} (guild_id, user_id, voice_time)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET voice_time = voice_time + excluded.voice_time;
            """,
            (guild_id, user_id, amount)
        )
        await self.db.commit()
        return True
    
    async def get_user_level(
        self,
        guild_id: int,
        user_id: int
        ) -> int:
        """Возвращает сохранённый уровень пользователя (если нет — 0)."""

        cursor = await self.db.execute(
            f"""
                SELECT level
                FROM {self.__TABLE}
                WHERE guild_id = ? AND user_id = ?
            """, (guild_id, user_id)
        )

        row = cursor.fetchone()
        return row[0] if row else 0

    async def set_user_level(
        self,
        guild_id: int,
        user_id: int,
        level: int
        ) -> bool:
        """Устанавливает уровень пользователя (вставка или обновление)."""

        await self.db.execute(
            f"""
                INSERT INTO {self.__TABLE} (guild_id, user_id, level)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id)
                DO UPDATE SET level = excluded.level;
            """, (guild_id, user_id, level)
        )
        await self.db.commit()
        return True
