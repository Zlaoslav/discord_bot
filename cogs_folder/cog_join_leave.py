import discord
from discord.ext import commands
from discord import app_commands
from db_folder import DB
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger

class join_leave(commands.Cog):
    def __init__(self, bot: commands.Bot):
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
            DB.join_leave.save_join_leave_channel(targetchanel.id, mention_role.id)
            await interaction.response.send_message("Успешно!", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Ошибка установки канала! (см логи)", ephemeral=False)


    @commands.Cog.listener()
    async def on_member_remove(self, member):
        channel_id, role_id = DB.join_leave.get_join_leave_channel(member.guild.id)
        if channel_id == None:
            return

        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return

        await channel.send(
            f"Пользователь {member.mention} ({member.name}) id: `{member.id}` покинул сервер."
        )


    @commands.Cog.listener()
    async def on_member_join(self, member):
        channel_id, role_id = DB.join_leave.get_join_leave_channel(member.guild.id)
        if channel_id == None:
            return

        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return
        
        if role_id:
            await channel.send(
                f"Добро пожаловать, {member.mention}! ({member.name}, id: `{member.id}` <@&{role_id}>)", 
            )
        else:
            await channel.send(
                f"Добро пожаловать, {member.mention}! ({member.name}, id: `{member.id}`)", 
            )



async def setup(bot: commands.Bot):
    await bot.add_cog(join_leave(bot))
