from bot import Bot
import discord
from discord.ext import commands, tasks
from discord import app_commands
from services_folder.srv_minecraft_panel import create_send_save_minecraft_panel, create_minecraft_panel

class minecraft_panel(commands.Cog):
    def __init__(self, bot: Bot):
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
            self.bot,
            interaction=interaction,
            ip=ip,
            port=port,
            query_port=query_port
        )
        
    @commands.Cog.listener()
    async def on_ready(self):
        if not self.update_panels_task.is_running():
            self.update_panels_task.start()

    @tasks.loop(seconds=30)
    async def update_panels_task(self):
        panels = await self.bot.db.minecraft_panel.get_minecraft_panels()

        for guild_id, ip, port, query_port, channel_id, message_id in panels:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            try:
                message = await channel.fetch_message(message_id)
                embed, view = await create_minecraft_panel(ip, port, query_port)
                await message.edit(embed=embed)

            except discord.NotFound:
                await self.bot.db.minecraft_panel.delete_panel(message_id)
                print(f"[PANEL REMOVE] {ip}:{port} — сообщение удалено")

            except discord.Forbidden:
                print(f"[PANEL ERROR] {ip}:{port} — нет прав")

            except Exception as e:
                print(f"[PANEL ERROR] {ip}:{port}: {e}")


async def setup(bot: Bot):
    await bot.add_cog(minecraft_panel(bot))