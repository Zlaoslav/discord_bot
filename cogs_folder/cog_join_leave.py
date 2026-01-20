from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger

from datetime import datetime, timezone

class join_leave(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot


    @app_commands.command(
        name="set_new_member_channel",
        description="Установить канал с сообщениями о входе и выходе с сервера (owner only)"
        )
    async def set_new_member_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        mention_role: discord.Role | None = None
        ):

        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=False)
            return

        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=False)
            logger.debug(f"{interaction.user.name} try use set_new_member_channel")
            return
        targetchanel = channel or interaction.channel
        try:
            await self.bot.db.join_leave.save_join_leave_channel(interaction.guild.id, targetchanel.id, mention_role.id)
            await interaction.response.send_message("Успешно!", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Ошибка установки канала! (см логи)", ephemeral=False)


    @commands.Cog.listener()
    async def on_member_remove(self, member):
        row = await self.bot.db.join_leave.get_join_leave_channel(member.guild.id)
        channel_id, role_id = row
        if channel_id == None:
            return

        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return


        now = datetime.now(timezone.utc)
        delta = now - member.joined_at

        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60

        await channel.send(
            f"Пользователь {member.mention} ({member.name}), пробыл на сервере: {days}d.{hours}h.{minutes}m, id: `{member.id}` покинул сервер."
        )


    @commands.Cog.listener()
    async def on_member_join(self, member):
        row = await self.bot.db.join_leave.get_join_leave_channel(member.guild.id)
        channel_id, role_id = row
        if channel_id == None:
            return

        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return
        

        created_at = member.created_at  # datetime (UTC)
        now = datetime.now(timezone.utc)

        age_days = (now - created_at).days or "unknown"

        if role_id:
            await channel.send(
                f"Добро пожаловать, {member.mention}! ({member.name}), age: {age_days}, id: `{member.id}` <@&{role_id}>", 
            )
        else:
            await channel.send(
                f"Добро пожаловать, {member.mention}! ({member.name}), age: {age_days}, id: `{member.id}`", 
            )



async def setup(bot: Bot):
    await bot.add_cog(join_leave(bot))
