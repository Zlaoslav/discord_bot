from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger
from configs_folder.advanced_settings import BOT_COMMANDS_LIST
from services_folder.hlpr_send_long import send_long_followup

class other_slash_cmds(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @app_commands.command(
        name="say",
        description="Отправка сообщения в канал"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def say(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: discord.TextChannel | None = None
    ):
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logger.debug(f"{interaction.user.name} try use say")
            return

        error_message = None
        targetchanel = channel or interaction.channel

        try:
            await targetchanel.send(message)
        except discord.Forbidden:
            error_message = "У бота недостаточно прав для отправки в этот канал"
        except Exception as e:
            error_message = "Ошибка отправки!"
            logger.error(f"Ошибка отправки say: {e}")
        finally:
            if error_message:
                await interaction.response.send_message(error_message , ephemeral=True)
            else:
                await interaction.response.send_message("Отправленно!", ephemeral=True)


    @app_commands.command(
        name="help",
        description="Показать справку по командам"
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def help_slash(
        self,
        interaction: discord.Interaction
    ):  
        """Отправляет полный список команд, разбитый на сообщения при необходимости."""
        await interaction.response.defer(ephemeral=False)
        text = BOT_COMMANDS_LIST.strip()
        await send_long_followup(interaction, text)


    @app_commands.command(
        name="who_owner",
        description="Узнать, кто является владельцем сервера"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def who_owner(
        self,
        interaction: discord.Interaction
    ):
        owner = interaction.guild.owner
        await interaction.response.send_message(f"Владелец сервера: {owner.mention}", allowed_mentions=discord.AllowedMentions.none())

        
    @app_commands.command(
        name="get_guilds",
        description="Узнать, сервера где есть бот"
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def get_guilds(
        self,
        interaction: discord.Interaction
    ):
        to_send = ""
        for guild in self.bot.guilds:
            to_send += f"{guild.name} - {guild.id}\n"
        await interaction.response.send_message(to_send)
async def setup(bot: Bot):
    await bot.add_cog(other_slash_cmds(bot))
