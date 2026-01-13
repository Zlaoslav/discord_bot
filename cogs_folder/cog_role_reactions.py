import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger
from db_folder import DB

class role_reactions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot





    @commands.Cog.listener()
    async def on_raw_message_delete(
        self,
        payload: discord.RawMessageDeleteEvent
        ):
        """Обработчик удаления сообщения - удаляет role_reaction из БД."""
        try:
            DB.role_reactions.delete_role_reaction(payload.message_id)
        except Exception as e:
            logger.error(f"Ошибка при удалении role_reaction из БД: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self,
        payload: discord.RawReactionActionEvent
        ):
        """Обработчик добавления реакции."""
        if payload.user_id == self.bot.user.id:
            return  # Игнорируем реакции самого бота

        # Получаем информацию о роле из БД
        emoji_str = str(payload.emoji)
        role_data = DB.role_reactions.get_role_reaction(payload.message_id, emoji_str)

        if not role_data:
            return  # Нет роли для этой реакции

        try:
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                return

            member = guild.get_member(payload.user_id)
            if not member:
                member = await guild.fetch_member(payload.user_id)

            role_id = role_data[3]
            role = guild.get_role(role_id)

            if not role:
                return

            # Проверяем, есть ли уже роль у пользователя
            had_role = role in member.roles

            if not had_role:
                await member.add_roles(role, reason=f"Role reaction на {emoji_str}")

            # Отправляем личное сообщение пользователю
            try:
                if had_role:
                    await member.send(f"ℹ️ Вы уже имели роль **{role.name}**")
                else:
                    await member.send(f"✅ Вам была выдана роль **{role.name}**")
            except Exception as e:
                logger.warning(f"Не удалось отправить личное сообщение о выдаче роли: {e}")
        except Exception as e:
            logger.error(f"Ошибка при добавлении роли на реакцию: {e}")



    @commands.Cog.listener()
    async def on_raw_reaction_remove(
        self,
        payload: discord.RawReactionActionEvent
        ):
        """Обработчик удаления реакции."""
        if payload.user_id == self.bot.user.id:
            return  # Игнорируем реакции самого бота

        # Получаем информацию о роле из БД
        emoji_str = str(payload.emoji)
        role_data = DB.role_reactions.get_role_reaction(payload.message_id, emoji_str)

        if not role_data:
            return  # Нет роли для этой реакции

        try:
            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                return

            member = guild.get_member(payload.user_id)
            if not member:
                member = await guild.fetch_member(payload.user_id)

            role_id = role_data[3]
            role = guild.get_role(role_id)

            if not role:
                return

            # Проверяем, есть ли роль у пользователя
            had_role = role in member.roles

            if had_role:
                await member.remove_roles(role, reason=f"Удалена реакция на {emoji_str}")

            # Отправляем личное сообщение пользователю
            try:
                if had_role:
                    await member.send(f"✅ У вас была забрана роль **{role.name}**")
                else:
                    await member.send(f"ℹ️ Вы не имели роль **{role.name}**")
            except Exception as e:
                logger.warning(f"Не удалось отправить личное сообщение об удалении роли: {e}")
        except Exception as e:
            logger.error(f"Ошибка при удалении роли на реакцию: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(role_reactions(bot))
