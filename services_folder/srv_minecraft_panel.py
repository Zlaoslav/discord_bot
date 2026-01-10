import discord
from mcstatus import JavaServer
from db_folder import DB

class MinecraftPlayersView(discord.ui.View):
    def __init__(self, players: list[str], source: str):
        super().__init__(timeout=120)
        self.players = players
        self.source = source

    @discord.ui.button(label="👥 Показать игроков", style=discord.ButtonStyle.primary)
    async def show_players(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.players:
            await interaction.response.send_message(
                "❌ Список игроков пуст или скрыт сервером",
                ephemeral=True
            )
            return

        header = (
            f"👥 **Игроки онлайн:** {len(self.players)}\n"
            f"📡 **Источник:** `{self.source}`\n\n"
        )

        chunks = []
        current = header

        for name in self.players:
            line = f"• {name}\n"
            if len(current) + len(line) > 1900:
                chunks.append(current)
                current = ""
            current += line

        if current:
            chunks.append(current)

        await interaction.response.send_message(chunks[0], ephemeral=True)
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
    interaction: discord.Interaction,
    ip: str,
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

    view = MinecraftPlayersView(players=data["players"], source=data["source"])
    msg = await interaction.followup.send(
        embed=embed,
        view=view
    )

    DB.minecraft_panel.save_minecraft_panel(
        guild_id=interaction.guild_id,
        server_ip=ip,
        server_port=port,
        query_port=query_port,
        channel_id=interaction.channel_id,
        message_id=msg.id
    )
    
    return None
