from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger


class root(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @app_commands.command(
        name="reload_cog",
        description="Перезагрузить cog [host only]"
    )
    async def reload_cog(
        self,
        interaction: discord.Interaction,
        cog_name: str
    ):
        await interaction.response.defer()
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.HOST):
            await interaction.followup.send("У вас нет прав для этой команды.")
            return
        
        try:
            await self.bot.reload_extension(f"cogs_folder.cog_{cog_name}")
            await interaction.followup.send(f"cogs_folder.cog_{cog_name} успешно перезагружен!")
        except Exception as e:
            await interaction.followup.send(f"cogs_folder.cog_{cog_name} ошибка перезагрузки!")
            logger.error(e)

    @commands.command(name="reload_cog")
    async def reload_cog_prefic(
        self,
        ctx: commands.Context,
        cog_name: str
    ):
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.HOST):
            await ctx.send("У вас нет прав для этой команды.")
            return
        
        try:
            await self.bot.reload_extension(f"cogs_folder.cog_{cog_name}")
            await ctx.send(f"cogs_folder.cog_{cog_name} успешно перезагружен!")
        except Exception as e:
            await ctx.send(f"cogs_folder.cog_{cog_name} ошибка перезагрузки!")
            logger.error(e)



    @app_commands.command(
        name="unload_cog",
        description="Выключить cog [host only] [!ВНИМАНИЕ! ROOT ИЛИ RESTART НЕВОЗМОЖНО ОТКЛЮЧИТЬ]"
    )
    async def unload_cog(
        self,
        interaction: discord.Interaction,
        cog_name: str
    ):
        await interaction.response.defer()
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.HOST):
            await interaction.followup.send("У вас нет прав для этой команды.")
            return
        
        if cog_name == "root" or cog_name == "restart_state":
            interaction.followup.send("ROOT или RESTART_STATE нельзя выключать!")
            return
        
        try:
            await self.bot.unload_extension(f"cogs_folder.cog_{cog_name}")
            await interaction.followup.send(f"cogs_folder.cog_{cog_name} успешно выключен!")
        except Exception as e:
            await interaction.followup.send(f"cogs_folder.cog_{cog_name} ошибка выключения!")
            logger.error(e)

    @commands.command(name="unload_cog")
    async def unload_cog_prefic(
        self,
        ctx: commands.Context,
        cog_name: str
    ):
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.HOST):
            await ctx.send("У вас нет прав для этой команды.")
            return
        
        if cog_name == "root" or cog_name == "restart_state":
            ctx.send("ROOT или RESTART_STATE нельзя выключать!")
            return
        
        try:
            await self.bot.unload_extension(f"cogs_folder.cog_{cog_name}")
            await ctx.send(f"cogs_folder.cog_{cog_name} успешно выключен!")
        except Exception as e:
            await ctx.send(f"cogs_folder.cog_{cog_name} ошибка выключения!")
            logger.error(e)



    @app_commands.command(
        name="load_cog",
        description="Включить cog [host only]"
    )
    async def load_cog(
        self,
        interaction: discord.Interaction,
        cog_name: str
    ):
        await interaction.response.defer()
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.HOST):
            await interaction.followup.send("У вас нет прав для этой команды.")
            return

        try:
            await self.bot.load_extension(f"cogs_folder.cog_{cog_name}")
            await interaction.followup.send(f"cogs_folder.cog_{cog_name} успешно включён!")
        except Exception as e:
            await interaction.followup.send(f"cogs_folder.cog_{cog_name} ошибка включения!")
            logger.error(e)

    @commands.command(name="load_cog")
    async def load_cog_prefic(
        self,
        ctx: commands.Context,
        cog_name: str
    ):
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.HOST):
            await ctx.send("У вас нет прав для этой команды.")
            return

        
        try:
            await self.bot.load_extension(f"cogs_folder.cog_{cog_name}")
            await ctx.send(f"cogs_folder.cog_{cog_name} успешно включён!")
        except Exception as e:
            await ctx.send(f"cogs_folder.cog_{cog_name} ошибка включения!")
            logger.error(e)


async def setup(bot: Bot):
    await bot.add_cog(root(bot))
