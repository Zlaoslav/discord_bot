from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.srv_restart_state import restart_process, quickrestart_process, notify_after_restart

import os 
from typing import Optional

class restart_state(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.command(name="shutdownbot")
    async def shutdownbot(self, ctx: commands.Context):
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.HOST):
            await ctx.send("У вас нет прав для этой команды.")
            return
        await ctx.send("Shutdown...")

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

        await self.bot.close()

        os._exit(0)

    @commands.command(name="restartbot")
    async def restartbot(self, ctx: commands.Context, channel_id: Optional[int] = None):
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.HOST):
            await ctx.send("У вас нет прав для этой команды.")
            return

        if channel_id:
            ctx.restart_target = channel_id
        else:
            ctx.restart_target = ctx.channel.id

        await restart_process(self.bot, ctx)

    @commands.command(name="quickrestartbot")
    async def quickrestartbot(self, ctx: commands.Context, channel_id: Optional[int] = None):
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.HOST):
            await ctx.send("У вас нет прав для этой команды.")
            return

        if channel_id:
            ctx.restart_target = channel_id
        else:
            ctx.restart_target = ctx.channel.id

        await quickrestart_process(self.bot, ctx)

    @commands.Cog.listener()
    async def on_ready(self):
        await notify_after_restart(self.bot)



async def setup(bot: Bot):
    await bot.add_cog(restart_state(bot))
    