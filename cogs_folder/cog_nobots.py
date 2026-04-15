from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger

class nobots(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @staticmethod
    async def _find_bot_inviter(member: discord.Member) -> str | None:
        try:
            async for entry in member.guild.audit_logs(limit=20, action=discord.AuditLogAction.bot_add):
                if entry.target and getattr(entry.target, 'id', None) == member.id:
                    return entry.user.mention if entry.user else None
        except Exception as e:
            logger.warning(f"Не удалось получить данные аудита для бота {member.name}: {e}")
        return None

    @app_commands.command(
        name="toggle_nobots",
        description="Включить/выключить режим nobots (новые боты не смогут зайти на сервер)"
    )
    async def toggle_nobots(
        self,
        interaction: discord.Interaction
    ):  
        if not interaction.guild:
            await interaction.response.send_message("Эту команду можно использовать только на сервере.")
            return
        if perms_manager.has_perm(
            interaction.user.id,
            perms_manager.PermRole.HOST
        ): 
            guild_id = interaction.guild.id
            current_state = await self.bot.db.nobots_state.get_nobots_state(guild_id)
            bot_member = interaction.guild.me or interaction.guild.get_member(self.bot.user.id)

            if current_state:
                await self.bot.db.nobots_state.remove_nobots_state(guild_id)
                await interaction.response.send_message("Режим nobots выключен.")
            else:
                if not bot_member or not bot_member.guild_permissions.administrator:
                    await interaction.response.send_message(
                        "Ошибка! У бота недостаточно прав для управления режимом nobots. Требуются права Kick Members или Администратор."
                    )
                    return

                await self.bot.db.nobots_state.add_nobots_state(guild_id)
                await interaction.response.send_message("Режим nobots включён. Новые боты не смогут зайти на сервер.")
        else:
            await interaction.response.send_message("Ошибка! Недостаточно прав для использования команды. (Требуется права уровня 0 (HOST))")


    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            inviter = await self._find_bot_inviter(member)
            logger.info(f"Bot {member.name} joined guild {member.guild.name}. Added by: {inviter or 'unknown'}")
            guild_id = member.guild.id
            if await self.bot.db.nobots_state.get_nobots_state(guild_id):
                try:
                    await member.kick(reason="Режим nobots включён, новые боты не могут зайти на сервер.")

                    row = await self.bot.db.join_leave.get_join_leave_channel(member.guild.id)
                    channel_id, role_id = row
                    if channel_id == None:
                        return
                    new_member_channel = member.guild.get_channel(channel_id)
                    if new_member_channel is None:
                        return
                    await new_member_channel.send(
                        f"Бот {member.name} был исключен из-за включённого режима nobots.\nДобавил: {inviter or 'неизвестно'}.\n<@&1416769650439749722>"
                    )
                except Exception as e:
                    logger.error(f"Ошибка при кике бота {member.name}: {e}")


async def setup(bot: Bot):
    await bot.add_cog(nobots(bot))
