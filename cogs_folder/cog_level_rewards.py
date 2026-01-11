import discord
from discord.ext import commands
from discord import app_commands
from services_folder.srv_level_rewards import try_set_level_reward


class level_rewards(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="set_lvl_reward",
        description="Установить награду за получение уровня (owner only)"
    )
    async def set_lvl_reward(
        self,
        interaction: discord.Interaction,
        level: int
    ):
        interaction.followup.send(try_set_level_reward(interaction, level), ephemeral=True)



async def setup(bot: commands.Bot):
    await bot.add_cog(level_rewards(bot))
