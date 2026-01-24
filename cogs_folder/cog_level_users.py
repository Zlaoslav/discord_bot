from bot import Bot
import discord
from discord import app_commands
from discord.ext import commands
from services_folder.srv_level_users import try_give_xp, xp_to_level, xp_left_to_next_level
import services_folder.hlpr_perms_manager as perms_manager


def format_duration(seconds: int) -> str:
    d, seconds = divmod(seconds, 86400)
    h, seconds = divmod(seconds, 3600)
    m, s = divmod(seconds, 60)
    return "".join(f"{x}{y}" for x, y in [(d,"d"),(h,"h"),(m,"m"),(s,"s")] if x)
class level_xp(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot


    @app_commands.command(
        name="lvl",
        description="Посмотерть уровень"
        )
    async def lvl(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "Команда доступна только на сервере.",
                ephemeral=True
            )
            return

        member = member or interaction.user
        guild_id = interaction.guild.id
        user_id = member.id

        level = await xp_to_level(self.bot, guild_id, user_id)
        xp_left = await xp_left_to_next_level(self.bot, guild_id, user_id)
        voice_time = format_duration(await self.bot.db.level_users.get_voice_time(guild_id, user_id))
        if voice_time == "" or voice_time == None:
            voice_time = "-"
        xp = await self.bot.db.level_users.get_xp(guild_id, user_id)

        embed = discord.Embed(
            title=member.display_name,
            url=f"https://discord.com/users/{member.id}",
            description="Информация об уровне участника",
            color=member.color if member.color.value != 0 else discord.Color.blurple()
        )

        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Топ", value=f"Место в топе по серверу: {await self.bot.db.level_users.get_user_rank(interaction.guild.id, interaction.user.id)}", inline=False)
        embed.add_field(name="Уровень", value=f"**{level}**", inline=True)
        embed.add_field(name="До следующего уровня", value=f"{xp_left} XP", inline=True)
        embed.add_field(name="Время в voice", value=str(voice_time), inline=False)

        # DEBUG
        if perms_manager.has_perm(
            interaction.user.id,
            perms_manager.PermRole.OWNER
        ):
            embed.add_field(
                name="Debug",
                value=(
                    f"XP: `{xp}`\n"
                    f"Guild ID: `{guild_id}`\n"
                    f"User ID: `{user_id}`"
                ),
                inline=False
            )

        embed.set_footer(
            text=f"Запросил: {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url
        )

        await interaction.response.send_message(embed=embed)


    @commands.Cog.listener()
    async def on_raw_reaction_add(
        self,
        payload: discord.RawReactionActionEvent
        ):
        
        if payload.guild_id is None:
            return  # это DM, игнорируем

        # Проверка: автор не бот
        member = payload.member  # может быть None, если бот не кэширует members
        if member is None:
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)  # ищем в кеше
        if member is None:
            # Если не нашли в кеше — можно запросить через API:
            # member = await guild.fetch_member(payload.user_id)
            return

        if member.bot:
            return  # реакция от бота, игнорируем
        
        await try_give_xp(self.bot, payload.guild_id, payload.user_id)

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message
    ):
        if message.author.bot:
            return  # реакция от бота, игнорируем
        
        await try_give_xp(self.bot, message.guild.id, message.author.id)
        

    @app_commands.command(
        name="lvltop",
        description="Посмотреть топ уровней"
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Опыт", value="xp"),
            app_commands.Choice(name="Уровень", value="level"),
            app_commands.Choice(name="Время войса", value="voice_time"),
        ]
    )
    async def lvltop(
        self,
        interaction: discord.Interaction,
        category: app_commands.Choice[str],
        top: int | None = None,
        start_at: int | None = None
    ):
        # ⏳ Задержка ответа
        await interaction.response.defer()

        top = top or 10
        start_at = start_at or 0

        # Валидация
        if start_at >= top:
            await interaction.followup.send(
                "start_at не может быть больше или равен top!",
                ephemeral=True
            )
            return

        if top - start_at > 50:
            await interaction.followup.send(
                "Максимум 50 пользователей за раз! (уменьшите top или увеличьте start_at)",
                ephemeral=True
            )
            return

        sort_by = category.value  # xp | level | voice_time

        # Получаем данные
        users = await self.bot.db.level_users.get_top_users(
            guild_id=interaction.guild.id,
            limit=top - start_at,
            offset=start_at,
            sort_by=sort_by
        )

        if not users:
            await interaction.followup.send(
                "Данные отсутствуют.",
                ephemeral=True
            )
            return

        # Формирование ответа
        lines: list[str] = []
        position = start_at + 1

        for user_id, xp, voice_time, level in users:
            if sort_by == "voice_time":
                value = format_duration(voice_time)
            elif sort_by == "xp":
                value = xp
            else:
                value = level

            lines.append(
                f"**#{position}** <@{user_id}> — `{value}`"
            )
            position += 1

        embed = discord.Embed(
            title=f"🏆 Топ пользователей по {category.name}",
            description="\n".join(lines),
            color=discord.Color.gold()
        )
        embed.set_footer(
            text=f"Запросил: {interaction.user.display_name}",
            icon_url=interaction.user.display_avatar.url
        )

        await interaction.followup.send(embed=embed)

        
        
async def setup(bot: Bot):
    await bot.add_cog(level_xp(bot))
