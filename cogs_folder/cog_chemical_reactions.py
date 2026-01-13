import discord
from discord.ext import commands
from discord import app_commands
import services_folder.srv_chem_reactions as chem_reactions
from services_folder.hlpr_logging import logger

class chemical_reactions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="chemical_reactions",
        description="Анализ и генерация возможных уравнений реакции по списку реагентов (owner only)"
    )
    async def chemical_reactions(
        self,
        interaction: discord.Interaction,
        reactants: str
        ):

        await interaction.response.defer(ephemeral=False)


        # Парсим строку реагентов
        try:
            parts = chem_reactions.parse_reactants_from_string(reactants)
        except Exception as e:
            await interaction.followup.send(f"Ошибка при разборе реагентов: {e}", ephemeral=True)
            return

        if not parts:
            await interaction.followup.send("Не удалось распознать реагенты. Укажите через `+` или `,` (например: `HCl , NaOH`).", ephemeral=True)
            return

        # Вызываем движок реакций с таймаутом через обёртку в chem_reactions
        try:
            # timeout в секундах — можно менять
            results = chem_reactions._run_with_timeout(chem_reactions.try_all_reaction_paths, args=(parts,), timeout=10.0)
        except TimeoutError:
            await interaction.followup.send("Ошибка: расчёт превысил допустимое время (таймаут). Упростите ввод или попробуйте снова позже.", ephemeral=True)
            return
        except Exception as e:
            logger.exception(f"Ошибка в chem_reactions: {e}")
            await interaction.followup.send(f"Внутренняя ошибка при анализе реакции: {e}", ephemeral=True)
            return

        proceeded = results.get('proceeded', []) or []
        blocked = results.get('possible_but_no_reaction', []) or []

        summary = [f"Reactants: {', '.join(parts)}", f"✅ Прошли вариантов: {len(proceeded)}", f"⚠️ Возможны, но не идут: {len(blocked)}"]
        await interaction.followup.send("\n".join(summary), ephemeral=False)

        # Функция для отправки подробного варианта (ограниченно по длине)
        async def send_variant(idx: int, rec: dict, tag: str):
            header = f"{tag} #{idx} — {rec.get('type') or ''}"
            body = rec.get('pretty') or ''
            payload = f"{header}\n\n{body}"
            # Discord ограничение: ~2000 символов. Обрезаем аккуратно.
            if len(payload) > 1900:
                payload = payload[:1900] + "\n... (truncated)"
            try:
                await interaction.followup.send(f"```{payload}```", ephemeral=False)
            except Exception:
                await interaction.followup.send(payload[:1900], ephemeral=False)

        # Отправляем до 5 подробных вариантов из каждой категории
        for i, rec in enumerate(proceeded[:5], start=1):
            await send_variant(i, rec, "Прошёл")

        for i, rec in enumerate(blocked[:5], start=1):
            await send_variant(i, rec, "Возможен, но не идёт")

        # Подсказка об ограничении
        if len(proceeded) > 5 or len(blocked) > 5:
            await interaction.followup.send("Показаны первые 5 вариантов в каждой категории. Уточните запрос для более узкого вывода.", ephemeral=True)

        return

async def setup(bot: commands.Bot):
    await bot.add_cog(chemical_reactions(bot))
