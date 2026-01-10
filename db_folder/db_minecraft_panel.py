import aiosqlite
class MinecraftPanelRepository:
    __TABLE = "minecraft_panels_v2"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def save_minecraft_panel(
        self,
        guild_id: int,
        server_ip: str,
        server_port: int,
        query_port: int | None,
        channel_id: int,
        message_id: int
    ) -> None:
        await self.db.execute(
            f"""
            INSERT INTO {self.__TABLE} 
            (guild_id, server_ip, server_port, query_port, channel_id, message_id)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, server_ip, server_port)
            DO UPDATE SET
                query_port = excluded.query_port,
                channel_id = excluded.channel_id,
                message_id = excluded.message_id
            """,
            (guild_id, server_ip, server_port, query_port, channel_id, message_id)
        )
        await self.db.commit()
        print(f"[PANEL ADD] {server_ip}:{server_port} (query={query_port}) → guild {guild_id}, channel {channel_id}")

    async def get_panel(
        self,
        guild_id: int,
        server_ip: str,
        server_port: int
    ) -> tuple | None:
        cursor = await self.db.execute(
            f"""
            SELECT guild_id, server_ip, server_port, query_port, channel_id, message_id
            FROM {self.__TABLE}
            WHERE guild_id = ? AND server_ip = ? AND server_port = ?
            """,
            (guild_id, server_ip, server_port)
        )
        return await cursor.fetchone()

    async def delete_panel(
        self,
        guild_id: int,
        server_ip: str,
        server_port: int
    ) -> None:
        await self.db.execute(
            f"""
            DELETE FROM {self.__TABLE}
            WHERE guild_id = ? AND server_ip = ? AND server_port = ?
            """,
            (guild_id, server_ip, server_port)
        )
        await self.db.commit()
        print(f"[PANEL DELETE] {server_ip}:{server_port} → guild {guild_id}")
