from version import CODEVERSION
import asyncio
import json
import subprocess
import sys
from pathlib import Path
import time
import os
import tempfile
import socket
import requests
import platform
from datetime import datetime, timezone
import uuid

# Platform-specific imports
IS_WINDOWS = platform.system() == "Windows"
if IS_WINDOWS:
    try:
        import msvcrt
        import win32api
        import win32con
    except ImportError:
        print("[WARN] Windows-specific modules not available; lock features may be limited")
        IS_WINDOWS = False

CURRENT_DIR = Path(__file__).parent.resolve()
BOT_FILE = CURRENT_DIR / "bot.py"
REPO_URL = "https://github.com/Zlaoslav/discord_bot"
REQUIREMENTS = CURRENT_DIR / "requirements.txt"

# Load config
CONFIGS_FOLDER = CURRENT_DIR / "configs_folder"
SETTINGS_PATH = CONFIGS_FOLDER / "setings.json"
if not SETTINGS_PATH.exists():
    raise FileNotFoundError(f"Config not found: {SETTINGS_PATH}")
with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

DISCORD_TOKEN = config.get("DISCORD_TOKEN")
STATUS_WEBHOOK_URL = config.get("STATUS_WEBHOOK_URL") or config.get("STATUS_WEBHOOK")

# Lock-related configuration: separate bot token and channel id (no webhook for lock)
LOCK_BOT_TOKEN = config.get("LOCK_BOT_TOKEN")
LOCK_CHANNEL_ID = int(config.get("LOCK_CHANNEL_ID")) if config.get("LOCK_CHANNEL_ID") else None
MAIN_THREAD_ID = None

USERNAME = os.getenv("USERNAME") or "unknown"
HOSTNAME = socket.gethostname()
starttime = time.time()


# ------------------- Функция для выполнения команды с прогрессом -------------------
def run_command(cmd, show_output=True):
    print(f"[CMD] {' '.join(cmd)}")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        if show_output:
            print(f". {line.strip()}")
    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)


# ------------------- Git/pip helpers -------------------
def git_update():
    git_dir = CURRENT_DIR / ".git"
    if git_dir.exists():
        print("[INFO] Репозиторий найден, обновляем...")
        run_command(["git", "-C", str(CURRENT_DIR), "fetch", "--all"])
        run_command(["git", "-C", str(CURRENT_DIR), "reset", "--hard", "origin/main"])
    else:
        print("[INFO] Инициализация нового репозитория...")
        run_command(["git", "init"])
        run_command(["git", "remote", "add", "origin", REPO_URL])
        run_command(["git", "fetch"])
        run_command(["git", "reset", "--hard", "origin/main"])
    print("[INFO] Репозиторий обновлен!")


def install_requirements():
    print("[INFO] Обновляем pip...")
    run_command([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    if REQUIREMENTS.exists():
        print(f"[INFO] Устанавливаем зависимости из {REQUIREMENTS.name}...")
        run_command([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    else:
        print("[INFO] requirements.txt не найден, пропускаем установку зависимостей.")


# ------------------- Status webhook -------------------
def send_status(msg: str, thread_id: int = None):
    """Send status via webhook (if configured)."""
    if not STATUS_WEBHOOK_URL:
        print("[WARN] STATUS_WEBHOOK_URL not configured; skipping status post")
        return
    try:
        # threads removed — post directly to webhook
        requests.post(STATUS_WEBHOOK_URL, json={"content": msg}, timeout=5)
    except Exception as e:
        print("send_status error:", e)


# ------------------- Local lock (from main.py) -------------------
LOCK_PREFIX = "LOCK|"
_local_lock_path = os.path.join(tempfile.gettempdir(), f"master_lock_{USERNAME}.lock")
_local_lock_fh = None
_local_lock_socket = None
LOCK_SOCKET_PORT = int(config.get("LOCK_SOCKET_PORT")) if config.get("LOCK_SOCKET_PORT") else 50001


def acquire_local_lock() -> bool:
    global _local_lock_fh
    global _local_lock_socket
    # Primary mechanism: try to bind a localhost TCP port. If bind succeeds,
    # we assume this instance is the sole owner and keep the socket open.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", LOCK_SOCKET_PORT))
        s.listen(1)
        _local_lock_socket = s
        # Also write pid/timestamp to a lock file for diagnostics
        try:
            fh = open(_local_lock_path, "w")
            fh.write(f"{os.getpid()}\n{time.time()}\n")
            fh.flush()
            _local_lock_fh = fh
        except Exception:
            # non-fatal: socket lock is primary
            _local_lock_fh = None
        return True
    except OSError:
        # Port already in use — likely another instance. Fall back to file lock.
        pass

    # Fallback: file locking (POSIX or Windows)
    if not IS_WINDOWS:
        try:
            fh = open(_local_lock_path, "w")
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            _local_lock_fh = fh
            fh.write(f"{os.getpid()}\n{time.time()}\n")
            fh.flush()
            return True
        except (IOError, BlockingIOError) as e:
            try:
                fh.close()
            except:
                pass
            return False

    # Windows fallback using msvcrt
    try:
        fh = open(_local_lock_path, "a+b")
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            fh.close()
            return False
        _local_lock_fh = fh
        fh.seek(0)
        fh.truncate()
        fh.write(f"{os.getpid()}\n{time.time()}\n".encode())
        fh.flush()
        return True
    except Exception as e:
        try:
            fh.close()
        except:
            pass
        return False


def release_local_lock():
    global _local_lock_fh
    try:
        if _local_lock_fh:
            if IS_WINDOWS:
                try:
                    msvcrt.locking(_local_lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
                except:
                    pass
            else:
                # Linux/macOS: fcntl unlock
                try:
                    import fcntl
                    fcntl.flock(_local_lock_fh.fileno(), fcntl.LOCK_UN)
                except:
                    pass
            try:
                _local_lock_fh.close()
            except:
                pass
            _local_lock_fh = None
        # close socket lock if present
        global _local_lock_socket
        if '_local_lock_socket' in globals() and _local_lock_socket:
            try:
                _local_lock_socket.close()
            except:
                pass
            _local_lock_socket = None
        if os.path.exists(_local_lock_path):
            try:
                os.remove(_local_lock_path)
            except:
                pass
    except Exception as e:
        print("release_local_lock error:", e)


# ------------------- Console handler -------------------
def format_duration(seconds: int) -> str:
    d, seconds = divmod(seconds, 86400)
    h, seconds = divmod(seconds, 3600)
    m, s = divmod(seconds, 60)
    return "".join(f"{x}{y}" for x, y in [(d, "d"), (h, "h"), (m, "m"), (s, "s")] if x)


is_waiting = False
sent_can_start = False
sent_version_alert = False


def console_handler(event):
    global is_waiting
    if IS_WINDOWS:
        if event in (win32con.CTRL_C_EVENT, win32con.CTRL_BREAK_EVENT,
                     win32con.CTRL_CLOSE_EVENT, win32con.CTRL_LOGOFF_EVENT,
                     win32con.CTRL_SHUTDOWN_EVENT):
            uptime = int(time.time() - starttime)
            if is_waiting:
                send_status(f"```diff\n- {USERNAME} Now Can't Start\n```", thread_id=MAIN_THREAD_ID)
            else:
                send_status(f"```diff\n- Shutdown, UpTime {format_duration(uptime)} By {USERNAME}\n```", thread_id=MAIN_THREAD_ID)
            release_local_lock()
            os._exit(0)
        return True
    return True


try:
    if IS_WINDOWS:
        win32api.SetConsoleCtrlHandler(console_handler, True)
except Exception as e:
    print("SetConsoleCtrlHandler failed:", e)


# ------------------- Bot process loop (wrapped) -------------------
def run_bot_loop():
    """Запускает `bot.py` в цикле, отправляет сообщения о рестарте/крашах в STATUS_WEBHOOK_URL."""
    first_run = True
    last_output_lines = []
    ffmpeg_file = CURRENT_DIR / "ffmpeg"
    if ffmpeg_file.exists():
        try:
            os.chmod(ffmpeg_file, 0o755)
        except Exception:
            pass

    while True:
        if not BOT_FILE.exists():
            print(f"[ERROR] Не найден {BOT_FILE}")
            send_status(f"```diff\n- Bot file missing: {BOT_FILE}\n```", thread_id=MAIN_THREAD_ID)
            return

        quick_restart_flag = BOT_FILE.parent / ".quick_restart"
        shutdown_flag = BOT_FILE.parent / ".shutdown"
        is_quick_restart = quick_restart_flag.exists()
        is_shutdown = shutdown_flag.exists()

        # Перед рестартом — при полном рестарте делаем git update/install
        if not first_run and not is_quick_restart and not is_shutdown:
            send_status(f"```diff\n- Restarting bot by {USERNAME}\n```", thread_id=MAIN_THREAD_ID)
            try:
                git_update()
                install_requirements()
            except Exception as e:
                print(f"[WARNING] Ошибка при обновлении: {e}")
                send_status(f"```diff\n- Update failed: {e}\n```", thread_id=MAIN_THREAD_ID)
        elif is_quick_restart:
            send_status(f"```diff\n- Quick Restarting bot by {USERNAME}\n```", thread_id=MAIN_THREAD_ID)
        elif is_shutdown:
            send_status(f"```diff\n- Shutdown requested by {USERNAME}\n```", thread_id=MAIN_THREAD_ID)

        if is_quick_restart:
            try:
                quick_restart_flag.unlink()
            except Exception:
                pass
            print("[INFO] Быстрый перезапуск (без обновления файлов)")

        if is_shutdown:
            try:
                shutdown_flag.unlink()
            except Exception:
                pass
            print("[INFO] Бот выключен. Завершение работы.")
            send_status(f"```diff\n- Shutdown requested by {USERNAME}\n```", thread_id=MAIN_THREAD_ID)
            os._exit(0)
            return

        print("[INFO] Запуск бота...")
        proc = subprocess.Popen([sys.executable, str(BOT_FILE)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        last_output_lines = []
        try:
            for line in proc.stdout:
                print(line, end="")
                last_output_lines.append(line)
                if len(last_output_lines) > 200:
                    last_output_lines.pop(0)
        except Exception as e:
            print("[ERROR] reading bot stdout failed:", e)

        proc.wait()
        exit_code = proc.returncode
        print(f"[INFO] Бот завершил работу с кодом {exit_code}")

        # Уведомления о завершении
        if exit_code == 0:
            send_status(f"```diff\n+ Bot stopped normally by {USERNAME}\n```", thread_id=MAIN_THREAD_ID)
        else:
            snippet = ''.join(last_output_lines[-20:])
            short = (snippet[:1900] + '...') if len(snippet) > 1900 else snippet
            send_status(f"```diff\n- Bot crashed (code {exit_code}) by {USERNAME}\n{short}\n```", thread_id=MAIN_THREAD_ID)

        first_run = False
        print("[INFO] Перезапуск через 2 секунды...")
        time.sleep(2)


# ------------------- Main client (lock manager) -------------------
import discord

intents = discord.Intents.default()
intents.messages = True
client = discord.Client(intents=intents)

claimed_message_id = None
heartbeat_task = None
INSTANCE_ID = str(uuid.uuid4())[:8]


async def get_last_lock_message(channel):
    async for msg in channel.history(limit=50):
        if msg.author == client.user and isinstance(msg.content, str) and msg.content.startswith(LOCK_PREFIX):
            return msg
    return None


def parse_lock_content(content: str):
    try:
        parts = content.split("|")
        # New format: LOCK|username|hostname|pid|instance_id|ts|version?
        if len(parts) >= 6:
            parsed = {"username": parts[1], "hostname": parts[2], "pid": parts[3], "instance": parts[4], "ts": parts[5]}
            if len(parts) >= 7:
                parsed["version"] = parts[6]
            return parsed
        # Old format (compat): LOCK|username|hostname|ts|version
        if len(parts) >= 5:
            return {"username": parts[1], "hostname": parts[2], "ts": parts[3], "version": parts[4]}
    except:
        pass
    return None


def lock_is_recent(ts_iso: str, max_age_seconds=90):
    try:
        ts = datetime.fromisoformat(ts_iso)
        return (datetime.now(timezone.utc) - ts).total_seconds() < max_age_seconds
    except:
        return False


async def claim_lock(channel):
    global claimed_message_id, heartbeat_task
    ts = datetime.now(timezone.utc).isoformat()
    pid = os.getpid()
    m = await channel.send(f"{LOCK_PREFIX}{USERNAME}|{HOSTNAME}|{pid}|{INSTANCE_ID}|{ts}")
    claimed_message_id = m.id

    async def heartbeat():
        nonlocal m
        try:
            while True:
                await asyncio.sleep(30)
                ts2 = datetime.now(timezone.utc).isoformat()
                try:
                    await m.edit(content=f"{LOCK_PREFIX}{USERNAME}|{HOSTNAME}|{pid}|{INSTANCE_ID}|{ts2}|v{CODEVERSION}")
                except discord.NotFound:
                    m = await channel.send(f"{LOCK_PREFIX}{USERNAME}|{HOSTNAME}|{pid}|{INSTANCE_ID}|{ts2}|v{CODEVERSION}")
                    global claimed_message_id
                    claimed_message_id = m.id
        except asyncio.CancelledError:
            try:
                await m.delete()
            except:
                pass
            raise

    heartbeat_task = asyncio.create_task(heartbeat())
    return True


async def release_remote_lock(channel):
    global claimed_message_id, heartbeat_task
    try:
        if claimed_message_id:
            try:
                m = await channel.fetch_message(claimed_message_id)
            except:
                return
            try:
                await m.delete()
            except:
                pass
    except:
        pass
    if heartbeat_task:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except:
            pass
    claimed_message_id = None


async def wait_for_remote_release(channel):
    global is_waiting, sent_can_start, sent_version_alert
    is_waiting = True
    sent_can_start = False
    sent_version_alert = False
    try:
        while True:
            last = await get_last_lock_message(channel)
            if not last:
                is_waiting = False
                return True
            parsed = parse_lock_content(last.content)
            if not parsed:
                is_waiting = False
                return True
            # Check if lock is stale (no heartbeat for > 90 seconds)
            if not lock_is_recent(parsed.get("ts"), max_age_seconds=90):
                print("[INFO] Lock is stale (no heartbeat for >90s); claiming lock...")
                is_waiting = False
                return True
            if not sent_can_start:
                send_status(f"```diff\n+ Can Start By {USERNAME}\n```", thread_id=MAIN_THREAD_ID)
                sent_can_start = True
            if not sent_version_alert and parsed.get("version") != f"v{CODEVERSION}":
                send_status(f"# ALERT outdated version detected! < @&1424904999212814469 ><@727105264486187090> __v{CODEVERSION}≠{parsed.get("version")}__\ndebug info: me:{USERNAME}|{HOSTNAME}|none|**v{CODEVERSION}**, parsed message: {parsed}", thread_id=MAIN_THREAD_ID)
                sent_version_alert = True
            await asyncio.sleep(15)
    finally:
        is_waiting = False


async def run_main_job():
    print("Main job started (master).")
    send_status(f"```diff\n+ StartUp By {USERNAME}\n```", thread_id=MAIN_THREAD_ID)
    # Запускаем loop запуска бота в фоновом потоке
    loop = asyncio.get_running_loop()
    asyncio.create_task(loop.run_in_executor(None, run_bot_loop))
    try:
        while True:
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        print("Main job cancelled.")
        return


async def startup_sequence():
    if not acquire_local_lock():
        send_status(f"```diff\n- Another copy on same device ({USERNAME}) stopped\n```", thread_id=MAIN_THREAD_ID)
        os._exit(0)

    if not LOCK_CHANNEL_ID:
        # No lock channel configured; just claim local lock and start
        asyncio.create_task(run_main_job())
        return

    lock_channel = await client.fetch_channel(LOCK_CHANNEL_ID)

    last = await get_last_lock_message(lock_channel)
    if last:
        parsed = parse_lock_content(last.content)
        if parsed and lock_is_recent(parsed["ts"], max_age_seconds=90):
            ok = await wait_for_remote_release(lock_channel)
            if not ok:
                release_local_lock()
                os._exit(0)

    await claim_lock(lock_channel)
    main_task = asyncio.create_task(run_main_job())

    async def watch_lock():
        nonlocal main_task
        try:
            while True:
                await asyncio.sleep(20)
                last = await get_last_lock_message(lock_channel)
                if not last:
                    continue
                if last.id != claimed_message_id:
                    if not main_task.done():
                        main_task.cancel()
                        try:
                            await main_task
                        except:
                            pass
                    await release_remote_lock(lock_channel)
                    await wait_for_remote_release(lock_channel)
                    await claim_lock(lock_channel)
                    main_task = asyncio.create_task(run_main_job())
        except asyncio.CancelledError:
            if not main_task.done():
                main_task.cancel()
                try:
                    await main_task
                except:
                    pass
            raise

    asyncio.create_task(watch_lock())


@client.event
async def on_ready():
    try:
        await startup_sequence()
    except Exception as e:
        send_status(f"```diff\n- startup_sequence error: {e}\n```", thread_id=MAIN_THREAD_ID)
        release_local_lock()
        try:
            await client.close()
        except:
            pass
        os._exit(1)


if __name__ == "__main__":
    try:
        # Первичное обновление и установка зависимостей
        git_update()
        install_requirements()
        # Запускаем lock-client (отдельный бот) — он запустит фоновый цикл для bot.py
        token_to_run = LOCK_BOT_TOKEN or DISCORD_TOKEN
        if token_to_run:
            client.run(token_to_run)
        else:
            print("No bot token set for lock client; running bot loop only")
            run_bot_loop()
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Ошибка при выполнении команды: {e}")
        send_status(f"```diff\n- Command error: {e}\n```", thread_id=MAIN_THREAD_ID)
    except Exception as e:
        print(f"[ERROR] {e}")
        send_status(f"```diff\n- Fatal error: {e}\n```", thread_id=MAIN_THREAD_ID)
