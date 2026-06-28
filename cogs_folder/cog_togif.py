from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
from services_folder.hlpr_logging import logger
from PIL import Image
import asyncio
import io
import os
import subprocess
import tempfile
from configs_folder.advanced_settings import FFMPEG_PATH

def create_gif_from_image(image_path: io.BytesIO) -> io.BytesIO:
    image = Image.open(image_path)
    output = io.BytesIO()
    image.save(
        output,
        format="GIF",
    )
    output.seek(0)
    return output

def create_gif_from_video(video_bytes: bytes) -> io.BytesIO:
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_video:
        temp_video.write(video_bytes)
        temp_video_path = temp_video.name

    temp_palette_path = None
    temp_gif_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_palette:
            temp_palette_path = temp_palette.name

        temp_gif_path = tempfile.mktemp(suffix='.gif')

        palette_command = [
            FFMPEG_PATH,
            '-y',
            '-i', temp_video_path,
            '-vf', 'fps=30,scale=iw:-1:flags=lanczos,palettegen=stats_mode=diff',
            temp_palette_path,
        ]
        subprocess.run(palette_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        gif_command = [
            FFMPEG_PATH,
            '-y',
            '-i', temp_video_path,
            '-i', temp_palette_path,
            '-lavfi', 'fps=15,scale=iw:-1:flags=lanczos [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5',
            '-loop', '0',
            temp_gif_path,
        ]
        subprocess.run(gif_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        with open(temp_gif_path, 'rb') as gif_file:
            output = io.BytesIO(gif_file.read())
        output.seek(0)
        return output
    finally:
        if os.path.exists(temp_video_path):
            os.unlink(temp_video_path)
        if temp_palette_path and os.path.exists(temp_palette_path):
            os.unlink(temp_palette_path)
        if temp_gif_path and os.path.exists(temp_gif_path):
            os.unlink(temp_gif_path)

class togif(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @app_commands.command(
        name="togif",
        description="Преобразовать видео/фото в GIF [max 8 MB]"
    )
    async def togif(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment
    ):
        """Преобразует видео/фото в GIF и отправляет его обратно."""
        await interaction.response.defer(ephemeral=False)
        if file.size > 8 * 1024 * 1024:  # 8 MB limit
            await interaction.followup.send("Файл слишком большой! Максимальный размер: 8 MB.")
            return
        
        if file.content_type.startswith('video/'):
            try:
                video_bytes = await file.read()
                gif_bytes = await asyncio.to_thread(create_gif_from_video, video_bytes)
                await interaction.followup.send(file=discord.File(fp=gif_bytes, filename="converted.gif"))
            except Exception as e:
                logger.error(f"Ошибка при преобразовании видео в GIF: {e}")
                await interaction.followup.send("Произошла ошибка при обработке видео.")
        
        elif file.content_type.startswith('image/'):
            try:
                image_bytes = await file.read()
                gif_bytes = create_gif_from_image(io.BytesIO(image_bytes))
                await interaction.followup.send(file=discord.File(fp=gif_bytes, filename="converted.gif"))
            except Exception as e:
                logger.error(f"Ошибка при преобразовании изображения в GIF: {e}")
                await interaction.followup.send("Произошла ошибка при обработке изображения.")
        
        else:
            await interaction.followup.send(f"Неизвестный формат! {file.content_type}, поддерживаются только изображения и видео")


async def setup(bot: Bot):
    await bot.add_cog(togif(bot))
