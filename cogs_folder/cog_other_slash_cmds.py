import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger
from configs_folder.advanced_settings import BOT_COMMANDS_LIST
from services_folder.hlpr_send_long import _send_long_followup

class customp_play(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="say",
        description="Отправка сообщения в канал"
    )
    async def say(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: discord.TextChannel | None = None
    ):

        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=False)
            return

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
    async def help_slash(
        self,
        interaction: discord.Interaction
    ):
        
        """Отправляет полный список команд, разбитый на сообщения при необходимости."""
        await interaction.response.defer(ephemeral=False)
        text = BOT_COMMANDS_LIST.strip()
        await _send_long_followup(interaction, text)


    @app_commands.command(
        name="set_slowmode",
        description="Установить slowmode в текущем канале (секунды)"
    )
    async def set_slowmode(
        self,
        interaction: discord.Interaction,
        seconds: int
    ):
        
        # проверка — команда только на сервере
        if interaction.guild is None:
            await interaction.response.send_message("Команда только на сервере.", ephemeral=True)
            return

        # проверяем право пользователя управлять каналами (в этом канале)
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Команду можно использовать только в текстовом канале.", ephemeral=True)
            return

        if not channel.permissions_for(interaction.user).manage_channels:
            await interaction.response.send_message("У вас нет права `Manage Channels` в этом канале.", ephemeral=True)
            return

        # проверяем лимиты
        if seconds < 0 or seconds > 21600:
            await interaction.response.send_message("Значение должно быть от 0 до 21600 секунд.", ephemeral=True)
            return

        try:
            await channel.edit(slowmode_delay=seconds, reason=f"Установлено {interaction.user} через бота")
        except Exception as e:
            await interaction.response.send_message(f"Не удалось изменить slowmode: {e}", ephemeral=True)
            logger.error(e)
            return

        await interaction.response.send_message(f"Slowmode установлен: {seconds} секунд.", ephemeral=False)

   
    @app_commands.command(
        name="ban",
        description="Заблокировать участника"
    )
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
        delete_days: int
    ):
        
        if not interaction.user.guild_permissions.ban_members and not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.T):
            return await interaction.response.send_message("У вас нет прав на бан.", ephemeral=True)


        if delete_days < 0 or delete_days > 7:
            delete_days = 0

        try:
            await interaction.guild.ban(member, reason=reason, delete_message_days=delete_days)
            await interaction.response.send_message(f"Пользователь {member.mention} забанен. Причина: {reason}")
        except discord.Forbidden:
            await interaction.response.send_message("У бота отсутсвуют права на ban!")
        except Exception as e:
            await interaction.response.send_message("Неизсвестная ошибка!")
            logger.error(e)


