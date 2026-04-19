from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger


class moderation(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @app_commands.command(
        name="set_slowmode",
        description="Установить slowmode в текущем канале (секунды)"
    )
    async def set_slowmode(
        self,
        interaction: discord.Interaction,
        seconds: int
    ):
        
        if interaction.guild is None:
            await interaction.response.send_message("Команда только на сервере.", ephemeral=True)
            return

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
        reason: str | None = "Причина не указана",
        delete_days: int | None = 0
    ):
        
        if not interaction.user.guild_permissions.ban_members and not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.HOST):
            return await interaction.response.send_message("У вас нет прав на бан.", ephemeral=True)


        if delete_days < 0 or delete_days > 7:
            delete_days = 0

        try:
            await interaction.guild.ban(member, reason=reason + f" (by {interaction.user.name}, via bot)", delete_message_days=delete_days)
            await interaction.response.send_message(f"Пользователь {member.mention} забанен. Причина: {reason}")
        except discord.Forbidden:
            await interaction.response.send_message("У бота отсутсвуют права на ban!")
        except Exception as e:
            await interaction.response.send_message("Неизсвестная ошибка!")
            logger.error(e)
    

    @app_commands.command(
        name="kick",
        description="Исключить участника"
    )
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = "Причина не указана"
    ):
        
        if not interaction.user.guild_permissions.kick_members and not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.HOST):
            return await interaction.response.send_message("У вас нет прав на исключение.", ephemeral=True)

        try:
            await interaction.guild.kick(member, reason=reason + f" (by {interaction.user.name}, via bot)")
            await interaction.response.send_message(f"Пользователь {member.mention} исключён. Причина: {reason}")
        except discord.Forbidden:
            await interaction.response.send_message("У бота отсутсвуют права на kick!")
        except Exception as e:
            await interaction.response.send_message("Неизсвестная ошибка!")
            logger.error(e)


    @app_commands.command(
        name="deadmin",
        description="Деадминить участника (убирает все роли и сохраняет их)"
    )
    async def deadmin(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None
    ):
        if interaction.guild is None:
            return await interaction.response.send_message("Команда только на сервере.", ephemeral=True)

        target = member or interaction.user

        # Проверка прав
        if not interaction.user.guild_permissions.administrator and not perms_manager.has_perm(
            interaction.user.id, perms_manager.PermRole.HOST
        ):
            return await interaction.response.send_message("У вас нет прав на деадмин.", ephemeral=True)

        # Уже деадминен?
        if await self.bot.db.deadmin_roles.is_deadmined(interaction.guild.id, target.id):
            return await interaction.response.send_message("Пользователь уже деадминен.", ephemeral=True)

        roles_to_remove = []
        for role in target.roles:
            if (
                role.is_default()
                or role.is_bot_managed()
                or role.is_integration()
                or not role.is_assignable()
            ):
                continue

            perms = role.permissions
            if (
                perms.administrator
                or perms.manage_guild
                or perms.manage_roles
                or perms.manage_channels
                or perms.kick_members
                or perms.ban_members
                or perms.moderate_members
            ):
                roles_to_remove.append(role)

        if not roles_to_remove:
            return await interaction.response.send_message("Нет ролей для удаления.", ephemeral=True)

        role_ids = [r.id for r in roles_to_remove]

        try:
            # СНАЧАЛА снимаем роли
            await target.remove_roles(
                *roles_to_remove,
                reason=f"Деадмин от {interaction.user} через бота"
            )

            # ПОТОМ сохраняем (чтобы не было рассинхрона)
            await self.bot.db.deadmin_roles.save_deadmin_roles(
                interaction.guild.id,
                target.id,
                role_ids
            )

            await interaction.response.send_message(
                f"{target.mention} деадминён. Роли сохранены."
            )

        except discord.Forbidden:
            await interaction.response.send_message("У бота нет прав на управление ролями!", ephemeral=True)

        except Exception as e:
            logger.exception(e)
            await interaction.response.send_message("Ошибка при деадмине.", ephemeral=True)

    @app_commands.command(
        name="readmin",
        description="Восстановить роли участника"
    )
    async def readmin(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None
    ):
        if interaction.guild is None:
            return await interaction.response.send_message("Команда только на сервере.", ephemeral=True)

        target = member or interaction.user

        # Проверка: есть ли вообще данные
        if not await self.bot.db.deadmin_roles.is_deadmined(interaction.guild.id, target.id):
            return await interaction.response.send_message("Пользователь не деадминен.", ephemeral=True)

        # Право на восстановление
        is_self_restore = target.id == interaction.user.id

        has_access = (
            interaction.user.guild_permissions.administrator
            or perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.HOST)
            or is_self_restore
        )

        if not has_access:
            return await interaction.response.send_message("У вас нет прав на восстановление.", ephemeral=True)

        try:
            role_ids = await self.bot.db.deadmin_roles.pop_deadmin_roles(
                interaction.guild.id,
                target.id
            )

            if not role_ids:
                return await interaction.response.send_message("Нет сохранённых ролей.", ephemeral=True)

            roles = [
                role for role_id in role_ids
                if (role := interaction.guild.get_role(role_id)) is not None
            ]

            if not roles:
                return await interaction.response.send_message("Роли не найдены на сервере.", ephemeral=True)

            await target.add_roles(
                *roles,
                reason=f"Восстановление ролей от {interaction.user} через бота"
            )

            await interaction.response.send_message(
                f"Роли {target.mention} восстановлены."
            )

        except discord.Forbidden:
            await interaction.response.send_message("У бота нет прав на управление ролями!", ephemeral=True)

        except Exception as e:
            logger.exception(e)
            await interaction.response.send_message("Ошибка при восстановлении ролей.", ephemeral=True)

async def setup(bot: Bot):
    await bot.add_cog(moderation(bot))
