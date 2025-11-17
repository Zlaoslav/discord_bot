import os
import asyncio
from typing import Any, Optional, Dict
import re
from pathlib import Path
import random
import sys
import sqlite3
import json
import logging

import discord
from discord.ext import commands
from discord.ui import View, Select
import discord.app_commands

import math
import ast

from playwright.async_api import async_playwright

# Импорт системы управления правами
sys.path.insert(0, str(Path(__file__).parent / "configs_folder"))
from configs_folder.perms_manager import PermRole, has_perm, get_user_roles, add_perm, remove_perm, init_perms, can_manage_role, get_hierarchy_level, get_role_description, INDEPENDENT_ROLES

# ------------------ access setup ------------------

# ------------------ logging setup ------------------
COLORS = {
    "DEBUG": "\033[38;5;245m",   # серый
    "INFO": "\033[38;5;39m",     # синий
    "WARNING": "\033[38;5;220m", # жёлтый
    "ERROR": "\033[38;5;203m",   # красный
    "CRITICAL": "\033[41m",      # белый на красном фоне
    "TIME": "\033[38;5;240m",    # тёмно-серый
    "SOURCE": "\033[38;5;141m",  # фиолетовый
    "RESET": "\033[0m"
}

class ColorFormatter(logging.Formatter):
    def format(self, record):
        level_color = COLORS.get(record.levelname, COLORS["RESET"])
        time_color = COLORS["TIME"]
        source_color = COLORS["SOURCE"]

        msg = super().format(record)

        msg = msg.replace(
            record.asctime, f"{time_color}{record.asctime}{COLORS['RESET']}"
        ).replace(
            record.levelname, f"{level_color}{record.levelname}{COLORS['RESET']}"
        ).replace(
            f"{record.filename}:{record.lineno}",
            f"{source_color}{record.filename}:{record.lineno}{COLORS['RESET']}"
        )

        return msg

# Формат с указанием файла и строки
formatter = ColorFormatter(
    "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d — %(message)s",
    "%Y-%m-%d %H:%M:%S"
)

handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)


# ------------------ setings setup ------------------
CONFIGS_FODLER = Path(__file__).with_name("configs_folder")
SETINGS_PATH = CONFIGS_FODLER / "setings.json"

with open(SETINGS_PATH, "r", encoding="utf-8") as f:
    config_setings = json.load(f)

DISCORD_TOKEN = config_setings["DISCORD_TOKEN"]
GUILD_ID = config_setings["GUILD_ID"]
PELLA_EMAIL = config_setings["PELLA_EMAIL"]
PELLA_PASSWORD = config_setings["PELLA_PASSWORD"]

intents = discord.Intents.default()
intents.members = True          # нужен для работы с Member объектами
intents.message_content = True  # нужен для префикс-команд (чтение сообщений)
bot = commands.Bot(command_prefix="?", intents=intents)  # ПРЕФИКС
GUILD = discord.Object(id=GUILD_ID)

COUNTER_TOLERANCE = 0.4  # допустимое отклонение у counting канала
OWNER_ID = 727105264486187090

# Инициализация системы прав
init_perms(OWNER_ID)

# ------------------ sounds setup ------------------
SCRIPT_DIR = Path(__file__).parent
USERNAME = os.getenv("USERNAME") or "unknown"
if USERNAME == "slavi":
    FFMPEG_PATH = r"C:\Code\Paths\ffmpeg\bin\ffmpeg.exe"
else:
    FFMPEG_PATH = SCRIPT_DIR / "ffmpeg"
BASE_DIR = Path(__file__).resolve().parent
SOUNDS_DIR = BASE_DIR / "sounds"
ALLOWED_EXT = (".mp3", ".wav", ".ogg", ".m4a")

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


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
        if interaction.user.id != self.author_id and not has_perm(interaction.user.id, PermRole.SOUNDPAD):
            await interaction.response.send_message(f"<@{interaction.user.id}>, Только инициатор может выбрать звук.", ephemeral=False)
            return
        # проверки
        #if not sound_path.exists() or not sound_path.is_file():
        #    await interaction.response.send_message("Файл звука не найден.", ephemeral=True)
        #    return

        if not Path(FFMPEG_PATH).exists():
            await interaction.response.send_message("ffmpeg не найден.", ephemeral=True)
            logging.error(f"FFMPEG not found at: {FFMPEG_PATH}")
            return
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
            vc.play(source, after=lambda err: logging.debug(f"play finished {err}") if err else None)
        except Exception as e:
            await interaction.followup.send(f"Ошибка воспроизведения: {e}", ephemeral=True)
            return
        # необязательно: можно отсоединять через некоторое время, или оставить постоянное подключение
        # пример: отсоединиться после окончания — сложнее отслеживать, можно поставить таймер в фоне

class SoundView(View):
    def __init__(self, sounds: list[str], author_id: int, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.add_item(SoundSelect(sounds, author_id))

# ------------------ gemini setup ------------------


# ------------------ BD setup ------------------


DB_PATH = os.path.join(os.path.dirname(__file__), "bot_state.db")  # файл базы рядом со скриптом

# --- Инициализация БД (выполняется при импорте модуля) ---
def _init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS restart_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            channel_id INTEGER
        );
    """)
    # гарантируем одну строку с id=1
    cur.execute("INSERT OR IGNORE INTO restart_state (id, channel_id) VALUES (1, NULL);")
    conn.commit()
    conn.close()

_init_db()

# --- Функции работы с состоянием рестарта ---
def save_restart_channel(channel_id: Optional[int]) -> None:
    """Сохраняет ID канала, куда надо отправить уведомление после рестарта."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE restart_state SET channel_id = ? WHERE id = 1;", (channel_id,))
    conn.commit()
    conn.close()

def pop_restart_channel() -> Optional[int]:
    """Возвращает сохранённый channel_id и очищает поле в БД."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT channel_id FROM restart_state WHERE id = 1;")
    row = cur.fetchone()
    channel_id = row[0] if row else None
    # очищаем
    cur.execute("UPDATE restart_state SET channel_id = NULL WHERE id = 1;")
    conn.commit()
    conn.close()
    return channel_id

async def notify_after_restart():
    # вызывается из on_ready после того как бот залогинился
    channel_id = pop_restart_channel()
    if not channel_id:
        return  # ничего не нужно делать

    # пытаемся найти канал и отправить сообщение
    try:
        guild = bot.get_guild(GUILD_ID)
        if guild:
            ch = guild.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        else:
            ch = await bot.fetch_channel(channel_id)
    except Exception as e:
        logging.warning(f"Не удалось получить канал для уведомления о рестарте: {e}")
        return

    try:
        # проверяем права бота в канале
        perms = ch.permissions_for(guild.me if (guild := getattr(ch, "guild", None)) else bot.user)
        if not perms.send_messages:
            # если нельзя писать в канале — попытка DM владельцу
            owner = bot.get_user(OWNER_ID) or await bot.fetch_user(OWNER_ID)
            try:
                await owner.send(f"⚠ Не удалось отправить уведомление о рестарте в канал {channel_id} — нет прав.")
            except Exception:
                pass
            return

        await ch.send("✅ Бот успешно перезапущен.")
    except Exception as e:
        logging.warning(f"Ошибка при отправке уведомления о рестарте: {e}")
        # попытка написать владельцу в личку
        try:
            owner = bot.get_user(OWNER_ID) or await bot.fetch_user(OWNER_ID)
            await owner.send(f"Ошибка при отправке уведомления о рестарте: {e}")
        except Exception:
            pass

# ------------------ calculate setup ------------------


_PREPROCESS_REPLACES = {
    '^': '**',
    'tg(': 'tan(',
    'ctg(': '1/tan(',
    'ln(': 'log('
}

_SAFE_NAMES = {
    'pi': math.pi,
    'e': math.e,
    'sin': math.sin,
    'cos': math.cos,
    'tan': math.tan,
    'asin': math.asin,
    'acos': math.acos,
    'atan': math.atan,
    'sinh': math.sinh,
    'cosh': math.cosh,
    'tanh': math.tanh,
    'sqrt': math.sqrt,
    'log': math.log,
    'log10': math.log10,
    'log2': math.log2,
    'abs': abs,
    'floor': math.floor,
    'ceil': math.ceil,
    'round': round,
    'factorial': math.factorial,
    'pow': pow,
}

_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.LShift,
    ast.RShift,
    ast.BitXor,
    ast.BitAnd,
    ast.BitOr,
)

def _preprocess(expr: str) -> str:
    s = expr
    for k, v in _PREPROCESS_REPLACES.items():
        s = s.replace(k, v)
    return s

def _find_names(node: ast.AST, found: set):
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            found.add(child.id)

def _check_nodes(node: ast.AST):
    for n in ast.walk(node):
        if not isinstance(n, _ALLOWED_NODES):
            raise ValueError(f"{type(n).__name__}")

def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            return left / right
        if isinstance(op, ast.FloorDiv):
            return left // right
        if isinstance(op, ast.Mod):
            return left % right
        if isinstance(op, ast.Pow):
            return left ** right
        if isinstance(op, ast.LShift):
            return left << right
        if isinstance(op, ast.RShift):
            return left >> right
        if isinstance(op, ast.BitXor):
            return left ^ right
        if isinstance(op, ast.BitAnd):
            return left & right
        if isinstance(op, ast.BitOr):
            return left | right
        raise ValueError(f"BinOp {type(op).__name__}")

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError(f"UnaryOp {type(node.op).__name__}")

    if isinstance(node, ast.Name):
        if node.id in _SAFE_NAMES:
            return _SAFE_NAMES[node.id]
        raise NameError(node.id)

    if isinstance(node, ast.Call):
        func = node.func
        if not isinstance(func, ast.Name):
            raise ValueError("Call must be simple name")
        func_name = func.id
        if func_name not in _SAFE_NAMES:
            raise NameError(func_name)
        fn = _SAFE_NAMES[func_name]
        args = [_eval_node(a) for a in node.args]
        return fn(*args)

    raise ValueError(f"Unsupported node {type(node).__name__}")

# ------------------ Counting chanel setup ------------------
def _init_counter_table():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS counter_single (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            channel_id INTEGER,
            next_expected INTEGER NOT NULL
        );
    """)
    # гарантируем одну строку с id=1
    cur.execute("INSERT OR IGNORE INTO counter_single (id, channel_id, next_expected) VALUES (1, NULL, 1);")
    conn.commit()
    conn.close()

_init_counter_table()

def set_counter_channel(channel_id: Optional[int], start_value: int = 1) -> None:
    """Установить (или переназначить) канал счётчика. Один канал в системе."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE counter_single SET channel_id = ?, next_expected = ? WHERE id = 1;", (channel_id, start_value))
    conn.commit()
    conn.close()

def unset_counter_channel() -> None:
    """Отключить канал счётчика (делает channel_id NULL)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE counter_single SET channel_id = NULL WHERE id = 1;")
    conn.commit()
    conn.close()

def get_counter_state() -> Optional[tuple[int, int]]:
    """
    Возвращает (channel_id, next_expected) или None, если channel_id NULL.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT channel_id, next_expected FROM counter_single WHERE id = 1;")
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    channel_id, next_expected = row
    if channel_id is None:
        return None
    return (int(channel_id), int(next_expected))



def inc_counter() -> None:
    """Увеличить next_expected на 1."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE counter_single SET next_expected = next_expected + 1 WHERE id = 1;")
    conn.commit()
    conn.close()




# ----------------------------
# очистка и восстановление локальных команд 
# ----------------------------
async def sync_local_slash():
    try:
        bot.tree.copy_global_to(guild=GUILD)
        synced = await bot.tree.sync(guild=GUILD)
        logging.debug(f"✅ Все локальные слэш-команды синхронизованы для {GUILD}")
        return synced
    except Exception as e:
        logging.error(f"Ошибка при sync_local_slash: {e}")
        return None

async def clear_local_slash():
    try:
#        bot.tree.clear_commands(guild=GUILD)
#        await bot.tree.sync(guild=GUILD)
#        logging.debug("✅ Все локальные слэш-команды удалены")
        return True
    except Exception as e:
        logging.error(f"Ошибка при clear_local_slash: {e}")
        return False

async def restart_process(interaction_or_ctx=None):
    """
    Сохраняет канал (если interaction_or_ctx передан), отвечает пользователю и перезапускает процесс.
    Если передан interaction (slash) — отправляет response, если ctx (prefix) — использует ctx.send.
    """
    # определяем канал для уведомления:
    channel_id = None
    try:
        # interaction (app command)
        if hasattr(interaction_or_ctx, "channel") and hasattr(interaction_or_ctx, "response"):
            # если interaction содержит custom attribute restart_target (см. команду ниже),
            # то он уже сохранил нужный channel_id в interaction_or_ctx.restart_target
            channel_id = getattr(interaction_or_ctx, "restart_target", None) or interaction_or_ctx.channel.id
            # быстрый ответ перед рестартом (чтобы не получить "Приложение не отвечает")
            await interaction_or_ctx.response.send_message("♻️ Перезапускаюсь...", ephemeral=True)
        # ctx (prefix)
        elif hasattr(interaction_or_ctx, "send") and hasattr(interaction_or_ctx, "author"):
            channel_id = getattr(interaction_or_ctx, "restart_target", None) or interaction_or_ctx.channel.id
            await interaction_or_ctx.send("♻️ Перезапускаюсь...")
    except Exception:
        # если не получилось ответить — всё равно продолжим рестарт, но сохраним канал
        pass

    # сохраняем в БД канал (может быть None)
    save_restart_channel(int(channel_id) if channel_id is not None else None)

    # небольшая пауза чтобы response/сообщение успели отправиться в сеть
    await asyncio.sleep(0.5)

    # перезапуск процесса
    python = sys.executable
    os.execv(python, [python] + sys.argv)


# ------------------ bot commands ------------------
def mainbotstart():

    # ----------------------------
    # ПРЕФИКС-КОМАНДА (пример)
    # ----------------------------
    @bot.command(name="дай_пять")
    async def ping_cmd(ctx: commands.Context):
        await ctx.send("https://cdn.discordapp.com/attachments/1350866065818783788/1434491390192255096/c0aced7c-94ef-4d24-aafa-480c618a74dd.gif?ex=69106eb6&is=690f1d36&hm=ba4189460e7fd7061f8f2928c6a75205ed4d8aaeeb5c04a3fb263745f2236cda&")

    @bot.command(name="ping")
    async def ping_cmd(ctx: commands.Context):
        await ctx.send("Pong!")

    @bot.command(name="disablecmds")
    async def disablecmds(ctx: commands.Context):
        # проверка прав: нужна роль OWNER
        if not has_perm(ctx.author.id, PermRole.OWNER):
            await ctx.send("У вас нет прав для этой команды.")
            return

        # запускаем ассинхронный helper и ждём результат
        result = await clear_local_slash()
        if result is True:
            await ctx.send("✅ Удалены локальные слэш-команды")
        else:
            await ctx.send("❌ Ошибка при удалении локальных команд. Смотри лог.")

    @bot.command(name="enablecmds")
    async def enablecmds(ctx: commands.Context):
        if not has_perm(ctx.author.id, PermRole.OWNER):
            await ctx.send("У вас нет прав для этой команды.")
            return

        result = await sync_local_slash()
        if result is None:
            await ctx.send("❌ Ошибка при синхронизации. Смотри лог.")
            return

        if len(result) != 0:
            await ctx.send(f"✅ Синхронизировано {len(result)} команд(ы).")
        else:
            await ctx.send("⚠ Синхронизация прошла, но вернулось 0 команд.")

    @bot.command(name="shutdownbot")
    async def shutdown_cmd(ctx: commands.Context):
        if not has_perm(ctx.author.id, PermRole.HOST):
            await ctx.send("У вас нет прав для этой команды.")
            return
        await ctx.send("Loading...")

        await clear_local_slash()

        await ctx.send("Success!")

        try:
            await ctx.guild.voice_client.disconnect()
        except: pass

        await bot.close()

        os._exit(0)

    @bot.command(name="restartbot")
    async def restart_prefix(ctx: commands.Context, channel_id: Optional[int] = None):
        if not has_perm(ctx.author.id, PermRole.HOST):
            await ctx.send("У вас нет прав для этой команды.")
            return

        if channel_id:
            ctx.restart_target = channel_id
        else:
            ctx.restart_target = ctx.channel.id

        await restart_process(ctx)


    # ----------------------------
    # SLASH: /myperms
    # ----------------------------
    @bot.tree.command(name="myperms", description="Показать права бота на сервере")
    async def myperms(interaction: discord.Interaction):
        if not has_perm(interaction.user.id, PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logging.debug(f"{interaction.user.name} try use myperms")
            return

        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=True)
            return

        perms = interaction.guild.me.guild_permissions
        allowed = [name for name, value in perms if value]
        if not allowed:
            await interaction.response.send_message("У бота нет прав на этом сервере.", ephemeral=True)
            return

        text = "\n".join(f"• {perm}" for perm in allowed)
        await interaction.response.send_message(f"**Права бота:**\n```{text}```", ephemeral=True)

    # ----------------------------
    # SLASH: /roles [member]
    # ----------------------------
    @bot.tree.command(name="roles", description="Показать роли участника и их ID")
    async def roles(interaction: discord.Interaction, member: discord.Member | None = None):

        if not has_perm(interaction.user.id, PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logging.debug(f"{interaction.user.name} try use roles")
            return
        
        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=True)
            return

        target = member or interaction.user
        if isinstance(target, discord.User):
            target = interaction.guild.get_member(target.id)

        if target is None:
            await interaction.response.send_message("Не удалось найти участника на сервере.", ephemeral=True)
            return

        roles_list = [r for r in target.roles if r.id != interaction.guild.id]
        if not roles_list:
            await interaction.response.send_message(f"У {target.display_name} нет ролей.", ephemeral=True)
            return

        text = "\n".join(f"• {r.name} — `{r.id}`" for r in roles_list)
        await interaction.response.send_message(f"Роли {target.mention}:\n```{text}```", ephemeral=True)

    # ----------------------------
    # SLASH: /listperms [member]
    # ----------------------------
    @bot.tree.command(name="listperms", description="Показать пользовательские права из perms_data.json")
    async def listperms(interaction: discord.Interaction, member: discord.Member | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=True)
            return

        target = member or interaction.user
        try:
            user_id = int(target.id)
        except Exception:
            await interaction.response.send_message("Не удалось получить ID пользователя.", ephemeral=True)
            return

        roles = get_user_roles(user_id)
        if not roles:
            await interaction.response.send_message(f"У {target.mention} нет назначенных прав.", ephemeral=True)
            return

        lines = [f"• {r.value} — {get_role_description(r)}" for r in sorted(roles, key=lambda x: x.value)]
        await interaction.response.send_message(f"Права {target.mention}:\n```\n" + "\n".join(lines) + "\n```", ephemeral=True)

    # ----------------------------
    # Функция автодополнения для ролей в /editperms
    # ----------------------------
    async def role_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[discord.app_commands.Choice[str]]:
        """Автодополнение для списка доступных независимых ролей."""
        roles = [r.value for r in INDEPENDENT_ROLES]
        # Фильтруем по введённому тексту
        choices = [
            discord.app_commands.Choice(
                name=r.upper(),
                value=r
            )
            for r in roles
            if r.startswith(current.lower())
        ]
        return choices[:25]  # Discord ограничивает до 25 вариантов

    # ----------------------------
    # SLASH: /editperms user role action
    # action: add|remove
    # ----------------------------
    @bot.tree.command(name="editperms", description="Добавить/удалить роль пользователю (permsmanager+)")
    async def editperms(
        interaction: discord.Interaction, 
        member: discord.Member, 
        set: bool
    ):
        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=True)
            return

        manager_id = int(interaction.user.id)
        target_id = int(member.id)

        # проверка прав инициатора
        if not has_perm(manager_id, PermRole.PERMSMANAGER):
            await interaction.response.send_message("У вас нет прав на изменение прав пользователей.", ephemeral=True)
            return
        # Представляем пользователю Select с доступными ролями
        class RoleSelect(discord.ui.Select):
            def __init__(self, manager_id: int, target_id: int, set_flag: bool):
                options = []
                for r in PermRole:
                    # не показываем защищённые роли в списке
                    if r in (PermRole.OWNER, PermRole.HOST, PermRole.PERMSMANAGER):
                        continue
                    options.append(discord.SelectOption(label=r.value.upper(), value=r.value, description=get_role_description(r)))

                super().__init__(placeholder="Выберите роль...", min_values=1, max_values=1, options=options)
                self.manager_id = manager_id
                self.target_id = target_id
                self.set_flag = set_flag

            async def callback(self, interaction: discord.Interaction):
                role_value = self.values[0]
                try:
                    role_enum = PermRole(role_value)
                except ValueError:
                    await interaction.response.send_message(f"Неизвестная роль `{role_value}`.", ephemeral=True)
                    return

                ok, msg = can_manage_role(self.manager_id, self.target_id, role_enum)
                if not ok:
                    await interaction.response.send_message(msg, ephemeral=True)
                    return

                if self.set_flag:
                    added = add_perm(self.target_id, role_enum)
                    if added:
                        await interaction.response.send_message(f"✅ Роль `{role_enum.value}` добавлена пользователю <@{self.target_id}>.", ephemeral=True)
                    else:
                        await interaction.response.send_message(f"⚠️ У пользователя уже есть роль `{role_enum.value}`.", ephemeral=True)
                else:
                    removed = remove_perm(self.target_id, role_enum)
                    if removed:
                        await interaction.response.send_message(f"✅ Роль `{role_enum.value}` удалена у <@{self.target_id}>.", ephemeral=True)
                    else:
                        await interaction.response.send_message(f"❌ Не удалось удалить роль `{role_enum.value}` (возможно её нет или роль защищена).", ephemeral=True)

        view = discord.ui.View(timeout=60)
        view.add_item(RoleSelect(manager_id, target_id, set))
        await interaction.response.send_message(f"Выберите роль для {'установки' if set else 'удаления'} пользователю {member.mention}:", view=view, ephemeral=True)

    # ----------------------------
    # SLASH: /toggle_role role [member]
    # ----------------------------
    @bot.tree.command(name="toggle_role", description="Добавить/убрать роль участнику.")
    async def toggle_role(interaction: discord.Interaction, role: discord.Role, member: discord.Member | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=True)
            return
        
        if not has_perm(interaction.user.id, PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logging.debug(f"{interaction.user.name} try use toggle_role")
            return
        
        bot_member = interaction.guild.me
        if bot_member is None:
            await interaction.response.send_message("Не удалось получить данные бота на сервере.", ephemeral=True)
            return

        if not bot_member.guild_permissions.manage_roles:
            await interaction.response.send_message("У бота нет права Manage Roles. Дай право и попробуй снова.", ephemeral=True)
            return

        target = member or interaction.user
        if isinstance(target, discord.User):
            target = interaction.guild.get_member(target.id)

        if target is None:
            await interaction.response.send_message("Не удалось найти участника на сервере.", ephemeral=True)
            return

        if role.position >= bot_member.top_role.position:
            await interaction.response.send_message("Не могу управлять этой ролью. Роль выше или равна роли бота.", ephemeral=True)
            return

        if target.top_role.position >= bot_member.top_role.position and target != bot_member:
            await interaction.response.send_message("Не могу изменять роли этого участника (его роль выше или равна роли бота).", ephemeral=True)
            return

        try:
            if role in target.roles:
                await target.remove_roles(role, reason=f"toggle_role by {interaction.user} ({interaction.user.id})")
                await interaction.response.send_message(f"Роль `{role.name}` убрана у {target.mention}.", ephemeral=True)
            else:
                await target.add_roles(role, reason=f"toggle_role by {interaction.user} ({interaction.user.id})")
                await interaction.response.send_message(f"Роль `{role.name}` выдана {target.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("Недостаточно прав для изменения ролей. Проверь позицию роли бота и права.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Ошибка при изменении роли: {e}", ephemeral=True)

    # ----------------------------
    # SLASH: /say message [channel]
    # ----------------------------
    @bot.tree.command(name="say", description="Отправка сообщения в канал")
    async def say(interaction: discord.Interaction, message: str, channel: discord.TextChannel | None = None):

        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=False)
            return
        
        if not has_perm(interaction.user.id, PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logging.debug(f"{interaction.user.name} try use say")
            return
        
        error_message = None
        targetchanel = channel or interaction.channel

        try:
            await targetchanel.send(message)
        except discord.Forbidden:
            error_message = "У бота недостаточно прав для отправки в этот канал"
        except Exception as e:
            error_message = "Ошибка отправки!"
            logging.error(f"Ошибка отправки say: {e}")
        finally:
            if error_message:
                await interaction.response.send_message(error_message , ephemeral=True)
            else:
                await interaction.response.send_message("Отправленно!", ephemeral=True)

    # ----------------------------
    # SLASH: /calculate expression
    # ----------------------------
    @bot.tree.command(name="calculate", description="Вычислить математическое выражение.")
    async def calculate(interaction: discord.Interaction, expression: str):
        await interaction.response.defer(ephemeral=False)

        expr = expression.strip()
        if not expr:
            await interaction.followup.send("Пустое выражение.", ephemeral=True)
            return

        expr = _preprocess(expr)

        try:
            node = ast.parse(expr, mode='eval')
        except Exception as e:
            await interaction.followup.send(f"Синтаксическая ошибка: {e}", ephemeral=True)
            return

        try:
            _check_nodes(node)
        except Exception as e:
            await interaction.followup.send(f"Недопустимый элемент в выражении: {e}", ephemeral=True)
            return

        used = set()
        _find_names(node, used)
        unknown = [name for name in used if name not in _SAFE_NAMES]
        if unknown:
            await interaction.followup.send(f"Неизвестные идентификаторы: {', '.join(sorted(unknown))}", ephemeral=True)
            return

        try:
            result = _eval_node(node)
        except NameError as ne:
            await interaction.followup.send(f"Неизвестная функция или константа: {ne}", ephemeral=True)
            return
        except Exception as e:
            await interaction.followup.send(f"Ошибка при вычислении: {e}", ephemeral=True)
            return

        if isinstance(result, float):
            out = f"{result:.12g}"
        else:
            out = str(result)

        await interaction.followup.send(f"`{expression}` = **{out}**", ephemeral=False)


    # ----------------------------
    # СЕКЦИЯ COINGING КАНАЛА
    # ----------------------------
    # --- Команды управления счётчиком ---
    @bot.tree.command(name="set_counter", description="Установить канал для счётчика (owner only).")
    async def set_counter(interaction: discord.Interaction, channel: discord.TextChannel | None = None, start_value : int | None = None):
        if not has_perm(interaction.user.id, PermRole.OWNER):
            await interaction.response.send_message("У вас нет прав для этой команды.", ephemeral=True)
            return
        start_value = start_value or 1
        target = channel or interaction.channel
        if target is None:
            await interaction.response.send_message("Не удалось определить канал.", ephemeral=True)
            return

        # один канал в системе — просто перезаписываем
        set_counter_channel(int(target.id), start_value=start_value)
        await interaction.response.send_message(f"Счётчик установлен в канал {target.mention}. Начинаем с {start_value}.", ephemeral=True)

    @bot.tree.command(name="unset_counter", description="Отключить канал счётчика (owner only).")
    async def unset_counter(interaction: discord.Interaction):
        if not has_perm(interaction.user.id, PermRole.OWNER):
            await interaction.response.send_message("У вас нет прав для этой команды.", ephemeral=True)
            return

        unset_counter_channel()
        await interaction.response.send_message("Счётчик отключён.", ephemeral=True)
    # --- Обработчик входящих сообщений ---
 
    async def on_counting_message(message: discord.Message):
    # игнорируем ботов
        if message.author.bot:
            return

        # получаем состояние единственного счётчика
        cs = get_counter_state()
        if cs is None:
            return  # счётчик не настроен

        channel_id, next_expected = cs
        # работаем только в настроенном канале
        if message.channel.id != channel_id:
            return

        expr = (message.content or "").strip()
        if not expr:
            return

        # парсим и вычисляем (те же функции что и /calculate)
        try:
            expr_proc = _preprocess(expr)
            node = ast.parse(expr_proc, mode='eval')
            _check_nodes(node)
            used = set()
            _find_names(node, used)
            unknown = [name for name in used if name not in _SAFE_NAMES]
            if unknown:
                return  # неизвестные идентификаторы — игнорируем
            result = _eval_node(node)
        except Exception:
            return  # ошибка парсинга/вычисления — игнорируем

        try:
            value = float(result)
        except Exception:
            return

        expected = float(next_expected)
        if abs(value - expected) <= COUNTER_TOLERANCE:
            try:
                await message.add_reaction("✅")
            except Exception:
                pass
            inc_counter()
        else:
            try:
                await message.add_reaction("⚠️")
            except Exception:
                pass
            prev_num = expected - 1
            try:
                await message.channel.send(f"Ожидаемое предыдущее число: **{int(prev_num)}**")
            except Exception:
                pass

    # ----------------------------
    # SLASH: /askgpt message
    # ----------------------------
    @bot.tree.command(name="askgpt", description="Спросить нейросеть")
    async def say(interaction: discord.Interaction, usermessage: str):
        await interaction.response.defer(ephemeral=False)

        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=False)
            return
        
        if not has_perm(interaction.user.id, PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logging.debug(f"{interaction.user.name} try use askgpt")
            return
        
        await interaction.response.send_message("Я в россии, увы без гемини", ephemeral=False)
    
    # ----------------------------
    # SLASH: /stopsound
    # ----------------------------
    @bot.tree.command(name="stopsound", description="Остановить воспроизведение звука")
    async def stopsound(interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=False)
            return
        
        if not has_perm(interaction.user.id, PermRole.SOUNDPAD):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=False)
            logging.debug(f"{interaction.user.name} try use stopsound")
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
    # ----------------------------
    # SLASH: /leave message
    # ----------------------------
    @bot.tree.command(name="leave", description="Выйти из войса")
    async def leave(interaction: discord.Interaction):

        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=False)
            return
        
        if not has_perm(interaction.user.id, PermRole.LEAVE):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=False)
            logging.debug(f"{interaction.user.name} try use leave")
            return
        
        
        try:
            await interaction.guild.voice_client.disconnect()

            await interaction.response.send_message("✅ Отключился к от канала!", ephemeral=False)
        except Exception as e:
            logging.warning(e)
            if e == "NoneType":
                await interaction.response.send_message(f"Ошибка: бот не в голосовом канале!", ephemeral=False)
            else:
                await interaction.response.send_message(f"Ошибка: подключения!", ephemeral=False)


    # ----------------------------
    # SLASH: /demute mute deafen
    # ----------------------------
    @bot.tree.command(name="demute", description="Включить или выключить микрофон/звук боту или участнику")
    async def say(interaction: discord.Interaction, mute : bool | None=None, deafen : bool | None=None, member : discord.Member | None=None):

        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=False)
            return
        
        if not has_perm(interaction.user.id, PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logging.debug(f"{interaction.user.name} try use demute")
            return
        
        if mute == None and deafen == None:
            await interaction.response.send_message("Укажите хотя бы 1 аргумент!.", ephemeral=True)
            return

        target = member or interaction.guild.me
        try:
            if mute != None:
                await target.edit(mute=mute)
            if deafen != None:
                await target.edit(deafen=deafen)
            await interaction.response.send_message(f"Успешно! (mute: {mute}, deafen: {deafen}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message("Ошибка! Вероятно у бота недостаточно прав.", ephemeral=True)
            logging.warning(e)
        
        
    # ----------------------------
    # SLASH: /join message
    # ----------------------------
    @bot.tree.command(name="join", description="Войти в войс")
    async def say(interaction: discord.Interaction, channel: discord.VoiceChannel | None=None):
        await interaction.response.defer(ephemeral=False)
        try:
            await interaction.guild.me.edit(mute=False)
            await interaction.guild.me.edit(deafen=True)
        except: pass
        if interaction.guild is None:
            await interaction.followup.send("Эта команда работает только на сервере.", ephemeral=False)
            return
        
        if not has_perm(interaction.user.id, PermRole.JOIN):
            await interaction.followup.send("У вас недостаточно прав использовать эту команду!.", ephemeral=False)
            logging.debug(f"{interaction.user.name} try use join")
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
            logging.warning(e)
            await interaction.followup.send(f"Ошибка: отключения!", ephemeral=False)


    # ----------------------------
    # SLASH: /soundpanel
    # ----------------------------
    @bot.tree.command(name="soundpanel", description="Выбрать и проиграть звук из списка доступных")
    async def playsound(interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=False)
            return
        
        if not has_perm(interaction.user.id, PermRole.SOUNDPAD):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logging.debug(f"{interaction.user.name} try use soundpanel ({interaction.user.id})")
            return
        
        sounds = list_sounds()
        if not sounds:
            await interaction.response.send_message("Список звуков пуст.", ephemeral=True)
            return

        # ответ с меню
        view = SoundView(sounds, interaction.user.id)
        await interaction.response.send_message("Выберите звук для воспроизведения:", view=view, ephemeral=False)

    # ----------------------------
    # SLASH: Команды кубиков
    # ----------------------------
    @bot.tree.command(name="d6", description="Подкинуть кубик d6")
    async def d6(interaction: discord.Interaction):
        await interaction.response.send_message("Подкинув кубик d6 выпало: `" + str(random.randint(1, 6)) + "`")

    @bot.tree.command(name="d20", description="Подкинуть кубик d20")
    async def d20(interaction: discord.Interaction):
        await interaction.response.send_message("Подкинув кубик d20 выпало: `" + str(random.randint(1, 20)) + "`")
    
    @bot.tree.command(name="d100", description="Подкинуть кубик d100")
    async def d100(interaction: discord.Interaction):
        await interaction.response.send_message("Подкинув кубик d100 выпало: `" + str(random.randint(1, 100)) + "`")

    @bot.tree.command(name="d_any", description="Подкинуть кубик с любыми числами")
    async def d_any(interaction: discord.Interaction, end: int, start: int | None=None):
        if start == None: start = 1
        if end == None: end = 100
        try:
            await interaction.response.send_message(f"Подкинув кубик от {start} до {end} выпало: `{random.randint(start, end)}`")
        except:
            await interaction.response.send_message("Ошибка, недопустимые числа!", ephemeral=True)

    # ----------------------------
    # ОБРАБОТКА ОСТАЛЬНЫХ СООБЩЕНИЙ
    # ----------------------------      
    async def on_sus_message(message):
        if message.author.bot:
            return
        if "<@1409084528588488727>" in message.content.lower():
            # reply автоматически упомянет автора (mention_author=True по умолчанию)
            await message.reply(r"https://tenor.com/view/fuck-you-gif-27037587", mention_author=True, delete_after=10)

        if "осуждаю" in message.content.lower():
            await message.reply(r"https://tenor.com/view/%D1%81%D1%82%D0%B8%D0%BD%D1%82-%D1%81%D1%82%D0%B8%D0%BD%D1%82%D0%B8%D0%BA-stint-stintik-%D0%B8%D1%81%D0%BF%D1%83%D0%B3%D0%B0%D0%BB%D1%81%D1%8F-gif-8740975965519379714", mention_author=True, delete_after=10)

        if r"||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​||||​" in message.content.lower():
            await message.reply(r"https://tenor.com/view/ghost-ping-troll-discord-gif-20744771", mention_author=True, delete_after=10)
        
        if "@everyone" in message.content.lower():
            await message.reply(r"https://tenor.com/view/everyone-discord-konosuba-gif-21395141", mention_author=True, delete_after=10)
        
        if "@here" in message.content.lower():
            await message.reply(r"https://tenor.com/view/everyone-discord-gif-18237159", mention_author=True, delete_after=10)
        
        
        TENOR_RE = re.compile(r"https?://(?:www\.)?tenor\.com", re.IGNORECASE)
        DS_RE = re.compile(r"https://media.discordapp.net/")
        if TENOR_RE.search(message.content or "") or DS_RE.search(message.content or ""):
            # получаем права автора именно в этом канале
            perms = message.channel.permissions_for(message.author)
            # attach_files — право прикреплять файлы/гифки      
            if not perms.attach_files:
                # проверяем, может ли бот писать в канал
                bot_perms = message.channel.permissions_for(message.guild.me if message.guild else bot.user)
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
                

    @bot.event
    async def on_message(message: discord.Message):
        await bot.process_commands(message)
        await on_counting_message(message)
        await on_sus_message(message)
    

        
    

    # ----------------------------
    # on_ready: синхронизация слэш-команд
    # ----------------------------
    @bot.event
    async def on_ready():
        
        try:
            await notify_after_restart()
        except Exception as e:
            logging.error(f"Ошибка при отправке уведомления после рестарта: {e}")

#        try:
#            synced = await sync_local_slash()
#            logging.debug(f"Синхронизировано {len(synced)} команд(ы) для гильдии {GUILD_ID}")
#        except Exception as e:
#            logging.error("Ошибка при sync:", type(e).__name__, e)


        logging.info(f"✅ Ready: {bot.user}")

    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    mainbotstart()
