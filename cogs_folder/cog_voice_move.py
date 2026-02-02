from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager


class voice_move(commands.Cog):

    @app_commands.command(
        name="move_all",
        description="Переместить всех [owner only]"
    )
    async def move_all(
        self,
        interaction: discord.Interaction,
        from_channel: discord.VoiceChannel,
        in_channel: discord.VoiceChannel
    ):
        await interaction.response.defer()
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.followup.send("У вас нет прав для этой команды.")
            return
        
        for member in from_channel.members:
            member.move_to(in_channel)
        interaction.followup.send("Все участники перемещены.")

        
    @app_commands.command(
        name="disconnect_all",
        description="Отключить всех [owner only]"
    )
    async def disconnect_all(
        self,
        interaction: discord.Interaction,
        from_channel: discord.VoiceChannel
    ):
        await interaction.response.defer()
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.followup.send("У вас нет прав для этой команды.")
            return
        
        for member in from_channel.members:
            member.move_to(None)
        interaction.followup.send("Все участники отключены.")

        

async def setup(bot: Bot):
    await bot.add_cog(voice_move(bot))
