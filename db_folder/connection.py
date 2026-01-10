
import os
import sqlite3
from typing import Any, Optional, Dict
import json
from pathlib import Path
import datetime
import aiosqlite

CONFIGS_FODLER = Path(__file__).with_name("configs_folder")
ADVANCED_SETTINGS_PATH = CONFIGS_FODLER / "advanced_settings.json"

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_state.db")

with open(ADVANCED_SETTINGS_PATH, "r", encoding="utf-8") as f:
    advanced_settings = json.load(f)

DAILY_REQUEST_LIMIT = advanced_settings["DAILY_REQUEST_LIMIT"]

def init_db():
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
    # Таблица для хранения количества дневных запросов пользователей
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_daily_requests (
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            count INTEGER NOT NULL,
            PRIMARY KEY(user_id, date)
        );
    """)
    # Таблица уровней пользователей
    cur.execute("""
        CREATE TABLE IF NOT EXISTS level_users (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0,
            voice_time INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        );
    """)
    # Таблица для настроек уведомлений о повышении уровня: хранит канал для каждой гильдии
    cur.execute("""
        CREATE TABLE IF NOT EXISTS level_alerts (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER
        );
    """)
    # Таблица наград за получение уровня
    cur.execute("""
        CREATE TABLE IF NOT EXISTS level_rewards (
            guild_id INTEGER NOT NULL,
            level INTEGER NOT NULL,
            role INTEGER NOT NULL,
            PRIMARY KEY (guild_id, level)
        );
    """)
    # Таблица панелей майнкрафта
    cur.execute("""
        CREATE TABLE IF NOT EXISTS minecraft_panels_v2 (
            guild_id INTEGER NOT NULL,
            server_ip TEXT NOT NULL,
            server_port INTEGER NOT NULL,
            query_port INTEGER,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, message_id)
        )
        """)
    conn.commit()
    conn.close()



class Database:
    def __init__(self, path: str):
        self.path = path
        self.db: aiosqlite.Connection | None = None

    async def connect(self):
        self.db = await aiosqlite.connect(self.path)
        await self.db.execute("PRAGMA foreign_keys = ON;")

    async def close(self):
        await self.db.close()



    


def get_user_daily_count(user_id: int, date: Optional[str] = None) -> int:
    """Возвращает количество запросов пользователя за указанную дату (по умолчанию сегодня)."""
    date = date or datetime.date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT count FROM user_daily_requests WHERE user_id = ? AND date = ?", (user_id, date))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else 0

def increment_user_daily_count(user_id: int) -> int:
    """Увеличивает счётчик запросов пользователя за сегодня и возвращает новое значение."""
    date = datetime.date.today().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT count FROM user_daily_requests WHERE user_id = ? AND date = ?", (user_id, date))
    row = cur.fetchone()
    if row:
        new = int(row[0]) + 1
        cur.execute("UPDATE user_daily_requests SET count = ? WHERE user_id = ? AND date = ?", (new, user_id, date))
    else:
        new = 1
        cur.execute("INSERT INTO user_daily_requests (user_id, date, count) VALUES (?, ?, ?)", (user_id, date, new))
    conn.commit()
    conn.close()
    return new

def get_remaining_requests(user_id: int) -> int:
    """Возвращает, сколько запросов осталось у пользователя сегодня."""
    used = get_user_daily_count(user_id)
    rem = DAILY_REQUEST_LIMIT - used
    return rem if rem >= 0 else 0

def set_level_reward(guild_id: int, level: int, role_id: int | None = None) -> None:
    """
    Устанавливает или удаляет награду за уровень.

    - role_id > 0  → назначить / переназначить награду
    - role_id == 0 или None → удалить награду за уровень
    """

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # удаление награды
    if not role_id:
        cur.execute(
            "DELETE FROM level_rewards WHERE guild_id = ? AND level = ?;",
            (guild_id, level)
        )
    else:
        # назначение / переназначение награды
        cur.execute(
            """
            INSERT INTO level_rewards (guild_id, level, role)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, level)
            DO UPDATE SET role = excluded.role;
            """,
            (guild_id, level, role_id)
        )

    conn.commit()
    conn.close()


def get_level_rewards(guild_id: int) -> list[tuple[int, int]]:
    """
    Возвращает список наград уровней:
    [(level, role_id), ...]
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT level, role FROM level_rewards WHERE guild_id = ?;",
        (guild_id,)
    )

    rows = cur.fetchall()
    conn.close()
    return rows