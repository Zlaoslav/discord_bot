from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands, Forbidden
import services_folder.hlpr_perms_manager as perms_manager

class announcements(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @app_commands.command(
        name="add_auto_publish",
        description="Запустить автопубликацию в канале для объявлений"
    )
    async def add_auto_publish(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        if channel.type != discord.ChannelType.news:
            await interaction.response.send_message("Это не канал объявлений!")
            return
        
        if not interaction.user.guild_permissions.administrator and not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав!")
            return
        
        permissions = channel.permissions_for(interaction.guild.me)
        if not permissions.manage_messages:
            await interaction.response.send_message("У бота недостаточно прав! (выдайте боту право управлять сообщениями)")
            return
    
        await self.bot.db.auto_announcements.add(channel.id)
        await interaction.response.send_message(f"В канале {channel.name} успешно включена автопубликация сообщений")

    @app_commands.command(
        name="remove_auto_publish",
        description="Отменить автопубликацию в канале для объявлений"
    )
    async def remove_auto_publish(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        if not interaction.user.guild_permissions.administrator and not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав!")
            return

        await self.bot.db.auto_announcements.delete(channel.id)
        await interaction.response.send_message(f"В канале {channel.name} успешно выключена автопубликация сообщений")


    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message
    ):
        if message.channel.guild == None:
            return
        
        if not message.channel.is_news():
            return
        
        if not await self.bot.db.auto_announcements.is_auto_announcement(message.channel.id):
            return
        
        perms = message.channel.permissions_for(message.guild.me)
        if not perms.manage_messages:
            return
        
        try:
            await message.publish()
        except Forbidden:
            await self.bot.db.auto_announcements.delete(message.channel.id)
        except Exception:
            pass
        
        
async def setup(bot: Bot):
    await bot.add_cog(announcements(bot))
