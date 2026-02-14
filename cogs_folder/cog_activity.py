from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager

from typing import Optional


class ActivityModal(discord.ui.Modal):
    def __init__(self, bot: commands.Bot, activity_type: str, status_str: str):
        super().__init__(title="Введите текст активности")
        self.bot = bot
        self.activity_type = activity_type
        self.status_str = status_str

        # Текст активности
        self.text_input = discord.ui.TextInput(
            label="Текст активности",
            style=discord.TextStyle.short,
            max_length=100,
            required=True
        )
        self.add_item(self.text_input)

        # Если нужен URL для стрима — добавляем поле
        if self.activity_type == "streaming":
            self.url_input = discord.ui.TextInput(
                label="Stream URL (например https://twitch.tv/yourchannel)",
                style=discord.TextStyle.short,
                placeholder="https://",
                required=True,
                max_length=200
            )
            self.add_item(self.url_input)
        else:
            self.url_input = None

    async def on_submit(self, interaction: discord.Interaction):
        text = self.text_input.value
        url = self.url_input.value if self.url_input else None

        # Собираем activity объект
        activity = None
        act = self.activity_type
        if act == "playing":
            activity = discord.Game(name=text)
        elif act == "streaming":
            activity = discord.Streaming(name=text, url=url)
        elif act == "listening":
            activity = discord.Activity(type=discord.ActivityType.listening, name=text)
        elif act == "watching":
            activity = discord.Activity(type=discord.ActivityType.watching, name=text)
        elif act == "competing":
            activity = discord.Activity(type=discord.ActivityType.competing, name=text)
        else:
            activity = discord.Game(name=text)

        # Статус
        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible
        }
        status = status_map.get(self.status_str, discord.Status.online)

        # Меняем presence
        try:
            await self.bot.change_presence(status=status, activity=activity)
        except Exception as e:
            await interaction.response.send_message(f"Не удалось изменить статус: {e}", ephemeral=True)
            return

        await interaction.response.send_message(
            f"✅ Активность установлена: **{text}** (тип: {self.activity_type}, статус: {self.status_str})",
            ephemeral=True
        )


class AdminActivityView(discord.ui.View):
    def __init__(self, bot: commands.Bot, author_id: int, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author_id = author_id
        self.activity_choice: Optional[str] = "playing"
        self.status_choice: Optional[str] = "online"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Только автор команды может использовать эти элементы.", ephemeral=True)
            return False
        return True

    # Select для типа активности
    @discord.ui.select(
        placeholder="Выберите тип активности",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="Играет", value="playing", description="Game / играет в..."),
            discord.SelectOption(label="Стримит", value="streaming", description="Streaming / стрим"),
            discord.SelectOption(label="Слушает", value="listening", description="Listening / слушает"),
            discord.SelectOption(label="Смотрит", value="watching", description="Watching / смотрит"),
            discord.SelectOption(label="Соревнуется", value="competing", description="Competing / соревнуется")
        ]
    )
    async def activity_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        # Первый аргумент — interaction, второй — select
        self.activity_choice = select.values[0]
        # Можно дать обратную связь (defer), но не обязательно
        await interaction.response.defer(ephemeral=True)

    # Select для статуса
    @discord.ui.select(
        placeholder="Выберите статус аккаунта",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="online", value="online", description="Доступен"),
            discord.SelectOption(label="idle", value="idle", description="Отсутствует"),
            discord.SelectOption(label="dnd", value="dnd", description="Не беспокоить"),
            discord.SelectOption(label="invisible", value="invisible", description="Скрыт")
        ]
    )
    async def status_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.status_choice = select.values[0]
        await interaction.response.defer(ephemeral=True)

    # Кнопка Подтвердить
    @discord.ui.button(label="Подтвердить", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Открываем модальное окно для ввода текста (и URL для стрима, если нужно)
        modal = ActivityModal(
            bot=self.bot,
            activity_type=self.activity_choice,
            status_str=self.status_choice
        )
        # Теперь interaction — действительно Interaction, можно отправить modal
        await interaction.response.send_modal(modal)

    # Кнопка Отмена
    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Операция отменена.", ephemeral=True)
        self.stop()


class activity(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="edit_activity",
        description="Изменить активность бота"
    )
    async def edit_activity(
        self,
        interaction: discord.Interaction
    ):
        # Проверка прав (можно изменить на свою логику)
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.HOST):
            await interaction.response.send_message("У вас недостаточно прав!", ephemeral=True)
            return

        view = AdminActivityView(bot=self.bot, author_id=interaction.user.id)
        embed = discord.Embed(
            title="Редактор активности бота",
            description="Выберите тип активности и статус, затем нажмите Подтвердить. После этого введите текст активности.",
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(activity(bot))
