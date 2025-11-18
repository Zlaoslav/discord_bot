import subprocess
import sys
from pathlib import Path
import shutil
import time
import os

CURRENT_DIR = Path(__file__).parent.resolve()
BOT_FILE = CURRENT_DIR / "bot.py"
REPO_URL = "https://github.com/Zlaoslav/discord_bot"
REQUIREMENTS = CURRENT_DIR / "requirements.txt"

# ------------------- Функция для выполнения команды с прогрессом -------------------
def run_command(cmd, show_output=True):
    print(f"[CMD] {' '.join(cmd)}")
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        if show_output:
            # Простейший "прогресс-бар" в виде точек
            print(f". {line.strip()}")
    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, cmd)

# ------------------- Обновление репозитория -------------------
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

# ------------------- Обновление pip и установка зависимостей -------------------
def install_requirements():
    print("[INFO] Обновляем pip...")
    run_command([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    
    if REQUIREMENTS.exists():
        print(f"[INFO] Устанавливаем зависимости из {REQUIREMENTS.name}...")
        run_command([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)])
    else:
        print("[INFO] requirements.txt не найден, пропускаем установку зависимостей.")

# ------------------- Запуск бота с автоматическим перезапуском -------------------
def run_bot_loop():
    """Запускает бота в цикле. При завершении автоматически перезапускает."""
    first_run = True
    while True:
        if not BOT_FILE.exists():
            print(f"[ERROR] Не найден {BOT_FILE}")
            sys.exit(1)
        
        # При рестарте обновляем файлы с репозитория
        if not first_run:
            print("[INFO] Обновление файлов перед перезапуском...")
            try:
                git_update()
                install_requirements()
            except Exception as e:
                print(f"[WARNING] Ошибка при обновлении: {e}")
        
        print("[INFO] Запуск бота...")
        process = subprocess.Popen([sys.executable, str(BOT_FILE)],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,
                                   text=True)
        
        for line in process.stdout:
            print(line, end="")
        
        process.wait()
        exit_code = process.returncode
        print(f"[INFO] Бот завершил работу с кодом {exit_code}")
        
        first_run = False
        
        # После завершения ждём 2 секунды перед перезапуском
        print("[INFO] Перезапуск через 2 секунды...")
        time.sleep(2)

# ------------------- Основной блок -------------------
if __name__ == "__main__":
    try:
        git_update()
        install_requirements()
        run_bot_loop()
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Ошибка при выполнении команды: {e}")
    except Exception as e:
        print(f"[ERROR] {e}")
