from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger
from configs_folder.advanced_settings import BASE_DIR, REPO_URL

from pathlib import Path
from typing import Optional
import subprocess

def run_command(cmd, show_output=True):
    print(f"[CMD] {' '.join(cmd)}")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        if show_output:
            print(f". {line.strip()}")
    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)


def run_cmd(*args, cwd: Optional[Path] = None, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(list(map(str, args)), cwd=str(cwd) if cwd else None,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None,
                          check=check)

def detect_origin_default_branch(repo_root: Path) -> Optional[str]:
    """
    Попытки определить ветку по-умолчанию у origin.
    Возвращает имя ветки без префикса origin/, например 'main' или 'master'
    """
    try:
        # Обычно origin/HEAD -> origin/main или origin/master
        cp = run_cmd("git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "origin/HEAD", cwd=repo_root)
        text = cp.stdout.decode().strip()
        if "/" in text:
            return text.split("/", 1)[1]
    except subprocess.CalledProcessError:
        pass

    # Попробуем через ls-remote --symref (внешний remote)
    try:
        cp = run_cmd("git", "ls-remote", "--symref", "origin", "HEAD", cwd=repo_root, check=True)
        out = cp.stdout.decode()
        # строка вида: "ref: refs/heads/main\tHEAD"
        for line in out.splitlines():
            if line.startswith("ref:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].startswith("refs/heads/"):
                    return parts[1].split("/", 2)[2]
    except subprocess.CalledProcessError:
        pass

    # fallback: проверим существование origin/main или origin/master прямо в remote refs
    for candidate in ("main", "master"):
        try:
            run_cmd("git", "-C", str(repo_root), "ls-remote", "--heads", "origin", candidate, cwd=repo_root)
            return candidate
        except subprocess.CalledProcessError:
            continue
    return None

def remote_ref_exists(repo_root: Path, branch: str) -> bool:
    """
    Проверить, присутствует ли refs/remotes/origin/<branch> в локальном git.
    Возвращает True если ref доступен (локально или в удалённом списке после fetch).
    """
    try:
        # сначала проверим локальные refs/remotes
        run_cmd("git", "-C", str(repo_root), "show-ref", "--verify", f"refs/remotes/origin/{branch}", cwd=repo_root, check=True)
        return True
    except subprocess.CalledProcessError:
        # если нет локальной записи, попробуем проверить через ls-remote (удалённый origin)
        try:
            cp = run_cmd("git", "ls-remote", "--heads", "origin", branch, cwd=repo_root, check=True)
            if cp.stdout and cp.stdout.strip():
                return True
        except subprocess.CalledProcessError:
            pass
    return False


def git_update():
    git_dir = BASE_DIR / ".git"
    # Helper to try resetting to one of candidate branches
    def try_reset(candidates: list[str]) -> bool:
        for c in candidates:
            # проверим, существует ли origin/<c>
            if not remote_ref_exists(BASE_DIR, c):
                print(f"[INFO] origin/{c} не найден — пропускаем попытку reset.")
                continue
            try:
                run_command(["git", "-C", str(BASE_DIR), "reset", "--hard", f"origin/{c}"])
                print(f"[INFO] Reset to origin/{c} succeeded")
                return True
            except subprocess.CalledProcessError:
                print(f"[WARN] Reset to origin/{c} failed")
                continue
        return False

    if git_dir.exists():
        print("[INFO] Репозиторий найден, обновляем...")
        try:
            # fetch all refs from origin (сжатый и тихий режим)
            run_command(["git", "-C", str(BASE_DIR), "fetch", "origin", "--prune", "--quiet"])
        except subprocess.CalledProcessError as e:
            print(f"[WARNING] git fetch failed: {e}")
            # если fetch не удался — не будем пытаться reset к origin/<branch>, т.к. рефы, возможно, не обновлены
            return False

        # Попробуем определить ветку по-умолчанию у origin и сделать reset
        branch = detect_origin_default_branch(BASE_DIR) or "main"
        print(f"[INFO] Попытка сброса к ветке по-умолчанию: {branch}")
        if try_reset([branch, "main", "master"]):
            print("[INFO] Репозиторий обновлен!")
            return True
        else:
            print("[WARNING] Не удалось сделать 'git reset' к origin/<branch> — пропускаем обновление файлов.")
            return False
    else:
        print("[INFO] Инициализация нового репозитория...")
        try:
            run_command(["git", "init", str(BASE_DIR)])
            run_command(["git", "-C", str(BASE_DIR), "remote", "add", "origin", REPO_URL])
            # Попытаемся получить heads с origin (чтобы узнать, есть ли доступ)
            fetched = False
            try:
                run_command(["git", "-C", str(BASE_DIR), "fetch", "origin", "--quiet"])
                fetched = True
            except subprocess.CalledProcessError as e:
                print(f"[WARNING] git fetch после add remote FAILED: {e}")
                fetched = False

            if not fetched:
                print("[WARNING] Не удалось получить refs от origin; репозиторий создан локально без фетча.")
        except subprocess.CalledProcessError as e:
            print(f"[WARNING] Ошибка при инициализации/фетче репозитория: {e}")
            return False

        branch = detect_origin_default_branch(BASE_DIR) or "main"
        print(f"[INFO] После инициализации определена ветка: {branch}")
        if try_reset([branch, "main", "master"]):
            print("[INFO] Репозиторий инициализирован и обновлён!")
            return True
        else:
            print("[WARNING] Не удалось сделать 'git reset' после инициализации репозитория.")
            return False

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


    @commands.command(name="updatebot")
    async def updatebot(
        self,
        ctx: commands.Context
    ):
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.HOST):
            await ctx.send("У вас нет прав для этой команды.")
            return
        
        await ctx.send("Обновление...")
        ok = git_update()
        if ok:
            await ctx.send("Успешно обновлено")
        else:
            await ctx.send("Ошибка обновления!")
        


async def setup(bot: Bot):
    await bot.add_cog(root(bot))
