import discord
from discord.ext import commands
from discord import app_commands

import random
import re

class sus_messages(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        msglow = message.content.lower()

        if "<@1409084528588488727>" in msglow:
            # reply автоматически упомянет автора (mention_author=True по умолчанию)
            await message.reply(r"<:realbot:1437494993248850052>\nhttps://tenor.com/view/fuck-you-gif-27037587", mention_author=True, delete_after=10)

        if "осуждаю" in msglow:
            await message.reply(r"https://tenor.com/view/%D1%81%D1%82%D0%B8%D0%BD%D1%82-%D1%81%D1%82%D0%B8%D0%BD%D1%82%D0%B8%D0%BA-stint-stintik-%D0%B8%D1%81%D0%BF%D1%83%D0%B3%D0%B0%D0%BB%D1%81%D1%8F-gif-8740975965519379714", mention_author=True, delete_after=15)

        if r"||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​" in msglow:
            await message.reply(r"https://tenor.com/view/ghost-ping-troll-discord-gif-20744771", mention_author=True)

        if "@everyone" in msglow:
            await message.reply(r"https://tenor.com/view/everyone-discord-konosuba-gif-21395141", mention_author=True, delete_after=15)

        if "@here" in msglow:
            await message.reply(r"https://tenor.com/view/everyone-discord-gif-18237159", mention_author=True, delete_after=15)

        if "да" == msglow:
            if random.randint(1, 50) == 1:
                await message.reply(r"пизда", mention_author=True, delete_after=60)

        if "нет" == msglow:
            if random.randint(1, 50) == 1:
                await message.reply(r"пидора ответ", mention_author=True, delete_after=60)

        if "агу" in msglow or "уээ" in msglow:
            if random.randint(1, 50) == 1:
                await message.reply(r"ливни с жизни ущербный ||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​|| _ _ _ _ _ _ https://tenor.com/view/son-agu-aaguu-aguu-aaaguu-gif-15295315305516131924", mention_author=True, delete_after=60)

        TENOR_RE = re.compile(r"https?://(?:www\.)?tenor\.com", re.IGNORECASE)
        DS_RE = re.compile(r"https://media.discordapp.net/")
        if TENOR_RE.search(message.content or "") or DS_RE.search(message.content or ""):
            # получаем права автора именно в этом канале
            perms = message.channel.permissions_for(message.author)
            # attach_files — право прикреплять файлы/гифки
            if not perms.attach_files:
                # проверяем, может ли бот писать в канал
                bot_perms = message.channel.permissions_for(message.guild.me if message.guild else self.bot.user)
                if not bot_perms.send_messages:
                    # если бот не может ответить в канале — попробуем в лс
                    try:
                        await message.author.send(
                            "https://tenor.com/view/no-gif-no-gif-perms-gif-27679658"
                        )
                    except Exception:
                        pass
                    return

                # отвечаем реплаем (упомянет автора) и даём понятную подсказку
                await message.reply(
                    "https://tenor.com/view/no-gif-no-gif-perms-gif-27679658",
                    mention_author=True
                    )


async def setup(bot: commands.Bot):
    await bot.add_cog(sus_messages(bot))
