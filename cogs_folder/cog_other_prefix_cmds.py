from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_send_long import send_long_ctx
from configs_folder.advanced_settings import BOT_COMMANDS_LIST, CODEVERSION, START_TIME, HOSTNAME, USERNAME
from services_folder.srv_cmds_manager import sync_local_slash, clear_local_slash
import time





def format_duration(seconds: int) -> str:
    d, seconds = divmod(seconds, 86400)
    h, seconds = divmod(seconds, 3600)
    m, s = divmod(seconds, 60)
    return "".join(f"{x}{y}" for x, y in [(d,"d"),(h,"h"),(m,"m"),(s,"s")] if x)

class other_prefix_cmds(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot
        try:
            self.bot.remove_command('help')
        except Exception:
            pass


    @commands.command(name="дай_пять")
    async def give_five(self, ctx: commands.Context):
        await ctx.send("https://cdn.discordapp.com/attachments/1350866065818783788/1434491390192255096/c0aced7c-94ef-4d24-aafa-480c618a74dd.gif?ex=69106eb6&is=690f1d36&hm=ba4189460e7fd7061f8f2928c6a75205ed4d8aaeeb5c04a3fb263745f2236cda&")

    @commands.command(name="ping")
    async def ping_cmd(self, ctx: commands.Context):
        uptime = int(time.time() - START_TIME)
        await ctx.send(f"Host:{HOSTNAME}({USERNAME})\nUptime: {format_duration(uptime)}\nPing: {round(self.bot.latency * 1000)} ms\n Version: {CODEVERSION}")


    @commands.command(name="help")
    async def help_prefix(self, ctx: commands.Context):
        """Показать справку по командам (префиксная команда)."""
        text = BOT_COMMANDS_LIST.strip()
        await send_long_ctx(ctx, text)

    @commands.command(name="disablecmds")
    async def disablecmds(self, ctx: commands.Context):
        # проверка прав: нужна роль OWNER
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.HOST):
            await ctx.send("У вас нет прав для этой команды.")
            return

        # запускаем ассинхронный helper и ждём результат
        result = await clear_local_slash(self.bot, ctx.guild)
        if result is True:
            await ctx.send("✅ Удалены локальные слэш-команды")
        else:
            await ctx.send("❌ Ошибка при удалении локальных команд. Смотри лог.")

    @commands.command(name="synccmds")
    async def synccmds(self, ctx: commands.Context):
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.HOST):
            await ctx.send("У вас нет прав для этой команды.")
            return

        result = await sync_local_slash(self.bot, ctx.guild)
        if result is None:
            await ctx.send("❌ Ошибка при синхронизации. Смотри лог.")
            return

        if len(result) != 0:
            await ctx.send(f"✅ Синхронизировано {len(result)} команд(ы).")
        else:
            await ctx.send("⚠ Синхронизация прошла, но вернулось 0 команд.")


async def setup(bot: Bot):
    await bot.add_cog(other_prefix_cmds(bot))
