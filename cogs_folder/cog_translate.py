from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
from deep_translator import GoogleTranslator


def translate_to_ru(text: str) -> str:
    return GoogleTranslator(source='auto', target='ru').translate(text)

class translate(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def process_message(self, interaction, message):
        content = message.content

        if not content:
            await interaction.response.send_message("Нет текста", ephemeral=True)
            return

        translated = translate_to_ru(content)

        await interaction.response.send_message(translated, ephemeral=True)
    
    @app_commands.command(
        name="translate_to_ru",
        description="Перевести на русский"
    )
    async def translate_to_ru(self, interaction: discord.Interaction, text: str):
        translated = translate_to_ru(text)
        await interaction.response.send_message(translated, ephemeral=True)



async def setup(bot: Bot):
    cog = translate(bot)

    async def callback(interaction: discord.Interaction, message: discord.Message):
        await cog.process_message(interaction, message)

    bot.tree.add_command(
        app_commands.ContextMenu(
            name="Перевести на русский",
            callback=callback
        )
    )

    await bot.add_cog(cog)