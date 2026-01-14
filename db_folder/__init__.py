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
from .db_join_leave import JoinLeaveRepository
from .db_role_reactions import RoleReactionsRepository
from .db_counting import CountingRepository
from .db_restart_state import RestartStateRepository

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_state.db")

class DB:
    daily_requests: DailyRequestsRepository
    level_rewards: LevelRewardsRepository
    level_users: LevelUsersRepository
    level_alerts: LevelAlertsRepository
    minecraft_panel: MinecraftPanelRepository
    tempvoice: TempvoiceRepository
    join_leave: JoinLeaveRepository
    role_reactions: RoleReactionsRepository
    counting: CountingRepository
    restart_state: RestartStateRepository

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
        self.join_leave = JoinLeaveRepository(db)
        self.role_reactions = RoleReactionsRepository(db)
        self.counting = CountingRepository(db)
        self.restart_state = RestartStateRepository(db)
        
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
