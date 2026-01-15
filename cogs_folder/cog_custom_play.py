import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger
from configs_folder.advanced_settings import FFMPEG_PATH, FFMPEG_OPTIONS, YTDL_OPTS

import asyncio
import yt_dlp

YTDL = yt_dlp.YoutubeDL(YTDL_OPTS)
customplay_queue = asyncio.Queue()
async def play_next(bot, vc):
    if customplay_queue.empty():
        return

    song = await customplay_queue.get()

    source = discord.FFmpegPCMAudio(
        song["url"],
        executable=FFMPEG_PATH,
        **FFMPEG_OPTIONS,
    )

    vc.play(
        source,
        after=lambda _: asyncio.run_coroutine_threadsafe(
            play_next(bot, vc), bot.loop
        )
    )

    await song["channel"].send(
        f"🎵 Сейчас играет: **{song['title']}**"
    )

class custom_play(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="play",
        description="Запуск песни по URL или названию с ютуба (CUSTOMPLAY only)"
    )
    async def play(
        self,
        interaction: discord.Interaction,
        query: str
        ):

        vc = interaction.guild.voice_client
        if interaction.guild is None:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.CUSTOMPLAY):
            await interaction.response.send_message("У вас недостаточно прав.", ephemeral=True)
            return
        await interaction.response.defer()

        if not interaction.user.voice:
            await interaction.followup.send("Вы должны быть в голосовом канале.")
            return

        channel = interaction.user.voice.channel

        if not vc or not vc.is_connected():
            vc = await channel.connect()
        elif vc.channel != channel:
            await vc.move_to(channel)

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None, lambda: YTDL.extract_info(query, download=False)
        )

        if "entries" in info:
            info = info["entries"][0]

        audio = next(
            f for f in info["formats"]
            if f.get("acodec") != "none" and f.get("vcodec") == "none"
        )

        await customplay_queue.put({
            "url": audio["url"],
            "title": info.get("title", "Без названия"),
            "channel": interaction.channel,
        })

        if not vc.is_playing():
            await play_next(self.bot, vc)

        await interaction.followup.send(f"Добавлено: **{info['title']}**")


    @app_commands.command(
        name="skip",
        description="Пропуск песни (CUSTOMPLAY only)"
    )
    async def skip(
        self,
        interaction: discord.Interaction
    ):
        
        vc = interaction.guild.voice_client
        if interaction.guild is None:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.CUSTOMPLAY):
            await interaction.response.send_message("У вас недостаточно прав.", ephemeral=True)
            return

        if vc and vc.is_playing():
            vc.stop()  # корректно триггерит play_next через after
            await interaction.response.send_message("⏭ Трек пропущен.")
        else:
            await interaction.response.send_message("Ничего не играет.")

    @app_commands.command(
        name="stop",
        description="Остоновка песни (CUSTOMPLAY only)"
    )
    async def stop(
        self,
        interaction: discord.Interaction
    ):
        
        vc = interaction.guild.voice_client
        if interaction.guild is None:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.CUSTOMPLAY):
            await interaction.response.send_message("У вас недостаточно прав.", ephemeral=True)
            return

        if vc and vc.is_connected():
            if vc.is_playing():
                vc.stop()

        # очищаем очередь
            while not customplay_queue.empty():
                customplay_queue.get_nowait()

            await interaction.response.send_message(
                "⏹ Воспроизведение остановлено."
            )
        else:
            await interaction.response.send_message("Бот не подключён к голосовому каналу.")


async def setup(bot: commands.Bot):
    await bot.add_cog(custom_play(bot))
