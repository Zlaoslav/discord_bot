from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands

import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger

from configs_folder.advanced_settings import _SAFE_NAMES, COUNTER_TOLERANCE
from services_folder.srv_counting import _preprocess, _check_nodes, _find_names, _eval_node
import ast

class counting(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @app_commands.command(
        name="calculate",
        description="Вычислить математическое выражение."
        )
    async def calculate(
        self,
        interaction: discord.Interaction,
        expression: str
        ):
        await interaction.response.defer(ephemeral=False)

        expr = expression.strip()
        if not expr:
            await interaction.followup.send("Пустое выражение.", ephemeral=True)
            return

        expr = _preprocess(expr)

        try:
            node = ast.parse(expr, mode='eval')
        except Exception as e:
            await interaction.followup.send(f"Синтаксическая ошибка: {e}", ephemeral=True)
            return

        try:
            _check_nodes(node)
        except Exception as e:
            await interaction.followup.send(f"Недопустимый элемент в выражении: {e}", ephemeral=True)
            return

        used = set()
        _find_names(node, used)
        unknown = [name for name in used if name not in _SAFE_NAMES]
        if unknown:
            await interaction.followup.send(f"Неизвестные идентификаторы: {', '.join(sorted(unknown))}", ephemeral=True)
            return

        try:
            result = _eval_node(node)
        except NameError as ne:
            await interaction.followup.send(f"Неизвестная функция или константа: {ne}", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Ошибка при вычислении: {e}", ephemeral=True)
            return

        if isinstance(result, float):
            out = f"{result:.12g}"
        else:
            out = str(result)

        await interaction.followup.send(f"`{expression}` = **{out}**", ephemeral=False)


    @app_commands.command(
        name="set_counter",
        description="Установить канал для счётчика (owner only)."
    )
    async def set_counter(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        start_value : int | None = None
        ):

        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас нет прав для этой команды.", ephemeral=True)
            return
        start_value = start_value or 1
        target = channel or interaction.channel
        if target is None:
            await interaction.response.send_message("Не удалось определить канал.", ephemeral=True)
            return

        await self.bot.db.counting.set_counter_channel(interaction.guild.id, int(target.id), start_value=start_value)
        await interaction.response.send_message(f"Счётчик установлен в канал {target.mention}. Начинаем с {start_value}.", ephemeral=True)

    @app_commands.command(
        name="unset_counter",
        description="Отключить канал счётчика (owner only)."
    )
    async def unset_counter(
        self,
        interaction: discord.Interaction
        ):

        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас нет прав для этой команды.", ephemeral=True)
            return

        await self.bot.db.counting.unset_counter_channel(interaction.guild.id)
        await interaction.response.send_message("Счётчик отключён.", ephemeral=True)
    # --- Обработчик входящих сообщений ---

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message
    ):

    # игнорируем ботов
        if message.author.bot:
            return

        # получаем состояние единственного счётчика
        channel_id, next_expected = await self.bot.db.counting.get_counter_state(message.guild.id)
        if channel_id is None or next_expected is None:
            return  # счётчик не настроен

        
        # работаем только в настроенном канале
        if message.channel.id != channel_id:
            return

        expr = (message.content or "").strip()
        if not expr:
            return

        # парсим и вычисляем (те же функции что и /calculate)
        try:
            expr_proc = _preprocess(expr)
            node = ast.parse(expr_proc, mode='eval')
            _check_nodes(node)
            used = set()
            _find_names(node, used)
            unknown = [name for name in used if name not in _SAFE_NAMES]
            if unknown:
                return  # неизвестные идентификаторы — игнорируем
            result = _eval_node(node)
        except Exception:
            return  # ошибка парсинга/вычисления — игнорируем

        try:
            value = float(result)
        except Exception:
            return

        expected = float(next_expected)
        if abs(value - expected) <= COUNTER_TOLERANCE:
            try:
                await message.add_reaction("✅")
            except Exception:
                pass
            await self.bot.db.counting.inc_counter(message.guild.id)
        else:
            try:
                await message.add_reaction("⚠️")
            except Exception:
                pass
            prev_num = expected - 1
            try:
                await message.channel.send(f"Предыдущее число: **{int(prev_num)}**")
            except Exception:
                pass



async def setup(bot: Bot):
    await bot.add_cog(counting(bot))
