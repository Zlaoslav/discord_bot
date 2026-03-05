import os
import asyncio
from typing import Any, Optional, Dict
from pathlib import Path
import json
import socket
import time

import discord
from discord.ext import commands, tasks
from discord.ui import View, Select
import discord.app_commands

from db_folder import DB

import services_folder.hlpr_perms_manager as hlpr_perms_manager
from configs_folder.advanced_settings import OWNER_ID
from services_folder.hlpr_logging import logger
# ------------------ main vars setup ------------------
SCRIPT_DIR = Path(__file__).parent
USERNAME = os.getenv("USERNAME") or "unknown"
HOSTNAME = socket.gethostname()
START_TIME = time.time()


# ------------------ setings setup ------------------
CONFIGS_FODLER = Path(__file__).with_name("configs_folder")
SETTINGS_PATH = CONFIGS_FODLER / "settings.json"

with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
    config_setings = json.load(f)

DISCORD_TOKEN = config_setings["DISCORD_TOKEN"]
GUILD_ID = config_setings["GUILD_ID"]
os.environ["GEMINI_API_KEY"] = config_setings["GEMINI_TOKEN"]

intents = discord.Intents.default()
intents.guilds = True           # нужен для доступа к информации о гильдиях
intents.presences = True        # нужен для работы с статусом участников
intents.members = True          # нужен для работы с Member объектами
intents.message_content = True  # нужен для префикс-команд (чтение сообщений)
intents.reactions = True        # нужен для обработки реакций
intents.voice_states = True     # нужен для отслеживания входа/выхода в войс
GUILD = discord.Object(id=GUILD_ID)

hlpr_perms_manager.init_perms(OWNER_ID)


class Bot(commands.Bot):
    db: DB
    def __init__(self):
        super().__init__(
            command_prefix="?",
            intents=intents
        )
        self.db: DB

    async def setup_hook(self):
        # --- БД ---
        self.db = DB()
        await self.db.init_db()
        await self.db.connect()

        # --- автозагрузка всех cog ---
        await self._load_all_cogs()

        # --- синхронизация slash-команд ---
        await self.tree.sync()

    async def _load_all_cogs(self):
        base_path = os.path.join(os.path.dirname(__file__), "cogs_folder")
        loaded_cogs_count = 0
        error_cogs_count = 0

        for file in os.listdir(base_path):
            if not file.endswith(".py"):
                continue
            if not file.startswith("cog_"):
                continue

            ext = f"cogs_folder.{file[:-3]}"

            try:
                await self.load_extension(ext)
                logger.info(f"COG loaded: {ext}")
                loaded_cogs_count += 1
            except Exception as e:
                logger.error(f"Failed to load cog: {ext}, Error: {e}")
                error_cogs_count += 1
        
        if error_cogs_count == 0:
            logger.info(f"All сogs loaded successfully ({loaded_cogs_count})")
        else:
            logger.critical(f"Only {loaded_cogs_count}/{loaded_cogs_count + error_cogs_count} cogs have been loaded.")



    async def close(self):
        if self.db:
            await self.db.database.close()
        await super().close()


def main():
    bot = Bot()
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()