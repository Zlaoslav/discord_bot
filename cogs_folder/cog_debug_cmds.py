from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger

class debug_cmds(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @app_commands.command(
        name="force_toggle_role",
        description="Добавить/убрать роль участнику."
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def force_toggle_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        member: discord.Member | None = None
    ):
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.HOST):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logger.debug(f"{interaction.user.name} try use toggle_role")
            return

        bot_member = interaction.guild.me
        if bot_member is None:
            await interaction.response.send_message("Не удалось получить данные бота на сервере.", ephemeral=True)
            return

        if not bot_member.guild_permissions.manage_roles:
            await interaction.response.send_message("У бота нет права Manage Roles. Дай право и попробуй снова.", ephemeral=True)
            return

        target = member or interaction.user
        if isinstance(target, discord.User):
            target = interaction.guild.get_member(target.id)

        try:
            if role in target.roles:
                await target.remove_roles(role, reason=f"toggle_role by {interaction.user} ({interaction.user.id})")
                await interaction.response.send_message(f"Роль `{role.name}` убрана у {target.mention}.", ephemeral=True)
            else:
                await target.add_roles(role, reason=f"toggle_role by {interaction.user} ({interaction.user.id})")
                await interaction.response.send_message(f"Роль `{role.name}` выдана {target.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("Недостаточно прав для изменения ролей. Проверь позицию роли бота и права.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Ошибка при изменении роли: {e}", ephemeral=True)


    @app_commands.command(
        name="toggle_role",
        description="Добавить/убрать роль участнику."
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def toggle_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        member: discord.Member | None = None
    ):
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logger.debug(f"{interaction.user.name} try use toggle_role")
            return

        bot_member = interaction.guild.me
        if bot_member is None:
            await interaction.response.send_message("Не удалось получить данные бота на сервере.", ephemeral=True)
            return

        if not bot_member.guild_permissions.manage_roles:
            await interaction.response.send_message("У бота нет права Manage Roles. Дай право и попробуй снова.", ephemeral=True)
            return

        target = member or interaction.user
        if isinstance(target, discord.User):
            target = interaction.guild.get_member(target.id)

        if target is None:
            await interaction.response.send_message("Не удалось найти участника на сервере.", ephemeral=True)
            return

        if role.position >= bot_member.top_role.position:
            await interaction.response.send_message("Не могу управлять этой ролью. Роль выше или равна роли бота.", ephemeral=True)
            return

        if target.top_role.position >= bot_member.top_role.position and target != bot_member:
            await interaction.response.send_message("Не могу изменять роли этого участника (его роль выше или равна роли бота).", ephemeral=True)
            return

        try:
            if role in target.roles:
                await target.remove_roles(role, reason=f"toggle_role by {interaction.user} ({interaction.user.id})")
                await interaction.response.send_message(f"Роль `{role.name}` убрана у {target.mention}.", ephemeral=True)
            else:
                await target.add_roles(role, reason=f"toggle_role by {interaction.user} ({interaction.user.id})")
                await interaction.response.send_message(f"Роль `{role.name}` выдана {target.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("Недостаточно прав для изменения ролей. Проверь позицию роли бота и права.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Ошибка при изменении роли: {e}", ephemeral=True)


    @app_commands.command(
        name="demute",
        description="Включить или выключить микрофон/звук боту или участнику"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def demute(
        self,
        interaction: discord.Interaction,
        mute : bool | None=None,
        deafen : bool | None=None,
        member : discord.Member | None=None
    ):
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logger.debug(f"{interaction.user.name} try use demute")
            return

        if mute == None and deafen == None:
            await interaction.response.send_message("Укажите хотя бы 1 аргумент!.", ephemeral=True)
            return

        target = member or interaction.guild.me
        try:
            if mute != None:
                await target.edit(mute=mute)
            if deafen != None:
                await target.edit(deafen=deafen)
            await interaction.response.send_message(f"Успешно! (mute: {mute}, deafen: {deafen}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("Ошибка! Вероятно у бота недостаточно прав.", ephemeral=True)
            logger.warning(e)


    @app_commands.command(
        name="roles",
        description="Показать роли участника и их ID"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def roles(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None
    ):

        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logger.debug(f"{interaction.user.name} try use roles")
            return

        target = member or interaction.user
        if isinstance(target, discord.User):
            target = interaction.guild.get_member(target.id)

        if target is None:
            await interaction.response.send_message("Не удалось найти участника на сервере.", ephemeral=True)
            return

        roles_list = [r for r in target.roles if r.id != interaction.guild.id]
        if not roles_list:
            await interaction.response.send_message(f"У {target.display_name} нет ролей.", ephemeral=True)
            return

        text = "\n".join(f"• {r.name} — `{r.id}`" for r in roles_list)
        await interaction.response.send_message(f"Роли {target.mention}:\n```{text}```", ephemeral=True)


    @app_commands.command(
        name="myperms",
        description="Показать права бота на сервере"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def myperms(
        self,
        interaction: discord.Interaction
    ):
        
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logger.debug(f"{interaction.user.name} try use myperms")
            return

        perms = interaction.guild.me.guild_permissions
        allowed = [name for name, value in perms if value]
        if not allowed:
            await interaction.response.send_message("У бота нет прав на этом сервере.", ephemeral=True)
            return

        text = "\n".join(f"• {perm}" for perm in allowed)
        await interaction.response.send_message(f"**Права бота:**\n```{text}```", ephemeral=True)


async def setup(bot: Bot):
    await bot.add_cog(debug_cmds(bot))
