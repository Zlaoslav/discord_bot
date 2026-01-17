from bot import Bot
import discord
from mcstatus import JavaServer
from services_folder.hlpr_logging import logger

import aiohttp
import re
import json

class MinecraftPlayersView(discord.ui.View):
    def __init__(self, bot: Bot, guild_id: int, message_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.message_id = message_id

    @discord.ui.button(label="👥 Показать игроков", style=discord.ButtonStyle.primary)
    async def show_players(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        # Получаем real_ip и query_port из БД
        row = await self.bot.db.minecraft_panel.get_real_ip_and_query_port(self.guild_id, self.message_id)


        if not row:
            await interaction.response.send_message(
                "⚠️ Панель не найдена в базе. (это ошибка, сообщите об этом администратору бота)",
                ephemeral=True
            )
            return

        real_ip, query_port = row

        if not query_port:
            await interaction.response.send_message(
                "❌ Query порт не указан для этой панели.",
                ephemeral=True
            )
            return

        url = f"http://{real_ip}:{query_port}/info"

        await interaction.response.defer(ephemeral=True)
        temp_msg = await interaction.followup.send(
            "⏳ Получаем информацию о игроках...",
            ephemeral=True
        )

        # --- HTTP запрос и парсинг игроков ---
        players: list[str] = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    text = await resp.text()

                    # Исправление кривого JSON с players без кавычек
                    def fix_players_json(text: str) -> str:
                        pattern = r'("players"\s*:\s*)\[(.*?)\]'
                        match = re.search(pattern, text, re.DOTALL)
                        if not match:
                            return text

                        prefix = match.group(1)
                        content = match.group(2).strip()

                        if not content:
                            fixed = prefix + "[]"
                        else:
                            names = [
                                f'"{name.strip()}"'
                                for name in content.split(",")
                                if name.strip()
                            ]
                            fixed = prefix + "[" + ",".join(names) + "]"

                        return re.sub(pattern, fixed, text, flags=re.DOTALL)

                    fixed_text = fix_players_json(text)

                    try:
                        data = json.loads(fixed_text)
                        players = data.get("players", [])
                    except Exception as e:
                        logger.warning(
                            f"[HTTP ERROR] Некорректный JSON после исправления "
                            f"{url}: {e}\nОтвет: {fixed_text}"
                        )
                        await temp_msg.edit(
                            content="❌ Сервер вернул некорректные данные."
                        )
                        return

        except Exception as e:
            logger.warning(f"[HTTP ERROR] {url} → {e}")
            await temp_msg.edit(
                content="❌ Не удалось получить информацию с сервера."
            )
            return

        # --- Формирование ответа ---
        if not players:
            await temp_msg.edit(
                content="❌ Игроки не онлайн или список пуст."
            )
            return

        header = f"👥 **Игроки онлайн:** {len(players)}\n\n"

        chunks = []
        current = header

        for name in players:
            line = f"• {name}\n"
            if len(current) + len(line) > 1900:
                chunks.append(current)
                current = ""
            current += line

        if current:
            chunks.append(current)

        await temp_msg.edit(content=chunks[0])
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk, ephemeral=True)


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
        #logging.info(f"[DEBUG] Статус сервера {ip}: онлайн={status.players.online}/{status.players.max}")
    except Exception as e:
        #logging.error(f"[DEBUG] Сервер офлайн или ошибка: {e}")
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
            #logging.info(f"[DEBUG] Query сработал, игроки: {query.players.names}")
            if query.players.names:
                players = query.players.names
                source = "query"
        except Exception as e:
            pass
            #logging.warning(f"[DEBUG] Query не сработал: {e}")

    return {
        "online": True,
        "players_online": status.players.online,
        "players_max": status.players.max,
        "players": players,
        "icon": status.icon,
        "source": source
    }


async def create_send_save_minecraft_panel(
    bot: Bot,
    interaction: discord.Interaction,
    ip: str,
    real_ip: str | None = None,
    port: int = 25565,
    query_port: int | None = None
):
    # Получаем данные ТОЛЬКО для embed
    data = await get_server_info(ip, query_port=query_port)

    embed = discord.Embed(
        title=f"{'🟩' if data['online'] else '🟥'} {ip}:{port}",
        color=discord.Color.green() if data["online"] else discord.Color.red()
    )

    embed.add_field(
        name="Игроки",
        value=f"{data['players_online']}/{data['players_max']}",
        inline=True
    )

    # Отправляем сообщение БЕЗ view (message_id ещё неизвестен)
    msg = await interaction.followup.send(embed=embed)

    # Сохраняем панель в БД
    await bot.db.minecraft_panel.add_minecraft_panel(
        guild_id=interaction.guild_id,
        server_ip=ip,
        real_ip=real_ip,
        server_port=port,
        query_port=query_port,
        channel_id=interaction.channel_id,
        message_id=msg.id
    )

    # Теперь можем создать view с guild_id + message_id
    view = MinecraftPlayersView(
        bot=bot,
        guild_id=interaction.guild_id,
        message_id=msg.id
    )

    # Обновляем сообщение, добавляя кнопку
    await msg.edit(view=view)

    return None


async def create_minecraft_panel(
    ip: str,
    real_ip: str | None = None,
    port: int = 25565,
    query_port: int | None = None
):
    """
    Создает embed для панели сервера Minecraft.
    View создаётся ТОЛЬКО после отправки сообщения (когда известен message_id).
    """

    from mcstatus import JavaServer

    data = None

    # Пытаемся получить данные через get_server_info
    try:
        try:
            data = await get_server_info(ip, query_port=query_port, real_ip=real_ip)
        except TypeError:
            data = await get_server_info(ip, query_port=query_port)
    except Exception as e:
        logger.warning(f"[GET INFO ERROR] {ip}:{port} → {e}")

    # Fallback на mcstatus
    if not data:
        online = False
        players_online = 0
        players_max = 0

        try:
            server = JavaServer.lookup(ip)
            status = server.status()
            online = True
            players_online = status.players.online
            players_max = status.players.max
        except Exception as e:
            logger.warning(f"[STATUS ERROR] {ip}:{port} → {e}")

        data = {
            "online": online,
            "players_online": players_online,
            "players_max": players_max
        }

    embed = discord.Embed(
        title=f"{'🟩' if data['online'] else '🟥'} {ip}:{port}",
        color=discord.Color.green() if data["online"] else discord.Color.red()
    )

    embed.add_field(
        name="Игроки",
        value=f"{data['players_online']}/{data['players_max']}",
        inline=True
    )

    return embed, None
