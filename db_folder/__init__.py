import os
from .connection import Database
from .db_daily_requests import DailyRequestsRepository
from .db_levels_rewards import LevelRewardsRepository
from .db_minecraft_panel import MinecraftPanelRepository
import aiosqlite
from typing import Self

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_state.db")

from typing import Self
import aiosqlite

class DB:
    daily_requests: DailyRequestsRepository
    level_rewards: LevelRewardsRepository
    minecraft_panel: MinecraftPanelRepository

    def __init__(self, path: str):
        self.database = Database(path)

    async def __init_repos(self) -> None:
        db: aiosqlite.Connection = self.database.db
        self.daily_requests = DailyRequestsRepository(db)
        self.level_rewards = LevelRewardsRepository(db)
        self.minecraft_panel = MinecraftPanelRepository(db)

    async def connect(self) -> None:
        await self.database.connect()
        await self.__init_repos()

    async def close(self) -> None:
        await self.database.close()

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
