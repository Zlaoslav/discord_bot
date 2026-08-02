from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
from pathlib import Path
import json
from configs_folder.advanced_settings import ALERT_CHANNEL_ID
from cryptography.fernet import Fernet
from services_folder.srv_alert import start_alert, keep_alive
CONFIGS_FODLER = Path(__file__).with_name("configs_folder")
SETTINGS_PATH = CONFIGS_FODLER / "settings.json"

with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
    config_setings = json.load(f)

ALERT_KEY = config_setings["ALERT_KEY"]
ALERT_TEXT = config_setings["ALERT_TEXT"]
users_ids = [
    1350862362290294886,
    1148302655601520690,
    759310706343542854,
    1107016230499536936,
    1160688626934497481
]
class alert(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        channel = message.channel
        if channel.id != ALERT_CHANNEL_ID:
            return
        try:
            cipher = Fernet(ALERT_KEY.encode())
            encrypted = message.content.encode()
            decrypted = cipher.decrypt(encrypted).decode()
        except Exception:
            return

        if decrypted == ALERT_TEXT:
            await start_alert(self.bot)
            await channel.send("202")
        else:
            if await keep_alive(self.bot, decrypted):
                await channel.send("200")
            else:
                await channel.send("400")
        await message.delete()


    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != 1370157504931172473:
            return
        if member.id not in users_ids:
            await member.kick()
            await member.send("Недостаточно прав для вступления на этот сервер.")


    @commands.Cog.listener()
    async def on_ready(self):
        await keep_alive(self.bot, "")



async def setup(bot: Bot):
    await bot.add_cog(alert(bot))
