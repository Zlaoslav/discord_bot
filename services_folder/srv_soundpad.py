import discord
from discord.ui import View, Select
import services_folder.hlpr_perms_manager as perms_manager
from configs_folder.advanced_settings import SOUNDS_DIR, ALLOWED_EXT, FFMPEG_PATH
from services_folder.hlpr_logging import logger

import os
from pathlib import Path

def list_sounds():
    if not SOUNDS_DIR.exists() or not SOUNDS_DIR.is_dir():
        return []
    files = [f.name for f in SOUNDS_DIR.iterdir() if f.suffix.lower() in ALLOWED_EXT and f.is_file()]
    files.sort()
    return files

class SoundSelect(Select):
    def __init__(self, sounds: list[str], author_id: int):
        # лимит опций — 25. если больше, можно разбиать на страницы.
        options = [discord.SelectOption(label=os.path.splitext(s)[0][:100], value=s) for s in sounds[:25]]
        super().__init__(placeholder="Выберите звук...", min_values=1, max_values=1, options=options)
        self.author_id = author_id

    async def callback(self, interaction: discord.Interaction):
        # защита: только инициатор может выбрать или пользователь с правом SOUNDPAD
        if interaction.user.id != self.author_id or not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.SOUNDPAD):
            await interaction.response.send_message(f"<@{interaction.user.id}>, Только инициатор может выбрать звук.", ephemeral=False)
            return
        # проверки
        #if not sound_path.exists() or not sound_path.is_file():
        #    await interaction.response.send_message("Файл звука не найден.", ephemeral=True)
        #    return

        if not Path(FFMPEG_PATH).exists():
            await interaction.response.send_message("ffmpeg не найден.", ephemeral=True)
            logger.error(f"FFMPEG not found at: {FFMPEG_PATH}")
            return

        # Проверяем и устанавливаем права на выполнение если нужно
        try:
            import stat
            ffmpeg_stat = os.stat(FFMPEG_PATH)
            if not (ffmpeg_stat.st_mode & stat.S_IXUSR):
                os.chmod(FFMPEG_PATH, ffmpeg_stat.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                logger.info(f"Установлены права на выполнение для {FFMPEG_PATH}")
        except Exception as e:
            logger.warning(f"Не удалось установить права на выполнение ffmpeg: {e}")

        sound_filename = self.values[0]
        sound_path = os.path.join(SOUNDS_DIR, sound_filename)
        if not os.path.isfile(sound_path):
            await interaction.response.send_message("Файл не найден.", ephemeral=True)
            return

        # проверяем гильдию и голосовой канал пользователя
        if interaction.guild is None:
            await interaction.response.send_message("Команда доступна только на сервере.", ephemeral=True)
            return

        vc = interaction.guild.voice_client
        if vc is None:
            await interaction.response.send_message(
                "Бот сейчас не находится в голосовом канале. Подключите бота в голосовой канал, чтобы проигрывать звуки.",
                ephemeral=True
            )
            return
        await interaction.response.send_message(f"Проигрываю **{os.path.splitext(sound_filename)[0]}** ", ephemeral=False)
        # останавливаем текущее воспроизведение, если есть
        if vc.is_playing():
            vc.stop()

        # запускаем ffmpeg плеер
        # можно добавить опции (before_options, options) при необходимости
        source = discord.FFmpegPCMAudio(str(sound_path), executable=FFMPEG_PATH)
        try:
            vc.play(source, after=lambda err: logger.error(f"play finished: {err!r}") if err else None)
        except Exception as e:
            import traceback
            logger.exception("Ошибка воспроизведения")
            await interaction.followup.send(f"Ошибка воспроизведения: {e!r}. Подробности в логах.", ephemeral=True)
            return
        # необязательно: можно отсоединять через некоторое время, или оставить постоянное подключение
        # пример: отсоединиться после окончания — сложнее отслеживать, можно поставить таймер в фоне

class SoundView(View):
    def __init__(self, sounds: list[str], author_id: int, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.add_item(SoundSelect(sounds, author_id))
