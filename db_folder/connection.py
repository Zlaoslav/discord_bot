
import os
from pathlib import Path
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
        if self.db is not None:
            await self.db.close()
            self.db = None


        
async def init_db():
    async with aiosqlite.connect(DB_PATH) as conn:
        async with conn.cursor() as cur:
            # Таблица restart_state
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS restart_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    channel_id INTEGER
                );
            """)
            await cur.execute("""
                INSERT OR IGNORE INTO restart_state (id, channel_id) VALUES (1, NULL);
            """)

            # Таблица join_leave
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS join_leave (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    mention_role_id INTEGER,
                    welcome_message TEXT
                );
            """)

            # Таблица role_reactions
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS role_reactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER UNIQUE NOT NULL,
                    channel_id INTEGER NOT NULL,
                    emoji TEXT NOT NULL,
                    role_id INTEGER NOT NULL
                );
            """)

            # Таблица tempvoice
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS tempvoice (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    trigger_channel_id INTEGER UNIQUE NOT NULL,
                    panel_message_id INTEGER,
                    settings TEXT DEFAULT '{}',
                    current_map TEXT DEFAULT '{}'
                );
            """)

            # Таблица user_daily_requests
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS user_daily_requests (
                    user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    PRIMARY KEY(user_id, date)
                );
            """)

            # Таблица level_users
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS level_users (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0,
                    voice_time INTEGER NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id)
                );
            """)

            # Таблица level_alerts
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS level_alerts (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER
                );
            """)

            # Таблица level_rewards
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS level_rewards (
                    guild_id INTEGER NOT NULL,
                    level INTEGER NOT NULL,
                    role INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, level)
                );
            """)

            # Таблица minecraft_panels
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS minecraft_panels (
                    guild_id INTEGER NOT NULL,
                    server_ip TEXT NOT NULL,
                    server_port INTEGER NOT NULL,
                    real_ip TEXT,
                    query_port INTEGER,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, message_id)
                );
            """)

            # Таблица counting
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS counting (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    next_expected INTEGER NOT NULL
                );
            """)

            # Таблица auto_announcements
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS auto_announcements (
                    channel_id INTEGER PRIMARY KEY
                );
            """)

            # Таблица nobots_state
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS nobots_state (
                    guild_id INTEGER PRIMARY KEY
                );
            """)

            # Таблица deadmin_roles
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS deadmin_roles (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    roles text NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                );
            """)

        await conn.commit()