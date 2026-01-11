import discord
from discord.ext import commands
from services_folder.srv_level_users import try_give_xp


class level_xp(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
        
        try_give_xp(payload.guild_id, payload.user_id)


    @commands.Cog.listener()
    async def on_reaction_add(
        self,
        reaction: discord.Reaction,
        user: discord.User
        ):
        if user.bot:
            return

        try_give_xp(self.bot, user.id)



async def setup(bot: commands.Bot):
    await bot.add_cog(level_xp(bot))
