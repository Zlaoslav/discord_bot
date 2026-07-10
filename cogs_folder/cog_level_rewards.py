from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
from services_folder.srv_level_rewards import try_set_level_reward


class level_rewards(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @app_commands.command(
        name="set_lvl_reward",
        description="Установить награду за получение уровня (owner only)"
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def set_lvl_reward(
        self,
        interaction: discord.Interaction,
        level: int
    ):
        await interaction.followup.send(await try_set_level_reward(self.bot, interaction, level), ephemeral=True)



async def setup(bot: Bot):
    await bot.add_cog(level_rewards(bot))
