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
import socket
import time

import discord
from discord.ext import commands
from discord.ui import View, Select
import discord.app_commands

import math
import ast

from playwright.async_api import async_playwright


import configs_folder.perms_manager as perms_manager
import chem_reactions 


# ------------------ main vars setup ------------------
SCRIPT_DIR = Path(__file__).parent
USERNAME = os.getenv("USERNAME") or "unknown"
HOSTNAME = socket.gethostname()
starttime = time.time()

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

def format_duration(seconds: int) -> str:
    d, seconds = divmod(seconds, 86400)
    h, seconds = divmod(seconds, 3600)
    m, s = divmod(seconds, 60)
    return "".join(f"{x}{y}" for x, y in [(d,"d"),(h,"h"),(m,"m"),(s,"s")] if x)

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
intents.reactions = True        # нужен для обработки реакций
intents.voice_states = True     # нужен для отслеживания входа/выхода в войс
bot = commands.Bot(command_prefix="?", intents=intents)  # ПРЕФИКС
GUILD = discord.Object(id=GUILD_ID)

COUNTER_TOLERANCE = 0.4  # допустимое отклонение у counting канала
OWNER_ID = 727105264486187090

# Инициализация системы прав
perms_manager.init_perms(OWNER_ID)

# ------------------ sounds setup ------------------

if USERNAME == "slavi":
    FFMPEG_PATH = r"C:\Code\Paths\ffmpeg\bin\ffmpeg.exe"
else:
    FFMPEG_PATH = str(SCRIPT_DIR / "ffmpeg")  # Преобразуем в строку
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
        if interaction.user.id != self.author_id or not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.SOUNDPAD):
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
        
        # Проверяем и устанавливаем права на выполнение если нужно
        try:
            import stat
            ffmpeg_stat = os.stat(FFMPEG_PATH)
            if not (ffmpeg_stat.st_mode & stat.S_IXUSR):
                os.chmod(FFMPEG_PATH, ffmpeg_stat.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                logging.info(f"Установлены права на выполнение для {FFMPEG_PATH}")
        except Exception as e:
            logging.warning(f"Не удалось установить права на выполнение ffmpeg: {e}")
        
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
    
    # Таблица для join_leave
    cur.execute("""
        CREATE TABLE IF NOT EXISTS join_leave (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            channel_id INTEGER
        );
    """)
    # гарантируем одну строку с id=1
    cur.execute("INSERT OR IGNORE INTO join_leave (id, channel_id) VALUES (1, NULL);")
    
    # Таблица для role_reaction (реакции с автоматической выдачей ролей)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS role_reactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER UNIQUE NOT NULL,
            channel_id INTEGER NOT NULL,
            emoji TEXT NOT NULL,
            role_id INTEGER NOT NULL
        );
    """)
    # Таблица для tempvoice (триггер-каналы и настройки)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tempvoice (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            trigger_channel_id INTEGER UNIQUE NOT NULL,
            panel_message_id INTEGER,
            settings TEXT DEFAULT '{}',
            current_map TEXT DEFAULT '{}'
        );
    """)
    conn.commit()
    conn.close()

_init_db()

# --- Функции работы с каналом join_leave ---
def save_join_leave_channel(channel_id: Optional[int]) -> None:
    """Сохраняет ID канала, куда надо отправить уведомление при выходе/входе участников на сервер."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE join_leave SET channel_id = ? WHERE id = 1;", (channel_id,))
    conn.commit()
    conn.close()

def get_join_leave_channel() -> Optional[int]:
    """Возвращает сохранённый channel_id для join/leave."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT channel_id FROM join_leave WHERE id = 1;")
    row = cur.fetchone()
    channel_id = row[0] if row else None
    conn.close()
    return channel_id

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

# --- Функции работы с role_reactions ---
def save_role_reaction(message_id: int, channel_id: int, emoji: str, role_id: int) -> None:
    """Сохраняет информацию о role_reaction в БД."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO role_reactions (message_id, channel_id, emoji, role_id)
        VALUES (?, ?, ?, ?)
    """, (message_id, channel_id, emoji, role_id))
    conn.commit()
    conn.close()

def get_role_reaction(message_id: int, emoji: str) -> Optional[tuple]:
    """Получает информацию о role_reaction: (message_id, channel_id, emoji, role_id)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT message_id, channel_id, emoji, role_id FROM role_reactions
        WHERE message_id = ? AND emoji = ?
    """, (message_id, emoji))
    row = cur.fetchone()
    conn.close()
    return row

def get_all_role_reactions_for_message(message_id: int) -> list:
    """Получает все role_reactions для сообщения."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT message_id, channel_id, emoji, role_id FROM role_reactions
        WHERE message_id = ?
    """, (message_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def delete_role_reaction(message_id: int) -> None:
    """Удаляет role_reaction из БД по ID сообщения."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM role_reactions WHERE message_id = ?
    """, (message_id,))
    conn.commit()
    conn.close()

# ------------------ tempvoice helpers ------------------
def save_tempvoice_trigger(guild_id: int, trigger_channel_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # default settings
    default_settings = {
        "prefix": "TempVoice ",
        "user_limit": 0,
        "bitrate": None,
        "slowmode": 0,
        "chat_enabled": True,
        "locked": False,
        "allowed_users": [],
        "allowed_roles": [],
        "blocked_users": [],
        "blocked_roles": [],
        "trusted_users": []
    }
    # allow trigger_channel_id==0 to mean "global / no specific trigger"
    trig = int(trigger_channel_id) if trigger_channel_id is not None else 0
    cur.execute("INSERT OR REPLACE INTO tempvoice (guild_id, trigger_channel_id, settings, current_map) VALUES (?, ?, ?, ?)",
                (guild_id, trig, json.dumps(default_settings, ensure_ascii=False), json.dumps({}, ensure_ascii=False)))
    conn.commit()
    conn.close()

def remove_tempvoice_trigger(trigger_channel_id: int) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM tempvoice WHERE trigger_channel_id = ?", (trigger_channel_id,))
    conn.commit()
    conn.close()

def get_tempvoice_by_trigger(trigger_channel_id: int) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, guild_id, trigger_channel_id, panel_message_id, settings, current_map FROM tempvoice WHERE trigger_channel_id = ?", (trigger_channel_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    tid, guild_id, trig_id, panel_id, settings_json, map_json = row
    try:
        settings = json.loads(settings_json or "{}")
    except Exception:
        settings = {}
    try:
        current_map = json.loads(map_json or "{}")
    except Exception:
        current_map = {}
    return {"id": tid, "guild_id": guild_id, "trigger_channel_id": trig_id, "panel_message_id": panel_id, "settings": settings, "current_map": current_map}

def get_tempvoice_by_guild(guild_id: int) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, guild_id, trigger_channel_id, panel_message_id, settings, current_map FROM tempvoice WHERE guild_id = ?", (guild_id,))
    rows = cur.fetchall()
    conn.close()
    out = []
    for row in rows:
        tid, guild_id, trig_id, panel_id, settings_json, map_json = row
        try:
            settings = json.loads(settings_json or "{}")
        except Exception:
            settings = {}
        try:
            current_map = json.loads(map_json or "{}")
        except Exception:
            current_map = {}
        out.append({"id": tid, "guild_id": guild_id, "trigger_channel_id": trig_id, "panel_message_id": panel_id, "settings": settings, "current_map": current_map})
    return out

def update_tempvoice_settings(trigger_channel_id: int, settings: dict) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE tempvoice SET settings = ? WHERE trigger_channel_id = ?", (json.dumps(settings, ensure_ascii=False), trigger_channel_id))
    conn.commit()
    conn.close()

def update_tempvoice_map(trigger_channel_id: int, current_map: dict) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE tempvoice SET current_map = ? WHERE trigger_channel_id = ?", (json.dumps(current_map, ensure_ascii=False), trigger_channel_id))
    conn.commit()
    conn.close()

def set_panel_message_id(trigger_channel_id: int, message_id: Optional[int]) -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE tempvoice SET panel_message_id = ? WHERE trigger_channel_id = ?", (message_id, trigger_channel_id))
    conn.commit()
    conn.close()

def add_temp_mapping(trigger_channel_id: int, user_id: int, voice_channel_id: int, text_channel_id: Optional[int] = None) -> None:
    rec = get_tempvoice_by_trigger(trigger_channel_id)
    if not rec:
        return
    m = rec.get("current_map") or {}
    # keep per-user settings here as optional field 'settings'
    m[str(user_id)] = {"voice": int(voice_channel_id), "text": int(text_channel_id) if text_channel_id else None, "settings": {}}
    update_tempvoice_map(trigger_channel_id, m)

def remove_temp_mapping_by_voice(trigger_channel_id: int, voice_channel_id: int) -> None:
    rec = get_tempvoice_by_trigger(trigger_channel_id)
    if not rec:
        return
    m = rec.get("current_map") or {}
    keys = [k for k, v in m.items() if v.get("voice") == int(voice_channel_id)]
    for k in keys:
        del m[k]
    update_tempvoice_map(trigger_channel_id, m)

def remove_temp_mapping_by_user(trigger_channel_id: int, user_id: int) -> None:
    rec = get_tempvoice_by_trigger(trigger_channel_id)
    if not rec:
        return
    m = rec.get("current_map") or {}
    if str(user_id) in m:
        del m[str(user_id)]
    update_tempvoice_map(trigger_channel_id, m)

def update_user_settings(trigger_channel_id: int, user_id: int, user_settings: dict) -> None:
    rec = get_tempvoice_by_trigger(trigger_channel_id)
    if not rec:
        return
    m = rec.get("current_map") or {}
    entry = m.get(str(user_id)) or {}
    entry_settings = entry.get("settings") or {}
    entry_settings.update(user_settings)
    entry["settings"] = entry_settings
    m[str(user_id)] = entry
    update_tempvoice_map(trigger_channel_id, m)

def get_user_settings(trigger_channel_id: int, user_id: int) -> dict:
    """Return merged settings: global settings overridden by per-user settings."""
    rec = get_tempvoice_by_trigger(trigger_channel_id)
    if not rec:
        return {}
    global_settings = rec.get("settings") or {}
    m = rec.get("current_map") or {}
    entry = m.get(str(user_id)) or {}
    user_settings = entry.get("settings") or {}
    # merge
    merged = dict(global_settings)
    merged.update(user_settings)
    return merged


def _serialize_overwrites(overwrites: dict) -> dict:
    """Serialize channel.overwrites mapping to simple dict."""
    out = {}
    perms_keys = ("connect", "view_channel", "send_messages", "manage_channels", "mute_members", "deafen_members", "move_members", "priority_speaker")
    for target, ow in (overwrites or {}).items():
        try:
            if isinstance(target, discord.Role):
                key = f"role:{target.id}"
            elif isinstance(target, discord.Member):
                key = f"member:{target.id}"
            else:
                continue
        except Exception:
            continue
        vals = {}
        for p in perms_keys:
            try:
                v = getattr(ow, p, None)
            except Exception:
                v = None
            if v is None:
                vals[p] = None
            else:
                vals[p] = bool(v)
        out[key] = vals
    return out


def _deserialize_overwrites(serialized: dict, guild: discord.Guild) -> dict:
    """Deserialize mapping into {target: PermissionOverwrite} where target is Role or Member if found."""
    out = {}
    perms_keys = ("connect", "view_channel", "send_messages", "manage_channels", "mute_members", "deafen_members", "move_members", "priority_speaker")
    for key, perms in (serialized or {}).items():
        try:
            typ, id_str = key.split(":", 1)
            idn = int(id_str)
        except Exception:
            continue
        target = None
        if typ == "role":
            target = guild.get_role(idn)
        elif typ == "member":
            target = guild.get_member(idn)
            # if not in cache, skip (can't fetch here safely)
        if not target:
            continue
        ow = discord.PermissionOverwrite()
        for p in perms_keys:
            v = perms.get(p)
            try:
                setattr(ow, p, None if v is None else bool(v))
            except Exception:
                pass
        out[target] = ow
    return out

def get_temp_channel_for_user(trigger_channel_id: int, user_id: int) -> Optional[int]:
    rec = get_tempvoice_by_trigger(trigger_channel_id)
    if not rec:
        return None
    m = rec.get("current_map") or {}
    v = m.get(str(user_id))
    if not v:
        return None
    return v.get("voice")

def get_all_temp_channels_for_trigger(trigger_channel_id: int) -> list[int]:
    rec = get_tempvoice_by_trigger(trigger_channel_id)
    if not rec:
        return []
    m = rec.get("current_map") or {}
    return [v.get("voice") for v in m.values() if v.get("voice")]


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

# ------------------ restart process setup ------------------
async def restart_process(interaction_or_ctx=None):
    """
    Сохраняет канал (если interaction_or_ctx передан), отвечает пользователю и перезапускает процесс.
    Если передан interaction (slash) — отправляет response, если ctx (prefix) — использует ctx.send.
    """
    channel_id = None
    try:
        if hasattr(interaction_or_ctx, "channel") and hasattr(interaction_or_ctx, "response"):
            channel_id = getattr(interaction_or_ctx, "restart_target", None) or interaction_or_ctx.channel.id
            try:
                await interaction_or_ctx.response.send_message("♻️ Перезапускаюсь...", ephemeral=True)
            except Exception as e:
                logging.debug(f"Не удалось отправить interaction.response: {e}")
        elif hasattr(interaction_or_ctx, "send") and hasattr(interaction_or_ctx, "author"):
            channel_id = getattr(interaction_or_ctx, "restart_target", None) or interaction_or_ctx.channel.id
            try:
                await interaction_or_ctx.send("♻️ Перезапускаюсь...")
            except Exception as e:
                logging.debug(f"Не удалось отправить ctx.send: {e}")
    except Exception as e:
        logging.exception(f"Ошибка при подготовке ответа перед рестартом: {e}")

    try:
        save_restart_channel(int(channel_id) if channel_id is not None else None)
    except Exception as e:
        logging.exception(f"Ошибка при сохранении channel_id в БД: {e}")

    await asyncio.sleep(0.5)

    try:
        # Закрываем бота
        await bot.close()
    except Exception as e:
        logging.debug(f"Ошибка при закрытии бота: {e}")

    # Небольшая пауза перед завершением
    await asyncio.sleep(0.5)

    # Завершаем процесс бота (start.py автоматически перезапустит его с обновлением файлов)
    logging.info("Завершение процесса для перезапуска...")
    os._exit(0)

async def quickrestart_process(interaction_or_ctx=None):
    """
    Быстрый перезапуск без обновления файлов.
    Сохраняет канал (если interaction_or_ctx передан), отвечает пользователю и перезапускает процесс.
    Если передан interaction (slash) — отправляет response, если ctx (prefix) — использует ctx.send.
    """
    # определяем канал для уведомления:
    channel_id = None
    try:
        # interaction (app command)
        if hasattr(interaction_or_ctx, "channel") and hasattr(interaction_or_ctx, "response"):
            channel_id = getattr(interaction_or_ctx, "restart_target", None) or interaction_or_ctx.channel.id
            await interaction_or_ctx.response.send_message("⚡ Быстрый перезапуск...", ephemeral=True)
        # ctx (prefix)
        elif hasattr(interaction_or_ctx, "send") and hasattr(interaction_or_ctx, "author"):
            channel_id = getattr(interaction_or_ctx, "restart_target", None) or interaction_or_ctx.channel.id
            await interaction_or_ctx.send("⚡ Быстрый перезапуск...")
    except Exception:
        pass

    # сохраняем в БД канал (может быть None)
    save_restart_channel(int(channel_id) if channel_id is not None else None)

    # создаём флаг быстрого перезапуска
    quick_restart_flag = os.path.join(os.path.dirname(__file__), ".quick_restart")
    try:
        with open(quick_restart_flag, "w") as f:
            f.write("")
    except Exception as e:
        logging.debug(f"Не удалось создать флаг быстрого перезапуска: {e}")

    # небольшая пауза чтобы response/сообщение успели отправиться в сеть
    await asyncio.sleep(0.5)

    try:
        # Закрываем бота
        await bot.close()
    except Exception as e:
        logging.debug(f"Ошибка при закрытии бота: {e}")

    # Небольшая пауза перед завершением
    await asyncio.sleep(0.5)

    # Завершаем процесс бота (start.py перезапустит его БЕЗ обновления файлов)
    logging.info("Завершение процесса для быстрого перезапуска...")
    os._exit(0)


# ------------------ bot commands ------------------
def mainbotstart():

    # ----------------------------
    # ПРЕФИКС-КОМАНДА (пример)
    # ----------------------------
    @bot.command(name="дай_пять")
    async def give_five(ctx: commands.Context):
        await ctx.send("https://cdn.discordapp.com/attachments/1350866065818783788/1434491390192255096/c0aced7c-94ef-4d24-aafa-480c618a74dd.gif?ex=69106eb6&is=690f1d36&hm=ba4189460e7fd7061f8f2928c6a75205ed4d8aaeeb5c04a3fb263745f2236cda&")

    @bot.command(name="ping")
    async def ping_cmd(ctx: commands.Context):
        uptime = int(time.time() - starttime)
        await ctx.send(f"Host:{HOSTNAME}({USERNAME})\nUptime: {format_duration(uptime)}\nPing: {round(bot.latency * 1000)} ms")

    @bot.command(name="disablecmds")
    async def disablecmds(ctx: commands.Context):
        # проверка прав: нужна роль OWNER
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.OWNER):
            await ctx.send("У вас нет прав для этой команды.")
            return

        # запускаем ассинхронный helper и ждём результат
        result = await clear_local_slash()
        if result is True:
            await ctx.send("✅ Удалены локальные слэш-команды")
        else:
            await ctx.send("❌ Ошибка при удалении локальных команд. Смотри лог.")

    @bot.command(name="synccmds")
    async def synccmds(ctx: commands.Context):
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.OWNER):
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
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.HOST):
            await ctx.send("У вас нет прав для этой команды.")
            return
        await ctx.send("Loading...")

        await clear_local_slash()

        await ctx.send("Success!")

        try:
            await ctx.guild.voice_client.disconnect()
        except: pass

        # Создаём флаг shutdown для корректного завершения
        shutdown_flag = os.path.join(os.path.dirname(__file__), ".shutdown")
        try:
            with open(shutdown_flag, "w") as f:
                f.write("")
        except Exception:
            pass

        await bot.close()

        os._exit(0)

    @bot.command(name="restartbot")
    async def restart_prefix(ctx: commands.Context, channel_id: Optional[int] = None):
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.HOST):
            await ctx.send("У вас нет прав для этой команды.")
            return

        if channel_id:
            ctx.restart_target = channel_id
        else:
            ctx.restart_target = ctx.channel.id

        await restart_process(ctx)

    @bot.command(name="quickrestartbot")
    async def restart_prefix(ctx: commands.Context, channel_id: Optional[int] = None):
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.HOST):
            await ctx.send("У вас нет прав для этой команды.")
            return

        if channel_id:
            ctx.restart_target = channel_id
        else:
            ctx.restart_target = ctx.channel.id

        await quickrestart_process(ctx)

    # ----------------------------
    # SLASH: /myperms
    # ----------------------------
    @bot.tree.command(name="myperms", description="Показать права бота на сервере")
    async def myperms(interaction: discord.Interaction):
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
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

        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
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

        roles = perms_manager.get_user_roles(user_id)
        if not roles:
            await interaction.response.send_message(f"У {target.mention} нет назначенных прав.", ephemeral=True)
            return

        lines = [f"• {r.value} — {perms_manager.get_role_description(r)}" for r in sorted(roles, key=lambda x: x.value)]
        await interaction.response.send_message(f"Права {target.mention}:\n```\n" + "\n".join(lines) + "\n```", ephemeral=True)

    # ----------------------------
    # Функция автодополнения для ролей в /editperms
    # ----------------------------
    async def role_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[discord.app_commands.Choice[str]]:
        """Автодополнение для списка доступных независимых ролей."""
        roles = [r.value for r in perms_manager.INDEPENDENT_ROLES]
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
        if not perms_manager.has_perm(manager_id, perms_manager.PermRole.PERMSMANAGER):
            await interaction.response.send_message("У вас нет прав на изменение прав пользователей.", ephemeral=True)
            return
        # Представляем пользователю Select с доступными ролями
        class RoleSelect(discord.ui.Select):
            def __init__(self, manager_id: int, target_id: int, set_flag: bool):
                options = []
                for r in perms_manager.PermRole:
                    # не показываем защищённые роли в списке
                    if r in (perms_manager.PermRole.OWNER, perms_manager.PermRole.HOST, perms_manager.PermRole.PERMSMANAGER):
                        continue
                    options.append(discord.SelectOption(label=r.value.upper(), value=r.value, description=perms_manager.get_role_description(r)))

                super().__init__(placeholder="Выберите роль...", min_values=1, max_values=1, options=options)
                self.manager_id = manager_id
                self.target_id = target_id
                self.set_flag = set_flag

            async def callback(self, interaction: discord.Interaction):
                role_value = self.values[0]
                try:
                    role_enum = perms_manager.PermRole(role_value)
                except ValueError:
                    await interaction.response.send_message(f"Неизвестная роль `{role_value}`.", ephemeral=True)
                    return

                ok, msg = perms_manager.can_manage_role(self.manager_id, self.target_id, role_enum)
                if not ok:
                    await interaction.response.send_message(msg, ephemeral=True)
                    return

                if self.set_flag:
                    added = perms_manager.add_perm(self.target_id, role_enum)
                    if added:
                        await interaction.response.send_message(f"✅ Роль `{role_enum.value}` добавлена пользователю <@{self.target_id}>.", ephemeral=True)
                    else:
                        await interaction.response.send_message(f"⚠️ У пользователя уже есть роль `{role_enum.value}`.", ephemeral=True)
                else:
                    removed = perms_manager.remove_perm(self.target_id, role_enum)
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
        
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
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
        
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
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
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
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
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
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
            await interaction.followup.send("Эта команда работает только на сервере.", ephemeral=False)
            return
        
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.followup.send("У вас недостаточно прав использовать эту команду!.", ephemeral=True)
            logging.debug(f"{interaction.user.name} try use askgpt")
            return
        
        await interaction.followup.send("Я в россии, увы без гемини", ephemeral=False)
    
    # ----------------------------
    # SLASH: /stopsound
    # ----------------------------
    @bot.tree.command(name="stopsound", description="Остановить воспроизведение звука")
    async def stopsound(interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=False)
            return
        
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.SOUNDPAD):
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
        
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.LEAVE):
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
        
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
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
        
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.JOIN):
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
        
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.SOUNDPAD):
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
    # SLASH: /set_slowmode time
    # ----------------------------
    @bot.tree.command(name="set_slowmode", description="Установить slowmode в текущем канале (секунды)")
    async def set_slowmode(interaction: discord.Interaction, seconds: int):
        # проверка — команда только на сервере
        if interaction.guild is None:
            await interaction.response.send_message("Команда только на сервере.", ephemeral=True)
            return

        # проверяем право пользователя управлять каналами (в этом канале)
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Команду можно использовать только в текстовом канале.", ephemeral=True)
            return

        if not channel.permissions_for(interaction.user).manage_channels:
            await interaction.response.send_message("У вас нет права `Manage Channels` в этом канале.", ephemeral=True)
            return

        # проверяем лимиты
        if seconds < 0 or seconds > 21600:
            await interaction.response.send_message("Значение должно быть от 0 до 21600 секунд.", ephemeral=True)
            return

        try:
            await channel.edit(slowmode_delay=seconds, reason=f"Установлено {interaction.user} через бота")
        except Exception as e:
            await interaction.response.send_message(f"Не удалось изменить slowmode: {e}", ephemeral=True)
            logger.error(e)
            return

        await interaction.response.send_message(f"Slowmode установлен: {seconds} секунд.", ephemeral=False)

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
    # SLASH: Role Reaction (реакции с выдачей ролей)
    # ----------------------------
    @bot.tree.command(name="role_reaction", description="Создать сообщение с реакцией для выдачи роли")
    @discord.app_commands.describe(
        emoji="Эмодзи для реакции",
        role="Роль для выдачи при реакции"
    )
    async def role_reaction(interaction: discord.Interaction, emoji: str, role: discord.Role):
        """Создаёт сообщение в канале с реакцией, которая выдаёт роль."""
        
        # Проверяем права
        if not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ У вас нет прав на управление ролями.", ephemeral=True)
            return
        
        bot_member = interaction.guild.get_member(bot.user.id)
        if not bot_member or not bot_member.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ У бота нет прав на управление ролями.", ephemeral=True)
            return
        
        if role.position >= bot_member.top_role.position:
            await interaction.response.send_message("❌ Не могу управлять этой ролью. Роль выше или равна роли бота.", ephemeral=True)
            return
        
        # Отправляем сообщение в канал
        channel = interaction.channel
        message = await channel.send(f"Нажмите {emoji} чтобы получить роль {role.mention}")
        
        # Добавляем реакцию
        try:
            await message.add_reaction(emoji)
        except Exception as e:
            await interaction.response.send_message(f"❌ Не удалось добавить реакцию: {e}", ephemeral=True)
            await message.delete()
            return
        
        # Сохраняем в БД
        try:
            save_role_reaction(message.id, channel.id, emoji, role.id)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ошибка при сохранении в БД: {e}", ephemeral=True)
            await message.delete()
            return
        
        await interaction.response.send_message(
            f"✅ Сообщение создано! Реакция: {emoji}, Роль: {role.mention}",
            ephemeral=True
        )

    # ----------------------------
    # SLASH: set_new_member_channel
    # ----------------------------
    @bot.tree.command(name="set_new_member_channel", description="Установить канал с сообщениями о входе и выходе с сервера [owner]")
    async def leave(interaction: discord.Interaction, channel: discord.TextChannel | None = None):

        if interaction.guild is None:
            await interaction.response.send_message("Эта команда работает только на сервере.", ephemeral=False)
            return
        
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав использовать эту команду!.", ephemeral=False)
            logging.debug(f"{interaction.user.name} try use set_new_member_channel")
            return
        targetchanel = channel or interaction.channel
        try:
            save_join_leave_channel(targetchanel.id)
            await interaction.response.send_message("Успешно!", ephemeral=True)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("Ошибка установки канала! (см логи)", ephemeral=False)

    # ----------------------------
    # SLASH: /set_tempvoice (owner only) — установить триггер-канал
    # ----------------------------
    @bot.tree.command(name="set_tempvoice", description="Установить voice-канал как триггер для TempVoice (owner only)")
    async def set_tempvoice(interaction: discord.Interaction, channel: discord.VoiceChannel):
        if interaction.guild is None:
            await interaction.response.send_message("Команда только на сервере.", ephemeral=True)
            return

        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав для этой команды.", ephemeral=True)
            return

        try:
            if channel is None:
                save_tempvoice_trigger(int(interaction.guild.id), 0)
                await interaction.response.send_message(f"Триггер TempVoice установлен глобально (любое вхождение).", ephemeral=True)
            else:
                save_tempvoice_trigger(int(interaction.guild.id), int(channel.id))
                await interaction.response.send_message(f"Триггер TempVoice установлен: {channel.mention}", ephemeral=True)
        except Exception as e:
            logging.exception(f"Ошибка при установке tempvoice триггера: {e}")
            await interaction.response.send_message("Ошибка при сохранении триггера (см лог).", ephemeral=True)

    @bot.tree.command(name="unset_tempvoicechannel", description="Удалить TempVoice триггер (owner only)")
    async def unset_tempvoicechannel(interaction: discord.Interaction, channel: discord.VoiceChannel | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("Команда только на сервере.", ephemeral=True)
            return

        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав для этой команды.", ephemeral=True)
            return

        try:
            trig_id = int(channel.id) if channel is not None else 0
            # remove DB record
            remove_tempvoice_trigger(trig_id)
            await interaction.response.send_message(f"Триггер TempVoice удалён (id={trig_id}).", ephemeral=True)
        except Exception as e:
            logging.exception(f"Ошибка при удалении tempvoice триггера: {e}")
            await interaction.response.send_message("Ошибка при удалении триггера (см лог).", ephemeral=True)

    # ----------------------------
    # SLASH: /send_tempvoicepanel (owner only) — отправить панель управления
    # ----------------------------
    class TempVoicePanelView(discord.ui.View):
        def __init__(self, trigger_channel_id: int):
            super().__init__(timeout=None)
            self.trigger_channel_id = trigger_channel_id

        @discord.ui.button(label="⚙️ Настройки", style=discord.ButtonStyle.secondary, custom_id="tv_settings")
        async def settings_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            # отправим приватное (ephemeral) сообщение с опциями
            await interaction.response.send_message("Выберите действие настройки (будут применяться к вашему временно созданному каналу):", view=SettingsOptionsView(self.trigger_channel_id), ephemeral=True)

        @discord.ui.button(label="🔐 Права входа", style=discord.ButtonStyle.secondary, custom_id="tv_perms")
        async def perms_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.send_message("Управление правами входа для TempVoice (ваш канал):", view=PermsOptionsView(self.trigger_channel_id), ephemeral=True)

    class SettingsOptionsView(discord.ui.View):
        def __init__(self, trigger_channel_id: int):
            super().__init__(timeout=120)
            self.trigger_channel_id = trigger_channel_id

        @discord.ui.button(label="✏️ Изменить название", style=discord.ButtonStyle.primary)
        async def rename(self, interaction: discord.Interaction, button: discord.ui.Button):
            # Modal для ввода нового имени
            class RenameModal(discord.ui.Modal, title="✏️ Изменить название канала"):
                new_name = discord.ui.TextInput(label="Новое имя (max 50)", max_length=50, placeholder="Например: TempVoice Алекс")

                async def on_submit(self_inner, modal_inter: discord.Interaction):
                    new_name_val = self_inner.new_name.value.strip()
                    # пытаемся найти temp канал пользователя
                    rec = get_tempvoice_by_trigger(self.trigger_channel_id)
                    if not rec:
                        await modal_inter.response.send_message("Триггер не найден.", ephemeral=True)
                        return
                    voice_id = get_temp_channel_for_user(self.trigger_channel_id, modal_inter.user.id)
                    if not voice_id:
                        await modal_inter.response.send_message("У вас нет созданного временного канала.", ephemeral=True)
                        return
                    guild = modal_inter.guild
                    try:
                        ch = guild.get_channel(int(voice_id))
                        if ch:
                            await ch.edit(name=new_name_val[:50])
                            await modal_inter.response.send_message(f"Название канала изменено на: {new_name_val}", ephemeral=True)
                        else:
                            await modal_inter.response.send_message("Канал не найден.", ephemeral=True)
                    except Exception as e:
                        logging.warning(f"Ошибка при переименовании: {e}")
                        await modal_inter.response.send_message("Ошибка при переименовании (см лог).", ephemeral=True)

            await interaction.response.send_modal(RenameModal())

        @discord.ui.button(label="👥 Изменить лимит", style=discord.ButtonStyle.primary)
        async def set_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
            class LimitModal(discord.ui.Modal, title="Установить лимит пользователей"):
                limit = discord.ui.TextInput(label="Лимит (0 — без лимита)", placeholder="0", max_length=4)

                async def on_submit(self_inner, modal_inter: discord.Interaction):
                    try:
                        val = int(self_inner.limit.value.strip())
                    except Exception:
                        await modal_inter.response.send_message("Неправильное число.", ephemeral=True)
                        return
                    voice_id = get_temp_channel_for_user(self.trigger_channel_id, modal_inter.user.id)
                    if not voice_id:
                        await modal_inter.response.send_message("У вас нет созданного временного канала.", ephemeral=True)
                        return
                    ch = modal_inter.guild.get_channel(int(voice_id))
                    if not ch:
                        await modal_inter.response.send_message("Канал не найден.", ephemeral=True)
                        return
                    try:
                        await ch.edit(user_limit=val)
                        await modal_inter.response.send_message(f"Лимит установлен: {val}", ephemeral=True)
                    except Exception as e:
                        logging.warning(e)
                        await modal_inter.response.send_message("Ошибка при установке лимита.", ephemeral=True)

            await interaction.response.send_modal(LimitModal())

        @discord.ui.button(label="🎚️ Изменить битрейт", style=discord.ButtonStyle.primary)
        async def set_bitrate(self, interaction: discord.Interaction, button: discord.ui.Button):
            class BitrateModal(discord.ui.Modal, title="Установить битрейт (kbps)"):
                br = discord.ui.TextInput(label="Битрейт в kbps (например 64)", placeholder="64", max_length=6)

                async def on_submit(self_inner, modal_inter: discord.Interaction):
                    try:
                        kb = int(self_inner.br.value.strip())
                    except Exception:
                        await modal_inter.response.send_message("Неправильное число.", ephemeral=True)
                        return
                    voice_id = get_temp_channel_for_user(self.trigger_channel_id, modal_inter.user.id)
                    if not voice_id:
                        await modal_inter.response.send_message("У вас нет созданного временного канала.", ephemeral=True)
                        return
                    ch = modal_inter.guild.get_channel(int(voice_id))
                    if not ch:
                        await modal_inter.response.send_message("Канал не найден.", ephemeral=True)
                        return
                    try:
                        await ch.edit(bitrate=kb * 1000)
                        await modal_inter.response.send_message(f"Битрейт установлен: {kb} kbps", ephemeral=True)
                    except Exception as e:
                        logging.warning(e)
                        await modal_inter.response.send_message("Ошибка при установке битрейта.", ephemeral=True)

            await interaction.response.send_modal(BitrateModal())

        @discord.ui.button(label="💬 Вкл/Выкл чат", style=discord.ButtonStyle.secondary)
        async def toggle_chat(self, interaction: discord.Interaction, button: discord.ui.Button):
            # переключим chat_enabled в настройках триггера и создадим/удалим текстовый канал
            rec = get_tempvoice_by_trigger(self.trigger_channel_id)
            if not rec:
                await interaction.response.send_message("Триггер не найден.", ephemeral=True)
                return
            settings = rec.get("settings") or {}
            settings["chat_enabled"] = not bool(settings.get("chat_enabled"))
            update_tempvoice_settings(self.trigger_channel_id, settings)
            # Сообщаем пользователю и даём инструкцию по встроенному чату (эпхемерно, без ЛС)
            await interaction.response.send_message(
                f"💬 Встроенный чат: {settings['chat_enabled']}.\n"
                "Чтобы изменить права встроенного чата: откройте настройки канала в Discord → Permissions.",
                ephemeral=True,
            )

        @discord.ui.button(label="🔒 Заблокировать/Разблокировать", style=discord.ButtonStyle.danger)
        async def lock_unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
            rec = get_tempvoice_by_trigger(self.trigger_channel_id)
            if not rec:
                await interaction.response.send_message("Триггер не найден.", ephemeral=True)
                return
            settings = rec.get("settings") or {}
            locked_now = not bool(settings.get('locked'))
            settings['locked'] = locked_now

            # применим к текущему каналу пользователя
            voice_id = get_temp_channel_for_user(self.trigger_channel_id, interaction.user.id)
            if voice_id:
                ch = interaction.guild.get_channel(int(voice_id))
                if ch:
                    try:
                        # получаем map saved_overwrites
                        saved = settings.get('saved_overwrites') or {}
                        if locked_now:
                            # сохраняем текущие overwrites
                            try:
                                so = _serialize_overwrites(ch.overwrites)
                                saved[str(ch.id)] = so
                                settings['saved_overwrites'] = saved
                            except Exception:
                                pass
                            # строим новые overwrites: блокируем @everyone и разрешаем trusted
                            new_overwrites = {}
                            # Запретим подключение для @everyone (voice-specific)
                            new_overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(connect=False, view_channel=False)
                            # Разрешим доступ для доверенных пользователей (voice perms)
                            for uid in (settings.get('trusted_users') or []):
                                try:
                                    m = interaction.guild.get_member(int(uid))
                                    if m:
                                        new_overwrites[m] = discord.PermissionOverwrite(connect=True, speak=True, manage_channels=True)
                                except Exception:
                                    continue
                            try:
                                await ch.edit(overwrites=new_overwrites)
                            except Exception as e:
                                logging.warning(f"Ошибка при установке locked overwrites: {e}")
                        else:
                            # разблокировать: восстановим сохранённые overwrites если есть
                            try:
                                saved = settings.get('saved_overwrites') or {}
                                ser = saved.get(str(ch.id))
                                if ser:
                                    des = _deserialize_overwrites(ser, interaction.guild)
                                    await ch.edit(overwrites=des)
                                    # удалить запись
                                    try:
                                        del saved[str(ch.id)]
                                    except KeyError:
                                        pass
                                    settings['saved_overwrites'] = saved
                                else:
                                    # нет сохранённых — просто разрешаем подключение
                                    await ch.set_permissions(interaction.guild.default_role, connect=True)
                            except Exception as e:
                                logging.warning(f"Ошибка при восстановлении overwrites: {e}")
                        update_tempvoice_settings(self.trigger_channel_id, settings)
                        await interaction.response.send_message(f"locked = {settings['locked']}", ephemeral=True)
                        return
                    except Exception as e:
                        logging.warning(e)
            else:
                # нет временного канала у пользователя — просто переключаем флаг
                update_tempvoice_settings(self.trigger_channel_id, settings)
                await interaction.response.send_message(f"locked установлено: {settings['locked']}", ephemeral=True)

        @discord.ui.button(label="🚪 Отключить участника", style=discord.ButtonStyle.danger)
        async def disconnect_member(self, interaction: discord.Interaction, button: discord.ui.Button):
            # Предоставляем список участников только из вашего временного канала
            voice_id = get_temp_channel_for_user(self.trigger_channel_id, interaction.user.id)
            if not voice_id:
                await interaction.response.send_message("У вас нет временного канала.", ephemeral=True)
                return
            ch = interaction.guild.get_channel(int(voice_id))
            if not ch:
                await interaction.response.send_message("Канал не найден.", ephemeral=True)
                remove_temp_mapping_by_user(self.trigger_channel_id, interaction.user.id)
                return

            members = [m for m in ch.members if not m.bot and m.id != interaction.user.id]
            if not members:
                await interaction.response.send_message("В вашем канале нет других участников для отключения.", ephemeral=True)
                return

            # Ограничение опций селекта до 25 (максимум Discord)
            options = [discord.SelectOption(label=m.display_name[:100], value=str(m.id), description=f"{m.id}") for m in members[:25]]

            class MemberSelect(discord.ui.Select):
                def __init__(self, opts, channel_id):
                    super().__init__(placeholder="Выберите участника(ов) для отключения...", min_values=1, max_values=min(len(opts), 25), options=opts)
                    self.channel_id = channel_id

                async def callback(self, select_inter: discord.Interaction):
                    guild = select_inter.guild
                    results = {"kicked": [], "failed": []}
                    for val in self.values:
                        try:
                            uid = int(val)
                            member_obj = guild.get_member(uid) or await guild.fetch_member(uid)
                            if member_obj and member_obj.voice and member_obj.voice.channel and member_obj.voice.channel.id == int(self.channel_id):
                                try:
                                    await member_obj.move_to(None)
                                    results["kicked"].append(member_obj.mention)
                                except Exception:
                                    results["failed"].append(member_obj.mention if member_obj else str(uid))
                            else:
                                results["failed"].append(str(uid))
                        except Exception:
                            results["failed"].append(val)

                    parts = []
                    if results['kicked']:
                        parts.append(f"Отключены: {', '.join(results['kicked'])}")
                    if results['failed']:
                        parts.append(f"Не удалось: {', '.join(results['failed'])}")
                    await select_inter.response.edit_message(content="\n".join(parts) or "Готово.", view=None)

            view = discord.ui.View(timeout=60)
            view.add_item(MemberSelect(options, voice_id))
            await interaction.response.send_message("Выберите участников для отключения:", view=view, ephemeral=True)

        @discord.ui.button(label="🗑️ Удалить мой канал", style=discord.ButtonStyle.danger)
        async def delete_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
            voice_id = get_temp_channel_for_user(self.trigger_channel_id, interaction.user.id)
            if not voice_id:
                await interaction.response.send_message("У вас нет созданного временного канала.", ephemeral=True)
                return
            ch = interaction.guild.get_channel(int(voice_id))
            if not ch:
                remove_temp_mapping_by_user(self.trigger_channel_id, interaction.user.id)
                await interaction.response.send_message("Канал не найден, запись удалена.", ephemeral=True)
                return
            # Показываем подтверждение (ephemeral) с кнопками
            class ConfirmDeleteView(discord.ui.View):
                def __init__(self, voice_channel, trig_id, user_id):
                    super().__init__(timeout=60)
                    self.voice_channel = voice_channel
                    self.trig_id = trig_id
                    self.user_id = user_id

                @discord.ui.button(label="Да, удалить 🗑️", style=discord.ButtonStyle.danger)
                async def confirm(self, i: discord.Interaction, b: discord.ui.Button):
                    # Только владелец кнопки может подтвердить
                    if i.user.id != interaction.user.id:
                        await i.response.send_message("Это подтверждение не для вас.", ephemeral=True)
                        return
                    try:
                        if self.voice_channel:
                            await self.voice_channel.delete()
                        remove_temp_mapping_by_user(self.trig_id, self.user_id)
                        await i.response.edit_message(content="Ваш временный канал удалён.", view=None)
                    except Exception as e:
                        logging.warning(e)
                        await i.response.edit_message(content="Ошибка при удалении канала.", view=None)

                @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary)
                async def cancel(self, i: discord.Interaction, b: discord.ui.Button):
                    if i.user.id != interaction.user.id:
                        await i.response.send_message("Это действие не для вас.", ephemeral=True)
                        return
                    await i.response.edit_message(content="Удаление отменено.", view=None)

            view = ConfirmDeleteView(ch, self.trigger_channel_id, interaction.user.id)
            await interaction.response.send_message("Подтвердите удаление вашего временного канала:", view=view, ephemeral=True)

    class PermsOptionsView(discord.ui.View):
        def __init__(self, trigger_channel_id: int):
            super().__init__(timeout=120)
            self.trigger_channel_id = trigger_channel_id

        async def ask_list_and_update(self, interaction: discord.Interaction, field: str, add: bool = True):
            # Показываем ephemeral сообщение с UserSelect для выбора пользователей
            class UsersSelect(discord.ui.UserSelect):
                def __init__(self, trig_id, field_name, add_flag):
                    super().__init__(placeholder="Выберите пользователей...", min_values=1, max_values=25)
                    self.trig_id = trig_id
                    self.field_name = field_name
                    self.add_flag = add_flag

                async def callback(self, select_inter: discord.Interaction):
                    ids = [u.id for u in self.values]
                    rec = get_tempvoice_by_trigger(self.trig_id)
                    if not rec:
                        await select_inter.response.send_message("⚠️ Триггер не найден.", ephemeral=True)
                        return
                    settings = rec.get('settings') or {}
                    lst = settings.get(self.field_name) or []
                    if self.add_flag:
                        for i in ids:
                            if i not in lst:
                                lst.append(i)
                    else:
                        for i in ids:
                            if i in lst:
                                lst.remove(i)
                    settings[self.field_name] = lst
                    update_tempvoice_settings(self.trig_id, settings)
                    await select_inter.response.edit_message(content=f"✅ Обновлено поле {self.field_name} (count={len(lst)})", view=None)

            view = discord.ui.View(timeout=60)
            view.add_item(UsersSelect(self.trigger_channel_id, field, add))
            await interaction.response.send_message(f"Выберите пользователей для `{field}`:", view=view, ephemeral=True)

        @discord.ui.button(label="✅ Разрешить пользователей", style=discord.ButtonStyle.primary)
        async def add_allowed(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.ask_list_and_update(interaction, 'allowed_users', add=True)

        @discord.ui.button(label="❌ Убрать разрешения", style=discord.ButtonStyle.secondary)
        async def remove_allowed(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.ask_list_and_update(interaction, 'allowed_users', add=False)

        @discord.ui.button(label="⛔ Заблокировать пользователей", style=discord.ButtonStyle.danger)
        async def add_blocked(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.ask_list_and_update(interaction, 'blocked_users', add=True)

        @discord.ui.button(label="⭐ Добавить доверенных", style=discord.ButtonStyle.success)
        async def add_trusted(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.ask_list_and_update(interaction, 'trusted_users', add=True)

        @discord.ui.button(label="✅ Разрешить роли", style=discord.ButtonStyle.primary)
        async def add_allowed_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.ask_list_and_update_roles(interaction, 'allowed_roles', add=True)

        @discord.ui.button(label="❌ Убрать разрешённые роли", style=discord.ButtonStyle.secondary)
        async def remove_allowed_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.ask_list_and_update_roles(interaction, 'allowed_roles', add=False)

        @discord.ui.button(label="⛔ Заблокировать роли", style=discord.ButtonStyle.danger)
        async def add_blocked_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.ask_list_and_update_roles(interaction, 'blocked_roles', add=True)

        @discord.ui.button(label="❌ Убрать блокированные роли", style=discord.ButtonStyle.secondary)
        async def remove_blocked_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.ask_list_and_update_roles(interaction, 'blocked_roles', add=False)

        async def ask_list_and_update_roles(self, interaction: discord.Interaction, field: str, add: bool = True):
            # Показываем эпхемерный RoleSelect для выбора ролей
            class RolesSelect(discord.ui.RoleSelect):
                def __init__(self, trig_id, field_name, add_flag):
                    super().__init__(placeholder="Выберите роли...", min_values=1, max_values=25)
                    self.trig_id = trig_id
                    self.field_name = field_name
                    self.add_flag = add_flag

                async def callback(self, select_inter: discord.Interaction):
                    ids = [r.id for r in self.values]
                    rec = get_tempvoice_by_trigger(self.trig_id)
                    if not rec:
                        await select_inter.response.send_message("⚠️ Триггер не найден.", ephemeral=True)
                        return
                    settings = rec.get('settings') or {}
                    lst = settings.get(self.field_name) or []
                    if self.add_flag:
                        for i in ids:
                            if i not in lst:
                                lst.append(i)
                    else:
                        for i in ids:
                            if i in lst:
                                lst.remove(i)
                    settings[self.field_name] = lst
                    update_tempvoice_settings(self.trig_id, settings)
                    await select_inter.response.edit_message(content=f"✅ Обновлено поле {self.field_name} (count={len(lst)})", view=None)

            view = discord.ui.View(timeout=60)
            view.add_item(RolesSelect(self.trigger_channel_id, field, add))
            await interaction.response.send_message(f"Выберите роли для `{field}`:", view=view, ephemeral=True)

    @bot.tree.command(name="send_tempvoicepanel", description="Отправить панель TempVoice (owner only)")
    async def send_tempvoicepanel(interaction: discord.Interaction, trigger: discord.VoiceChannel | None, channel: discord.TextChannel | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав.", ephemeral=True)
            return
        # support passing trigger or using global trigger (0)
        rec = None
        if trigger is not None:
            rec = get_tempvoice_by_trigger(int(trigger.id))
        if not rec:
            # try global
            rec = get_tempvoice_by_trigger(0)
        if not rec:
            await interaction.response.send_message("⚠️ Триггер не настроен. Сначала используйте /set_tempvoice.", ephemeral=True)
            return
        target = channel or interaction.channel
        # удаляем старую панель, если есть
        old_msg_id = rec.get('panel_message_id')
        if old_msg_id:
            try:
                ch = target
                old = await ch.fetch_message(old_msg_id)
                try:
                    await old.delete()
                except Exception:
                    pass
            except Exception:
                pass
        # отправим новую (с эмодзи и более дружелюбным текстом)
        trig_key = int(trigger.id) if trigger is not None else (rec.get('trigger_channel_id') or 0)
        view = TempVoicePanelView(int(trig_key))
        sent = await target.send("🎛️ Панель TempVoice — нажмите кнопки для управления вашим временным каналом.", view=view)
        set_panel_message_id(int(trig_key), int(sent.id))
        await interaction.response.send_message("✅ Панель TempVoice отправлена.", ephemeral=True)

    # ----------------------------
    # SLASH: /chemical_reactions reactants
    # ----------------------------
    @bot.tree.command(name="chemical_reactions", description="Анализ и генерация возможных уравнений реакции по списку реагентов (owner only)")
    async def chemical_reactions(interaction: discord.Interaction, reactants: str):
        
        await interaction.response.defer(ephemeral=False)


        # Парсим строку реагентов
        try:
            parts = chem_reactions.parse_reactants_from_string(reactants)
        except Exception as e:
            await interaction.followup.send(f"Ошибка при разборе реагентов: {e}", ephemeral=True)
            return

        if not parts:
            await interaction.followup.send("Не удалось распознать реагенты. Укажите через `+` или `,` (например: `HCl , NaOH`).", ephemeral=True)
            return

        # Вызываем движок реакций с таймаутом через обёртку в chem_reactions
        try:
            # timeout в секундах — можно менять
            results = chem_reactions._run_with_timeout(chem_reactions.try_all_reaction_paths, args=(parts,), timeout=10.0)
        except TimeoutError:
            await interaction.followup.send("Ошибка: расчёт превысил допустимое время (таймаут). Упростите ввод или попробуйте снова позже.", ephemeral=True)
            return
        except Exception as e:
            logging.exception(f"Ошибка в chem_reactions: {e}")
            await interaction.followup.send(f"Внутренняя ошибка при анализе реакции: {e}", ephemeral=True)
            return

        proceeded = results.get('proceeded', []) or []
        blocked = results.get('possible_but_no_reaction', []) or []

        summary = [f"Reactants: {', '.join(parts)}", f"✅ Прошли вариантов: {len(proceeded)}", f"⚠️ Возможны, но не идут: {len(blocked)}"]
        await interaction.followup.send("\n".join(summary), ephemeral=False)

        # Функция для отправки подробного варианта (ограниченно по длине)
        async def send_variant(idx: int, rec: dict, tag: str):
            header = f"{tag} #{idx} — {rec.get('type') or ''}"
            body = rec.get('pretty') or ''
            payload = f"{header}\n\n{body}"
            # Discord ограничение: ~2000 символов. Обрезаем аккуратно.
            if len(payload) > 1900:
                payload = payload[:1900] + "\n... (truncated)"
            try:
                await interaction.followup.send(f"```{payload}```", ephemeral=False)
            except Exception:
                await interaction.followup.send(payload[:1900], ephemeral=False)

        # Отправляем до 5 подробных вариантов из каждой категории
        for i, rec in enumerate(proceeded[:5], start=1):
            await send_variant(i, rec, "Прошёл")

        for i, rec in enumerate(blocked[:5], start=1):
            await send_variant(i, rec, "Возможен, но не идёт")

        # Подсказка об ограничении
        if len(proceeded) > 5 or len(blocked) > 5:
            await interaction.followup.send("Показаны первые 5 вариантов в каждой категории. Уточните запрос для более узкого вывода.", ephemeral=True)

        return
    # ----------------------------
    # ОБРАБОТКА TEMPVOICE СООБЩЕНИЙ
    # ----------------------------   

    @bot.event
    async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Игнорировать ботов (включая самого бота)
        if member.bot:
            return

        # Пользователь зашёл в канал (или переместился)
        try:
            # если вошёл в канал
            if after.channel is not None and (before.channel is None or before.channel.id != after.channel.id):
                trig = get_tempvoice_by_trigger(after.channel.id)
                # try global trigger (0) if specific trigger not found
                if not trig:
                    trig = get_tempvoice_by_trigger(0)
                if trig:
                    guild = after.channel.guild
                    # если у пользователя уже есть temp-канал — переместить
                    existing = get_temp_channel_for_user(after.channel.id, member.id)
                    if existing:
                        ch = guild.get_channel(int(existing))
                        if ch:
                            try:
                                await member.move_to(ch)
                            except Exception:
                                pass
                        return

                    trig_key = trig.get('trigger_channel_id') or 0
                    settings = trig.get('settings') or {}
                    # merge per-user settings
                    user_merged = get_user_settings(trig_key, member.id) or {}
                    final_settings = dict(settings)
                    final_settings.update(user_merged)
                    prefix = final_settings.get('prefix', 'TempVoice ')
                    # формируем название (макс 50 символов)
                    base_name = f"{prefix}{member.display_name}"[:50]
                    category = after.channel.category

                    # собираем overwrites
                    # собираем overwrites с приоритетом: allowed -> blocked -> trusted
                    overwrites: dict = {}
                    # по умолчанию разрешаем подключаться всем (будут блокировки ниже при необходимости)
                    overwrites[guild.default_role] = discord.PermissionOverwrite(connect=True, view_channel=True)

                    # сначала allowed (могут быть позже переопределены blocked)
                    for rid in (settings.get('allowed_roles') or []):
                        try:
                            r = guild.get_role(int(rid))
                            if r:
                                overwrites[r] = discord.PermissionOverwrite(connect=True)
                        except Exception:
                            continue

                    for uid in (settings.get('allowed_users') or []):
                        try:
                            m = guild.get_member(int(uid))
                            if m:
                                overwrites[m] = discord.PermissionOverwrite(connect=True)
                        except Exception:
                            continue

                    # затем blocked (переопределяют allowed)
                    for rid in (settings.get('blocked_roles') or []):
                        try:
                            r = guild.get_role(int(rid))
                            if r:
                                overwrites[r] = discord.PermissionOverwrite(connect=False)
                        except Exception:
                            continue

                    for uid in (settings.get('blocked_users') or []):
                        try:
                            m = guild.get_member(int(uid))
                            if m:
                                overwrites[m] = discord.PermissionOverwrite(connect=False)
                        except Exception:
                            continue

                    # trusted — всегда имеют доступ, перебивают блокировки
                    for uid in (settings.get('trusted_users') or []):
                        try:
                            m = guild.get_member(int(uid))
                            if m:
                                overwrites[m] = discord.PermissionOverwrite(connect=True, manage_channels=True)
                        except Exception:
                            continue

                    # создаём канал
                    user_limit = int(final_settings.get('user_limit') or 0) or 0
                    br = final_settings.get('bitrate')
                    kwargs = {"overwrites": overwrites, "category": category, "user_limit": user_limit}
                    if br:
                        try:
                            kwargs['bitrate'] = int(br)
                        except Exception:
                            pass

                    try:
                        # use per-user settings overrides if exist
                        # kwargs currently contains overwrites/category/user_limit/bitrate
                        ch = await guild.create_voice_channel(name=base_name, **kwargs)
                    except TypeError:
                        # старые версии discord.py могут не принимать bitrate
                        kwargs.pop('bitrate', None)
                        ch = await guild.create_voice_channel(name=base_name, **kwargs)

                    # Не создаём отдельный текстовый канал — используем встроенный связанный чат голосового канала.
                    # Сохраняем mapping (текстовый канал не применяется)
                    trig_key = trig.get('trigger_channel_id') or 0
                    add_temp_mapping(int(trig_key), member.id, ch.id, None)

                    # пытаемся переместить пользователя
                    try:
                        await member.move_to(ch)
                    except Exception:
                        pass

            # выход из канала — если ушёл из временного канала, проверить на удаление
            if before.channel is not None and (after.channel is None or (after.channel is not None and before.channel.id != after.channel.id)):
                # проверяем все триггеры сервера
                for rec in get_tempvoice_by_guild(member.guild.id):
                    mapping = rec.get('current_map') or {}
                    # если before.channel.id — один из temp каналов
                    for k, v in list(mapping.items()):
                        if v.get('voice') == (before.channel.id if before.channel else None):
                            # если канал пуст — удалить и очистить запись
                            vc = member.guild.get_channel(int(v.get('voice')))
                            if vc:
                                if len(vc.members) == 0:
                                    try:
                                        await vc.delete()
                                    except Exception:
                                        pass
                                    # удалить маппинг
                                    remove_temp_mapping_by_voice(rec.get('trigger_channel_id'), int(v.get('voice')))
                            else:
                                # канал не найден — удаляем запись
                                remove_temp_mapping_by_voice(rec.get('trigger_channel_id'), int(v.get('voice')))
        except Exception as e:
            logging.exception(f"Ошибка в on_voice_state_update (tempvoice): {e}")


    # ----------------------------
    # ОБРАБОТКА ОСТАЛЬНЫХ СООБЩЕНИЙ
    # ----------------------------      
    async def on_sus_message(message):
        if message.author.bot:
            return
        
        msglow = message.content.lower()

        if "<@1409084528588488727>" in msglow:
            # reply автоматически упомянет автора (mention_author=True по умолчанию)
            await message.reply(r"https://tenor.com/view/fuck-you-gif-27037587", mention_author=True, delete_after=10)

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
                
    # ----------------------------
    # Обработчики для выхода участника
    # ----------------------------
    @bot.event
    async def on_member_remove(member):
        channel_id = get_join_leave_channel()
        if channel_id == None:
            return
        
        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return

        await channel.send(
            f"Пользователь {member.mention} ({member.name}) id: `{member.id}` покинул сервер."
        )

    # ----------------------------
    # Обработчики для входа участника
    # ----------------------------
    @bot.event
    async def on_member_join(member):
        channel_id = get_join_leave_channel()
        if channel_id == None:
            return
        
        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return

        await channel.send(
            f"Добро пожаловать, {member.mention}! ({member.name}, id: `{member.id}` )",
        )
    # ----------------------------
    # Обработчики для role_reactions
    # ----------------------------
    @bot.event
    async def on_raw_message_delete(payload: discord.RawMessageDeleteEvent):
        """Обработчик удаления сообщения - удаляет role_reaction из БД."""
        try:
            delete_role_reaction(payload.message_id)
        except Exception as e:
            logging.error(f"Ошибка при удалении role_reaction из БД: {e}")

    @bot.event
    async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
        """Обработчик добавления реакции."""
        if payload.user_id == bot.user.id:
            return  # Игнорируем реакции самого бота
        
        # Получаем информацию о роле из БД
        emoji_str = str(payload.emoji)
        role_data = get_role_reaction(payload.message_id, emoji_str)
        
        if not role_data:
            return  # Нет роли для этой реакции
        
        try:
            guild = bot.get_guild(payload.guild_id)
            if not guild:
                return
            
            member = guild.get_member(payload.user_id)
            if not member:
                member = await guild.fetch_member(payload.user_id)
            
            role_id = role_data[3]
            role = guild.get_role(role_id)
            
            if not role:
                return
            
            # Проверяем, есть ли уже роль у пользователя
            had_role = role in member.roles
            
            if not had_role:
                await member.add_roles(role, reason=f"Role reaction на {emoji_str}")
            
            # Отправляем личное сообщение пользователю
            try:
                if had_role:
                    await member.send(f"ℹ️ Вы уже имели роль **{role.name}**")
                else:
                    await member.send(f"✅ Вам была выдана роль **{role.name}**")
            except Exception as e:
                logging.warning(f"Не удалось отправить личное сообщение о выдаче роли: {e}")
        except Exception as e:
            logging.error(f"Ошибка при добавлении роли на реакцию: {e}")

    @bot.event
    async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
        """Обработчик удаления реакции."""
        if payload.user_id == bot.user.id:
            return  # Игнорируем реакции самого бота
        
        # Получаем информацию о роле из БД
        emoji_str = str(payload.emoji)
        role_data = get_role_reaction(payload.message_id, emoji_str)
        
        if not role_data:
            return  # Нет роли для этой реакции
        
        try:
            guild = bot.get_guild(payload.guild_id)
            if not guild:
                return
            
            member = guild.get_member(payload.user_id)
            if not member:
                member = await guild.fetch_member(payload.user_id)
            
            role_id = role_data[3]
            role = guild.get_role(role_id)
            
            if not role:
                return
            
            # Проверяем, есть ли роль у пользователя
            had_role = role in member.roles
            
            if had_role:
                await member.remove_roles(role, reason=f"Удалена реакция на {emoji_str}")
            
            # Отправляем личное сообщение пользователю
            try:
                if had_role:
                    await member.send(f"✅ Вам была забрана роль **{role.name}**")
                else:
                    await member.send(f"ℹ️ Вы не имели роль **{role.name}**")
            except Exception as e:
                logging.warning(f"Не удалось отправить личное сообщение об удалении роли: {e}")
        except Exception as e:
            logging.error(f"Ошибка при удалении роли на реакцию: {e}")

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
