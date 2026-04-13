from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands, AllowedMentions

import services_folder.hlpr_timestamps as timestaps
import random
import re

from services_folder.srv_askgroq import ask_groq

list_doksa = [759310706343542854, 1310153194340352030, 1476857212419833916, 1350862362290294886]

async def forward_message_to_user(
    bot: discord.Client,
    source_message: discord.Message,
    target_user_id: int
):
    """
    Пересылает сообщение source_message пользователю target_user_id в ЛС
    со всем контентом и вложениями
    """

    # получаем пользователя
    try:
        user = await bot.fetch_user(target_user_id)
    except discord.NotFound:
        return False, "Пользователь не найден"

    # embed — имитация пересылки
    embed = discord.Embed(
        description=source_message.content or "*Без текста*",
        color=discord.Color.blurple(),
        timestamp=source_message.created_at
    )

    embed.set_author(
        name=f"{source_message.author} ({source_message.author.id})",
        icon_url=(
            source_message.author.avatar.url
            if source_message.author.avatar
            else None
        )
    )

    if source_message.guild:
        embed.set_footer(
            text=f"Сервер: {source_message.guild.name} | "
                 f"Канал: #{source_message.channel.name}"
        )
    else:
        embed.set_footer(text="Личные сообщения")

    # собираем вложения
    files = []
    for attachment in source_message.attachments:
        try:
            file = await attachment.to_file()
            files.append(file)
        except Exception:
            pass  # если файл не удалось скачать — пропускаем

    # отправка
    try:
        await user.send(embed=embed, files=files)
        return True, "Сообщение отправлено"
    except discord.Forbidden:
        return False, "ЛС пользователя закрыты"


class sus_messages(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        self.slavi_guild = None
        self.slavi_member = None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):

        msglow = message.content.lower()
        author_id = message.author.id

        # айдишник бота
        if "<@1409084528588488727>" in msglow:
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
                await message.reply(r"ливни с жизни ущербный https://tenor.com/view/son-agu-aaguu-aguu-aaaguu-gif-15295315305516131924", mention_author=True, delete_after=60)
        
        if "эщкере" in msglow:
            if random.randint(1, 50) == 1:
                await message.reply(r"https://klipy.com/gifs/pearto-teto")

        # ловушка на оркена
        if self.slavi_member in message.mentions or "@everyone" in msglow or "@here" in msglow or author_id == 1476857212419833916:
            if self.slavi_member.status != discord.Status.online:
                await message.reply(f"**Славик не в сети!**\nЯ его виртуальный помощник, прошу тебя написать всё что хочешь от него, как только он вернётся я напомню ему о сообщении от {message.author.mention}\n__Это сообщение будет удалено {timestaps.in_seconds(60)}__", delete_after=60)
            else:
                if author_id in list_doksa:
                    await message.reply(
                        await ask_groq( f"С тобой разговаривает: {message.author.name}. Сообщение: " + str(message.content)),
                        allowed_mentions=AllowedMentions().none()
                    )


        if message.guild == None and message.author.bot == False:
            await forward_message_to_user(self.bot, message, 727105264486187090)

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
                
    @commands.Cog.listener()
    async def on_ready(self):
        self.slavi_guild = self.bot.get_guild(1255059241358721137)
        if self.slavi_guild:
            self.slavi_member = self.slavi_guild.get_member(727105264486187090)

async def setup(bot: Bot):
    await bot.add_cog(sus_messages(bot))
