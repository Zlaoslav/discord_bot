import discord
from discord.ext import commands
from discord import app_commands

import random

class dice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="d6",
        description="Подкинуть кубик d6"
    )
    async def d6(
        self,
        interaction: discord.Interaction
    ):
        await interaction.response.send_message("Подкинув кубик d6 выпало: `" + str(random.randint(1, 6)) + "`")

    @app_commands.command(
        name="d20",
        description="Подкинуть кубик d20"
    )
    async def d20(
        self,
        interaction: discord.Interaction
    ):
        await interaction.response.send_message("Подкинув кубик d20 выпало: `" + str(random.randint(1, 20)) + "`")

    @app_commands.command(
        name="d100",
        description="Подкинуть кубик d100"
    )
    async def d100(
        self,
        interaction: discord.Interaction
    ):
        await interaction.response.send_message("Подкинув кубик d100 выпало: `" + str(random.randint(1, 100)) + "`")

    @app_commands.command(
        name="d_any",
        description="Подкинуть кубик с любыми числами"
    )
    async def d_any(
        self,
        interaction: discord.Interaction,
        end: int,
        start: int | None=None
    ):
        if start == None: start = 1
        if end == None: end = 100
        try:
            await interaction.response.send_message(f"Подкинув кубик от {start} до {end} выпало: `{random.randint(start, end)}`")
        except:
            await interaction.response.send_message("Ошибка, недопустимые числа!", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(dice(bot))
