from bot import Bot
import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger
from configs_folder.advanced_settings import BASE_DIR, REPO_URL

from pathlib import Path
from typing import Optional, List, Set, Tuple
import subprocess
import os
import sys
import datetime

# -----------------------
# Helper subprocess utils
# -----------------------
def run_command(cmd: List[str], show_output: bool = True) -> None:
    """Запускает команду и печатает поток stdout/stderr в реальном времени. Выбрасывает CalledProcessError при non-zero."""
    print(f"[CMD] {' '.join(cmd)}")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        if show_output:
            print(f". {line.rstrip()}")
    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)

def run_cmd(*args, cwd: Optional[Path] = None, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(list(map(str, args)), cwd=str(cwd) if cwd else None,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None,
                          check=check)

# -----------------------
# Git helpers (твои старые + расширения)
# -----------------------
def detect_origin_default_branch(repo_root: Path) -> Optional[str]:
    try:
        cp = run_cmd("git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "origin/HEAD", cwd=repo_root)
        text = cp.stdout.decode().strip()
        if "/" in text:
            return text.split("/", 1)[1]
    except subprocess.CalledProcessError:
        pass

    try:
        cp = run_cmd("git", "ls-remote", "--symref", "origin", "HEAD", cwd=repo_root, check=True)
        out = cp.stdout.decode()
        for line in out.splitlines():
            if line.startswith("ref:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].startswith("refs/heads/"):
                    return parts[1].split("/", 2)[2]
    except subprocess.CalledProcessError:
        pass

    for candidate in ("main", "master"):
        try:
            run_cmd("git", "-C", str(repo_root), "ls-remote", "--heads", "origin", candidate, cwd=repo_root)
            return candidate
        except subprocess.CalledProcessError:
            continue
    return None

def remote_ref_exists(repo_root: Path, branch: str) -> bool:
    try:
        run_cmd("git", "-C", str(repo_root), "show-ref", "--verify", f"refs/remotes/origin/{branch}", cwd=repo_root, check=True)
        return True
    except subprocess.CalledProcessError:
        try:
            cp = run_cmd("git", "ls-remote", "--heads", "origin", branch, cwd=repo_root, check=True)
            if cp.stdout and cp.stdout.strip():
                return True
        except subprocess.CalledProcessError:
            pass
    return False

def git_update() -> bool:
    """
    Выполняет fetch + reset --hard к origin/<default branch>.
    Возвращает True при успехе.
    """
    git_dir = BASE_DIR / ".git"
    def try_reset(candidates: List[str]) -> bool:
        for c in candidates:
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
            run_command(["git", "-C", str(BASE_DIR), "fetch", "origin", "--prune", "--quiet"])
        except subprocess.CalledProcessError as e:
            print(f"[WARNING] git fetch failed: {e}")
            return False

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

# -----------------------
# Diff helpers
# -----------------------
def get_changed_files(before: str, after: str) -> List[Path]:
    cp = run_cmd("git", "-C", str(BASE_DIR), "diff", "--name-only", before, after, cwd=BASE_DIR, check=True)
    out = cp.stdout.decode().strip()
    if not out:
        return []
    return [BASE_DIR / line.strip() for line in out.splitlines() if line.strip()]

def changed_cogs_from_files(files: List[Path]) -> Set[str]:
    result = set()
    for f in files:
        try:
            rel = f.relative_to(BASE_DIR)
        except Exception:
            continue
        parts = rel.parts
        if "cogs_folder" in parts and f.name.startswith("cog_") and f.suffix == ".py":
            module = ".".join(rel.with_suffix("").parts)
            result.add(module)
    return result

# -----------------------
# Backup (store previous versions)
# -----------------------
def backup_cog_files_from_git(before: str, files: List[Path]) -> Path:
    """
    Сохраняет версии файлов из коммита <before> в BASE_DIR/.cog_backups/<before>/...
    Возвращает путь к каталогу бекапа.
    """
    backup_root = BASE_DIR / ".cog_backups" / before
    for f in files:
        try:
            rel = f.relative_to(BASE_DIR)
        except Exception:
            continue
        target_path = backup_root / rel
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # Получим содержимое из старого коммита
        try:
            cp = run_cmd("git", "-C", str(BASE_DIR), "show", f"{before}:{str(rel)}", cwd=BASE_DIR, check=True)
            content_bytes = cp.stdout
            # CompletedProcess.stdout is bytes; if None, skip
            if content_bytes is None:
                content = ""
            else:
                if isinstance(content_bytes, bytes):
                    content = content_bytes.decode("utf-8", errors="replace")
                else:
                    content = str(content_bytes)
            target_path.write_text(content, encoding="utf-8")
        except subprocess.CalledProcessError:
            # файл отсутствовал в before — пропускаем
            continue
    return backup_root

# -----------------------
# Rollback helper
# -----------------------
def rollback_to_commit(commit_hash: str) -> bool:
    try:
        run_command(["git", "-C", str(BASE_DIR), "reset", "--hard", commit_hash])
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Rollback to {commit_hash} failed: {e}")
        return False

# -----------------------
# Cog reload logic
# -----------------------
async def reload_changed_cogs(bot: Bot, modules: Set[str],
                              prev_loaded: Set[str]) -> Tuple[bool, Optional[str]]:
    """
    Пытается применить новые версии к заданным модулям.
    Если какой-то модуль не загрузился — возвращает (False, module_name).
    prev_loaded — набор модулей, которые были загружены ДО обновления (для rollback логики).
    """
    successfully_loaded_new = set()

    for module in modules:
        try:
            if module in bot.extensions:
                # перезагрузить
                await bot.reload_extension(module)
            else:
                # первый раз загружаем
                await bot.load_extension(module)
                successfully_loaded_new.add(module)
            logger.info(f"{module} reloaded/loaded successfully")
        except Exception as e:
            logger.exception(f"Failed to load/reload {module}: {e}")
            # при ошибке — сначала выгружаем те модули, которые были загружены как новые (чтобы не оставлять "плавающие" ext)
            for m in successfully_loaded_new:
                try:
                    if m in bot.extensions:
                        await bot.unload_extension(m)
                except Exception:
                    logger.exception(f"Failed unload after partial success: {m}")
            return False, module

    # все успешно
    return True, None
RELOAD_ALL_FOLDERS = {"services_folder", "db_folder", "configs_folder"}

def classify_changes(changed_files: list[Path]) -> tuple[set[str], bool]:
    """
    Возвращает:
    - set модулей cog_* которые нужно перезагрузить
    - bool: требуется ли перезагрузка всех когов
    """
    changed_cogs = set()
    reload_all = False

    for f in changed_files:
        try:
            rel = f.relative_to(BASE_DIR)
        except Exception:
            continue

        parts = rel.parts
        if not parts:
            continue

        if parts[0] in RELOAD_ALL_FOLDERS:
            reload_all = True

        if parts[0] == "cogs_folder" and f.name.startswith("cog_") and f.suffix == ".py":
            module = ".".join(rel.with_suffix("").parts)
            changed_cogs.add(module)

    return changed_cogs, reload_all


def list_all_cogs() -> set[str]:
    cogs_dir = BASE_DIR / "cogs_folder"
    result = set()
    for f in cogs_dir.glob("cog_*.py"):
        result.add(f"cogs_folder.{f.stem}")
    return result
async def reload_cogs_with_rollback(bot: Bot, target_cogs: set[str]) -> tuple[bool, str | None]:
    """
    Перезагружает указанные коги.
    Возвращает (успех, имя упавшего coga)
    """
    loaded_before = set(bot.extensions.keys())
    loaded_new = set()

    for cog in target_cogs:
        try:
            if cog in bot.extensions:
                await bot.reload_extension(cog)
            else:
                await bot.load_extension(cog)
                loaded_new.add(cog)
        except Exception as e:
            logger.exception(f"Ошибка загрузки {cog}: {e}")

            # откат runtime-состояния
            for m in loaded_new:
                try:
                    if m in bot.extensions:
                        await bot.unload_extension(m)
                except Exception:
                    pass

            for m in target_cogs:
                if m in loaded_before:
                    try:
                        if m in bot.extensions:
                            await bot.reload_extension(m)
                        else:
                            await bot.load_extension(m)
                    except Exception:
                        pass

            return False, cog

    return True, None

# -----------------------
# Команда и Cog
# -----------------------
class root(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    # (свои команды load/unload/reload оставил без изменений, только update обновлён)
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

    # -----------------------
    # Основная команда updatebot с selective reload + rollback
    # -----------------------
    @commands.command(name="updatebot")
    async def updatebot(self, ctx: commands.Context):
        if not perms_manager.has_perm(ctx.author.id, perms_manager.PermRole.HOST):
            await ctx.send("У вас нет прав.")
            return

        msg = await ctx.send("🔄 Проверка обновлений...")

        before = run_cmd(
            "git", "-C", str(BASE_DIR), "rev-parse", "HEAD",
            cwd=BASE_DIR
        ).stdout.decode().strip()

        if not git_update():
            await msg.edit(content="❌ Ошибка git обновления")
            return

        after = run_cmd(
            "git", "-C", str(BASE_DIR), "rev-parse", "HEAD",
           cwd=BASE_DIR
       ).stdout.decode().strip()

        if before == after:
           await msg.edit(content="ℹ️ Обновлений нет")
           return

        changed_files = get_changed_files(before, after)
        changed_cogs, reload_all = classify_changes(changed_files)

        if reload_all:
            target_cogs = list_all_cogs()
        else:
            target_cogs = changed_cogs

        if not target_cogs:
            await msg.edit(content="ℹ️ Изменения не затрагивают коги")
            return

        await msg.edit(content="♻️ Перезагрузка когов...")

        ok, failed = await reload_cogs_with_rollback(self.bot, target_cogs)

        if not ok:
            rollback_to_commit(before)
            await msg.edit(
                content=f"❌ Ошибка загрузки `{failed}`.\n"
                       f"Выполнен rollback к предыдущей версии."
            )
            return

        await self.bot.tree.sync()

        files_list = "\n".join(f"- `{f.relative_to(BASE_DIR)}`" for f in changed_files)
        cogs_list = "\n".join(f"- `{c}`" for c in sorted(target_cogs))

        await msg.edit(
            content=(
                "✅ Обновление успешно\n\n"
                "**Обновлённые файлы:**\n"
                f"{files_list}\n\n"
                "**Перезагруженные коги:**\n"
                f"{cogs_list}"
            )
        )


async def setup(bot: Bot):
    await bot.add_cog(root(bot))
