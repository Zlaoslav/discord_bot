from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger
from configs_folder.advanced_settings import RADIO_STATIONS, FFMPEG_PATH

PER_PAGE = 25


class PaginatedSelect(discord.ui.Select):
    def __init__(self, items: list[str], page: int):
        self.items = items
        self.page = page

        start = page * PER_PAGE
        end = start + PER_PAGE
        page_items = items[start:end]

        options = [
            discord.SelectOption(label=str(item), value=str(item))
            for item in page_items
        ]

        super().__init__(
            placeholder=f"Страница {page + 1}",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client

        if vc is None:
            await interaction.response.send_message(
                "Бот сейчас не находится в голосовом канале. Подключите бота в голосовой канал.",
                ephemeral=True
            )
            return

        stream_url = RADIO_STATIONS[self.values[0]]

        await interaction.response.send_message(
            f"Подключаюсь к стриму: {self.values[0]}",
            ephemeral=False
        )

        # Останавливаем текущее воспроизведение (когда уже играет предыдущий поток)
        if vc.is_playing() or vc.is_paused():
            vc.stop()

        ffmpeg_options = {
            "before_options": (
                "-reconnect 1 "
                "-reconnect_streamed 1 "
                "-reconnect_delay_max 5 "
                "-icy 0 "
                "-loglevel error"
            ),
            "options": (
                "-vn "
                "-f s16le "
                "-ar 48000 "
                "-ac 2"
            )
        }

        source = discord.FFmpegPCMAudio(
            stream_url,
            executable=FFMPEG_PATH,
            **ffmpeg_options
        )

        try:
            vc.play(
            source,
            after=lambda err: print(f"Ошибка: {err}") if err else None
        )
        except Exception as e:
            await interaction.followup.send(
                f"Ошибка воспроизведения: {e}",
                ephemeral=True
            )


class PaginationView(discord.ui.View):
    def __init__(self, items: list[str]):
        super().__init__(timeout=120)
        self.items = items
        self.page = 0
        self.max_page = max(0, (len(items) - 1) // PER_PAGE)
        self.update_select()

    def update_select(self):
        self.clear_items()

        if not self.items:
            return

        self.add_item(PaginatedSelect(self.items, self.page))

        if self.page > 0:
            self.add_item(PrevButton())

        if self.page < self.max_page:
            self.add_item(NextButton())


class PrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="⬅", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view: PaginationView = self.view  # type: ignore
        view.page = max(0, view.page - 1)
        view.update_select()
        await interaction.response.edit_message(view=view)


class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="➡", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction):
        view: PaginationView = self.view  # type: ignore
        view.page = min(view.max_page, view.page + 1)
        view.update_select()
        await interaction.response.edit_message(view=view)


class radio(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @app_commands.command(
        name="play_radio_station",
        description="Включить радио станцию"
    )
    async def play_radio_station(
        self,
        interaction: discord.Interaction
    ):
        stations = list(RADIO_STATIONS.keys())

        if not stations:
            await interaction.response.send_message(
                "Список радио станций пуст.",
                ephemeral=True
            )
            return

        view = PaginationView(stations)

        await interaction.response.send_message(
            "Выберите радио станцию:",
            view=view,
            ephemeral=True
        )


async def setup(bot: Bot):
    await bot.add_cog(radio(bot))