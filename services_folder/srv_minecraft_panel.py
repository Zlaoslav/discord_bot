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
    async def show_players(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Берем real_ip и query_port из базы
        await interaction.response.defer(ephemeral=True)
        temp_msg = await interaction.followup.send("⏳ Получаем информацию о игроках...", ephemeral=True)

        row = await self.bot.db.minecraft_panel.get_panel_by_message_id(self.guild_id, self.message_id)

        if not row:
            await temp_msg.edit(content="❌ Панель не найдена в базе.", ephemeral=True)
            return

        real_ip, query_port = row

        if not query_port:
            await temp_msg.edit(content="❌ Query порт не указан для этой панели.", ephemeral=True)
            return
        
        if len(real_ip) <= 5:
            real_ip, query_port = query_port, real_ip
            
        url = f"http://{real_ip}:{query_port}/info"


        players = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    text = await resp.text()

                    # Попытка исправить некорректные имена игроков в массиве players
                    def fix_players_json(text: str) -> str:
                        pattern = r'("players"\s*:\s*)\[(.*?)\]'
                        match = re.search(pattern, text, re.DOTALL)
                        if match:
                            prefix = match.group(1)
                            content = match.group(2).strip()
                            if content:
                                # Разделяем по запятым и добавляем кавычки
                                names = [f'"{name.strip()}"' for name in content.split(",")]
                                fixed = prefix + "[" + ",".join(names) + "]"
                                text = re.sub(pattern, fixed, text, flags=re.DOTALL)
                            else:
                                # пустой массив
                                fixed = prefix + "[]"
                                text = re.sub(pattern, fixed, text, flags=re.DOTALL)
                        return text

                    fixed_text = fix_players_json(text)

                    try:
                        data = json.loads(fixed_text)
                        players = data.get("players", [])
                    except Exception as e_json:
                        logger.warning(f"[HTTP ERROR] Некорректный JSON после исправления с {url}: {e_json}\nТекст ответа: {fixed_text}")
                        await temp_msg.edit(content="❌ Сервер вернул некорректные данные даже после исправления JSON.")
                        return

        except Exception as e:
            logger.warning(f"[HTTP ERROR] {url} → {e}")
            await temp_msg.edit(content="❌ Не удалось получить информацию с сервера (таймаут или оффлайн).")
            return

        if not players:
            text = "❌ Игроки не онлайн или список пуст."
        else:
            text = "👥 Игроки онлайн:\n" + "\n".join(f"• {p}" for p in players)

        await temp_msg.edit(content=text)

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

    view = MinecraftPlayersView(
        bot=bot,
        guild_id=interaction.guild_id,
        message_id=0  # временно, обновится после send
    )

    return embed, view


async def create_minecraft_panel(
    ip: str,
    real_ip: str | None,
    port: int,
    query_port: int | None,
    bot: Bot,
    guild_id: int,
    message_id: int
):
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

    view = MinecraftPlayersView(
        bot=bot,
        guild_id=guild_id,
        message_id=message_id
    )

    return embed, view
