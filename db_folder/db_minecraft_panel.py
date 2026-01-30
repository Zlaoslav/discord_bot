import aiosqlite
from services_folder.hlpr_logging import logger

class MinecraftPanelRepository:
    __TABLE = "minecraft_panels"

    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def add_minecraft_panel(
        self,
        guild_id: int,
        server_ip: str,
        real_ip: str,
        server_port: int,
        query_port: int | None,
        channel_id: int,
        message_id: int
    ):
        await self.db.execute(
            f"""
                INSERT OR REPLACE INTO {self.__TABLE}
                (guild_id, server_ip, real_ip, server_port, query_port, channel_id, message_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                server_ip,
                real_ip,
                server_port,
                query_port,
                channel_id,
                message_id
            )
        )

        await self.db.commit()
        logger.info(f"[PANEL ADD] {server_ip} (real {real_ip}:{server_port}) → guild {guild_id}, channel {channel_id}")
        return True


    async def get_panel_by_message_id(
        self,
        guild_id: int,
        message_id: int
    ):
        cursor = await self.db.execute(
            f"""
                SELECT real_ip, query_port
                FROM {self.__TABLE}
                WHERE guild_id = ? AND message_id = ?
            """,
            (
                guild_id,
                message_id
            )
        )
        row = await cursor.fetchone()
        if row:
            # Возвращаем кортеж (real_ip, query_port)
            return (row[0], row[1])
        return None


    async def delete_minecraft_panel(
        self,
        message_id: int
    ):

        await self.db.execute(
            f"""
                DELETE FROM {self.__TABLE}
                WHERE message_id = ?
            """,
            (
                message_id,
            )
        )
        await self.db.commit()
        return True


    async def get_all_panels(self):
        cursor = await self.db.execute(
            f"""
                SELECT guild_id, server_ip, real_ip, server_port, query_port, channel_id, message_id
                FROM {self.__TABLE}
            """
        )

        panels = await cursor.fetchall()
        return panels
