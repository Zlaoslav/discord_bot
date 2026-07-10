from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager


class custom_perms(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @app_commands.command(
        name="listperms",
        description="Показать пользовательские права из perms_data.json"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def listperms(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None
    ):
        target = member or interaction.user
        try:
            user_id = int(target.id)
        except Exception:
            await interaction.response.send_message("Не удалось получить ID пользователя.", ephemeral=True)
            return

        roles = perms_manager.get_user_roles(user_id)
        if not roles:
            await interaction.response.send_message(f"У {target.mention} нет назначенных прав.", ephemeral=True)
            return

        lines = [f"• {r.value} — {perms_manager.get_role_description(r)}" for r in sorted(roles, key=lambda x: x.value)]
        await interaction.response.send_message(f"Права {target.mention}:\n```\n" + "\n".join(lines) + "\n```", ephemeral=True)


    @app_commands.command(
        name="editperms",
        description="Добавить/удалить роль пользователю (permsmanager+)"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def editperms(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        set: bool
    ):

        manager_id = int(interaction.user.id)
        target_id = int(member.id)

        # проверка прав инициатора
        if not perms_manager.has_perm(manager_id, perms_manager.PermRole.PERMSMANAGER):
            await interaction.response.send_message("У вас нет прав на изменение прав пользователей.", ephemeral=True)
            return
        # Представляем пользователю Select с доступными ролями
        class RoleSelect(discord.ui.Select):
            def __init__(self, manager_id: int, target_id: int, set_flag: bool):
                options = []
                for r in perms_manager.PermRole:
                    # не показываем защищённые роли в списке
                    if r in (perms_manager.PermRole.OWNER, perms_manager.PermRole.HOST, perms_manager.PermRole.PERMSMANAGER):
                        continue
                    options.append(discord.SelectOption(label=r.value.upper(), value=r.value, description=perms_manager.get_role_description(r)))

                super().__init__(placeholder="Выберите роль...", min_values=1, max_values=1, options=options)
                self.manager_id = manager_id
                self.target_id = target_id
                self.set_flag = set_flag

            async def callback(self, interaction: discord.Interaction):
                role_value = self.values[0]
                try:
                    role_enum = perms_manager.PermRole(role_value)
                except ValueError:
                    await interaction.response.send_message(f"Неизвестная роль `{role_value}`.", ephemeral=True)
                    return

                ok, msg = perms_manager.can_manage_role(self.manager_id, self.target_id, role_enum)
                if not ok:
                    await interaction.response.send_message(msg, ephemeral=True)
                    return

                if self.set_flag:
                    added = perms_manager.add_perm(self.target_id, role_enum)
                    if added:
                        await interaction.response.send_message(f"✅ Роль `{role_enum.value}` добавлена пользователю <@{self.target_id}>.", ephemeral=True)
                    else:
                        await interaction.response.send_message(f"⚠️ У пользователя уже есть роль `{role_enum.value}`.", ephemeral=True)
                else:
                    removed = perms_manager.remove_perm(self.target_id, role_enum)
                    if removed:
                        await interaction.response.send_message(f"✅ Роль `{role_enum.value}` удалена у <@{self.target_id}>.", ephemeral=True)
                    else:
                        await interaction.response.send_message(f"❌ Не удалось удалить роль `{role_enum.value}` (возможно её нет или роль защищена).", ephemeral=True)

        view = discord.ui.View(timeout=60)
        view.add_item(RoleSelect(manager_id, target_id, set))
        await interaction.response.send_message(f"Выберите роль для {'установки' if set else 'удаления'} пользователю {member.mention}:", view=view, ephemeral=True)


async def setup(bot: Bot):
    await bot.add_cog(custom_perms(bot))
