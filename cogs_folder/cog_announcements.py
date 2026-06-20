from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands, Forbidden, VoiceChannel
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

        if message.channel.type == discord.ChannelType.voice:
            return
        
        if not message.channel.is_news():
            return
        
        if not await self.bot.db.auto_announcements.is_auto_announcement(message.channel.id):
            return
        
        perms = message.channel.permissions_for(message.guild.me)
        if not perms.manage_messages:
            return
        
        if message.is_crossposted():
            return

        try:
            await message.publish()
        except Forbidden:
            await self.bot.db.auto_announcements.delete(message.channel.id)
        except Exception:
            pass
    
    
    @commands.Cog.listener()
    async def on_ready(self):
        # При запуске бота проверяем все каналы с автопубликацией и удаляем те, в которых нет прав
        auto_channels = await self.bot.db.auto_announcements.get_all()
        for channel_id in auto_channels:
            # Валидация
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                await self.bot.db.auto_announcements.delete(channel_id)
                continue
            
            if channel.type == discord.ChannelType.voice:
                await self.bot.db.auto_announcements.delete(channel_id)
                continue

            if not channel.type.is_news():
                await self.bot.db.auto_announcements.delete(channel_id)
                continue

            perms = channel.permissions_for(channel.guild.me)
            if not (
                    perms.manage_messages
                    and perms.read_messages
                    and perms.view_channel
                    and perms.send_messages
                    and perms.read_message_history
                ):
                await self.bot.db.auto_announcements.delete(channel_id)
                continue
            
            # Обновления последних 100 сообщений
            async for message in channel.history(limit=100):
                if message.is_crossposted():
                    break
                try:
                    await message.publish()
                except Forbidden:
                    await self.bot.db.auto_announcements.delete(channel_id)
                    break
                except Exception:
                    pass
        
        
async def setup(bot: Bot):
    await bot.add_cog(announcements(bot))
