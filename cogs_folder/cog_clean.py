from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands

import services_folder.hlpr_timestamps as timestamps
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger

import time
import asyncio

class clean(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
    
    @commands.command(name="parse_duration")
    async def parse_duration(self, ctx: commands.Context, duration: str):
        try:
            seconds = timestamps.parse_duration(duration)
            await ctx.send(f"{duration} соответствует {seconds} секундам.")
        except ValueError as e:
            await ctx.send(str(e))
    @app_commands.command(
        name="clean",
        description="Очистить сообщения"
    )
    @discord.app_commands.describe(
        limit="Лимит сообщений для удаления [10000 max]",
        duration="Очистка по давности сообщений (например, 1d, 2h30m, 45m)",
        author="Автор сообщений для очистки (по умолчанию — все)"
    )
    async def clean(
        self,
        interaction: discord.Interaction,
        limit: int | None=None,
        duration: str | None=None,
        author: discord.Member | None=None
    ):
        if not (
                perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER)
                or interaction.user.guild_permissions.manage_messages
            ):
            await interaction.response.send_message("У вас недостаточно прав!")
            return
        
        if not (limit or duration):
            await interaction.response.send_message("Укажите лимит или продолжительность для очистки сообщений!")
            return
        
        limit = limit or 10000
        if limit < 1 or limit > 10000:
            await interaction.response.send_message("Лимит должен быть от 1 до 10000!")
            return
        
        bot_permissions = interaction.channel.permissions_for(interaction.guild.me)
        if not (
            (bot_permissions.manage_messages
            and bot_permissions.read_message_history)
            or bot_permissions.administrator
        ):
            await interaction.response.send_message("У бота недостаточно прав! (выдайте боту право управлять сообщениями и читать историю сообщений)")
            return
        
        await interaction.response.defer()

        original_response_id = None
        try:
            original_message = await interaction.original_response()
            original_response_id = original_message.id
        except Exception:
            original_response_id = None
        
        time_limit = None
        if duration:
            try:
                time_limit = timestamps.parse_duration(duration)
            except ValueError as e:
                await interaction.followup.send(str(e))
                return

        def check(message: discord.Message) -> bool:
            if original_response_id and message.id == original_response_id:
                return False
            if author and message.author != author:
                return False
            if time_limit:
                return (discord.utils.utcnow() - message.created_at).total_seconds() <= time_limit
            return True

        async def update_interaction_progress(interaction: discord.Interaction, remaining: int, deleted_count: int, text: str | None=None):
            text = text or "пожалуйста, подождите"
            await interaction.edit_original_response(
                content=(
                    f"Удалено: {deleted_count}, обработано: {limit - remaining}/{limit}\n**Удаление...** _({text})_"
                )
            )

        start_at = time.time()
        deleted_count = 0
        remaining = limit
        batch_size = 25
        
        try:
            while remaining > 0:
                await update_interaction_progress(interaction, remaining, deleted_count)
                batch_limit = min(batch_size, remaining)
                batch = await interaction.channel.purge(
                    limit=batch_limit,
                    check=check,
                    bulk=True
                )
                deleted_count += len(batch)
                remaining -= batch_limit
                if not batch:
                    break
                    
        except Exception as e:
            logger.error(f"Ошибка при очистке сообщений: {e}")
            await interaction.edit_original_response("Произошла ошибка при удалении сообщений.")
            return

        await interaction.edit_original_response(
            content=(
                f"Удалено: {deleted_count}\nСообщения очищены!\nЗатраченное время: {time.time() - start_at:.2f} секунд"
            )
        )


async def setup(bot: Bot):
    await bot.add_cog(clean(bot))
