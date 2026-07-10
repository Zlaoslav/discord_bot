from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger


class level_alerts(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @app_commands.command(
        name="set_level_alerts_channel",
        description="Установить канал для уведомлений о повышении уровня (owner only)"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def set_level_alerts_channel_cmd(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None
    ):
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав для этой команды.", ephemeral=True)
            return
        try:
            await self.bot.db.level_alerts.save_level_alerts_channel(interaction.guild.id, channel.id if channel else None)
            if channel:
                await interaction.response.send_message(f"Канал для уведомлений о повышении уровня установлен: {channel.mention}", ephemeral=True)
            else:
                await interaction.response.send_message("Канал для уведомлений о повышении уровня очищен.", ephemeral=True)
        except Exception as e:
            logger.exception(f"Ошибка при сохранении канала уведомлений уровней: {e}")
            await interaction.response.send_message("Ошибка при сохранении.", ephemeral=True)



async def setup(bot: Bot):
    await bot.add_cog(level_alerts(bot))

