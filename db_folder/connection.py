
import os
import sqlite3
from typing import Any, Optional, Dict
import json
from pathlib import Path
import datetime
import aiosqlite

CONFIGS_FODLER = Path(__file__).with_name("configs_folder")
DB_PATH = os.path.join(os.path.dirname(__file__), "bot_state.db")


class Database:
    def __init__(self, path: str):
        self.path = path
        self.db: aiosqlite.Connection | None = None

    async def connect(self):
        self.db = await aiosqlite.connect(self.path)
        await self.db.execute("PRAGMA foreign_keys = ON;")

    async def close(self):
        await self.db.close()

        
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
        CREATE TABLE IF NOT EXISTS join_leave_v2 (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            mention_role_id INTEGER
        );
    """)


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
    # Таблица коунтинг канала
    cur.execute("""
        CREATE TABLE IF NOT EXISTS counting (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            next_expected INTEGER NOT NULL
        );
    """)

    conn.commit()
    conn.close()    
