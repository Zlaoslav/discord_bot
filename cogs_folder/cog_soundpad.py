import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger
from services_folder.srv_soundpad import list_sounds, SoundView

class soundpad(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="soundpanel",
        description="Выбрать и проиграть звук из списка доступных"
    )
    async def playsound(
        self,
        interaction: discord.Interaction
    ):
        
        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=False)
            return

        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.SOUNDPAD):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logger.debug(f"{interaction.user.name} try use soundpanel ({interaction.user.id})")
            return

        sounds = list_sounds()
        if not sounds:
            await interaction.response.send_message("Список звуков пуст.", ephemeral=True)
            return

        # ответ с меню
        view = SoundView(sounds, interaction.user.id)
        await interaction.response.send_message("Выберите звук для воспроизведения:", view=view, ephemeral=False)

    @app_commands.command(
        name="join",
        description="Войти в войс"
    )
    async def say(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel | None=None
    ):
        
        await interaction.response.defer(ephemeral=False)
        try:
            await interaction.guild.me.edit(mute=False)
            await interaction.guild.me.edit(deafen=True)
        except: pass
        if interaction.guild is None:
            await interaction.followup.send("Эта команда работает только на сервере.", ephemeral=False)
            return

        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.JOIN):
            await interaction.followup.send("У вас недостаточно прав использовать эту команду!.", ephemeral=False)
            logger.debug(f"{interaction.user.name} try use join")
            return

        try:
            if channel == None:
                channel = interaction.user.voice.channel

            if interaction.guild.voice_client:
                await interaction.guild.voice_client.move_to(channel)
            else:
                await channel.connect()

            await interaction.followup.send(f"✅ Подключился к {channel.name}", ephemeral=False)
        except Exception as e:
            logger.warning(e)
            await interaction.followup.send(f"Ошибка: отключения!", ephemeral=False)

    @app_commands.command(
        name="leave",
        description="Выйти из войса"
    )
    async def leave(
        self,
        interaction: discord.Interaction
    ):

        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=False)
            return

        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.LEAVE):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=False)
            logger.debug(f"{interaction.user.name} try use leave")
            return


        try:
            await interaction.guild.voice_client.disconnect()

            await interaction.response.send_message("✅ Отключился к от канала!", ephemeral=False)
        except Exception as e:
            logger.warning(e)
            if e == "NoneType":
                await interaction.response.send_message(f"Ошибка: бот не в голосовом канале!", ephemeral=False)
            else:
                await interaction.response.send_message(f"Ошибка: подключения!", ephemeral=False)

    @app_commands.command(
        name="stopsound",
        description="Остановить воспроизведение звука"
    )
    async def stopsound(
        self,
        interaction: discord.Interaction
    ):

        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=False)
            return

        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.SOUNDPAD):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=False)
            logger.debug(f"{interaction.user.name} try use stopsound")
            return

        voice_client = interaction.guild.voice_client
        if voice_client is None or not voice_client.is_connected():
            await interaction.response.send_message("Бот не подключен к голосовому каналу.", ephemeral=False)
            return

        if not voice_client.is_playing():
            await interaction.response.send_message("В данный момент ничего не воспроизводится.", ephemeral=False)
            return

        voice_client.stop()
        await interaction.response.send_message("⏹ Воспроизведение остановлено.", ephemeral=False)



async def setup(bot: commands.Bot):
    await bot.add_cog(soundpad(bot))
