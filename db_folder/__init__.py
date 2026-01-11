import os
import aiosqlite
from typing import Self

from .connection import Database, init_db
from .db_daily_requests import DailyRequestsRepository
from .db_level_rewards import LevelRewardsRepository
from .db_level_users import LevelUsersRepository
from .db_level_alerts import LevelAlertsRepository
from .db_minecraft_panel import MinecraftPanelRepository
from .db_tempvoice import TempvoiceRepository


DB_PATH = os.path.join(os.path.dirname(__file__), "bot_state.db")

class DB:
    daily_requests: DailyRequestsRepository
    level_rewards: LevelRewardsRepository
    level_users : LevelUsersRepository
    level_alerts : LevelAlertsRepository
    minecraft_panel: MinecraftPanelRepository
    tempvoice: TempvoiceRepository

    def __init__(self, path: str):
        self.database = Database(path)

    async def __init_repos(self) -> None:
        db: aiosqlite.Connection = self.database.db
        self.daily_requests = DailyRequestsRepository(db)
        self.level_rewards = LevelRewardsRepository(db)
        self.level_users = LevelUsersRepository(db)
        self.level_alerts = LevelAlertsRepository(db)
        self.minecraft_panel = MinecraftPanelRepository(db)
        self.tempvoice = TempvoiceRepository(db)

    def init_db(self):
        init_db()

        

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
