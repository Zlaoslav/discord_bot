from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
from services_folder.srv_daily_requests import get_remaining_requests, increment_user_daily_count, ask_gemini, DAILY_REQUEST_LIMIT
import services_folder.hlpr_perms_manager as hlpr_perms_manager
from services_folder.hlpr_logging import logger
class Askgpt(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @app_commands.command(
        name="askgpt",
        description="Спросить нейросеть"
    )
    async def askgpt(
        self,
        interaction: discord.Interaction,
    usermessage: str
    ):
        await interaction.response.defer()

        # OWNER и HOST игнорируют лимит
        is_privileged = hlpr_perms_manager.has_perm(interaction.user.id, hlpr_perms_manager.PermRole.OWNER) or hlpr_perms_manager.has_perm(interaction.user.id, hlpr_perms_manager.PermRole.HOST)

        if not is_privileged:
            remaining = await get_remaining_requests(self.bot, interaction.user.id)
            if remaining <= 0:
                await interaction.followup.send(f"Лимит запросов на сегодня исчерпан (максимум {DAILY_REQUEST_LIMIT}/день).", ephemeral=True)
                logger.debug(f"{interaction.user.name} exceeded daily askgpt limit")
                return

        try:
            # увеличиваем счётчик для непривилегированных пользователей
            if not is_privileged:
                increment_user_daily_count(self.bot, interaction.user.id)

            response = ask_gemini(usermessage)

            # Разбиваем ответ на сообщения по 1900 символов
            chunk_size = 1900
            max_chunks = 20
            chunks = [response[i:i+chunk_size] for i in range(0, len(response), chunk_size)][:max_chunks]

            for chunk in chunks:
                chunk = chunk.replace("```", "")
                if chunk.strip():  # Пропускаем пустые чанки
                    await interaction.followup.send(f"```markdown\n{chunk}\n```", ephemeral=False)
        except Exception as e:
            await interaction.followup.send(f"Erorr: {e}", ephemeral=False)



async def setup(bot: Bot):
    await bot.add_cog(Askgpt(bot))
