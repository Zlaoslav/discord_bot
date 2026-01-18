import aiosqlite
from services_folder.hlpr_logging import logger
from mcstatus import JavaServer

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
                SELECT real_ip, server_port
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
            return {row[0], row[1]}
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



    async def get_server_info(ip: str, query_port: int | None = None):
        """
        Возвращает информацию о сервере Minecraft:
        - статус онлайн/офлайн
        - игроков онлайн / макс
        - список игроков (через query, если query_port задан)
        - иконка
        - источник данных ("ping" или "query")
        """

        # создаём объект для ping/status
        try:
            server = JavaServer.lookup(ip)
            status = server.status()
            logger.info(f"[DEBUG] Статус сервера {ip}: онлайн={status.players.online}/{status.players.max}")
        except Exception as e:
            logger.error(f"[DEBUG] Сервер офлайн или ошибка: {e}")
            return {
                "online": False,
                "players_online": 0,
                "players_max": 0,
                "players": [],
                "icon": None,
                "source": "offline"
            }

        # по умолчанию список игроков пуст, источник ping
        players = []
        source = "ping"

        # query — только для кнопки игроков
        if query_port:
            try:
                query_server = JavaServer.lookup(f"{ip}:{query_port}")
                query = query_server.query()
                logger.info(f"[DEBUG] Query сработал, игроки: {query.players.names}")
                if query.players.names:
                    players = query.players.names
                    source = "query"
            except Exception as e:
                logger.warning(f"[DEBUG] Query не сработал: {e}")

        return {
            "online": True,
            "players_online": status.players.online,
            "players_max": status.players.max,
            "players": players,
            "icon": status.icon,
            "source": source
       }
    
    async def get_all_panels(self):
        cursor = await self.db.execute(
            f"""
                SELECT guild_id, server_ip, real_ip, server_port, query_port, channel_id, message_id
                FROM {self.__TABLE}
            """
        )

        panels = await cursor.fetchall()
        return panels