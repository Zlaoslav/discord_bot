import discord
from discord.ext import commands
from discord import app_commands
from services_folder.srv_minecraft_panel import create_send_save_minecraft_panel

class Minecraft_panel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="send_minecraft_panel",
        description="Создать панель сервера"
    )
    async def send_minecraft_panel(
        self,
        interaction: discord.Interaction,
        ip: str,
        port: int,
        query_port: int | None = None
    ):
        await interaction.response.defer()

        await create_send_save_minecraft_panel(
            interaction=interaction,
            ip=ip,
            port=port,
            query_port=query_port
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Minecraft_panel(bot))