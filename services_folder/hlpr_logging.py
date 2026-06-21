import logging
import os
import requests
from queue import Queue
from threading import Thread
import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).parent.parent / "configs_folder" / "settings.json"
with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
    config_setings = json.load(f)

LOGGING_WEBHOOK_URL = config_setings.get("LOGGING_WEBHOOK_URL")
# Цвета для терминала
COLORS = {
    "DEBUG": "\033[38;5;245m",
    "INFO": "\033[38;5;39m",
    "WARNING": "\033[38;5;220m",
    "ERROR": "\033[38;5;203m",
    "CRITICAL": "\033[41m",
    "TIME": "\033[38;5;240m",
    "SOURCE": "\033[38;5;141m",
    "RESET": "\033[0m"
}


class ColorFormatter(logging.Formatter):
    def format(self, record):
        level_color = COLORS.get(record.levelname, COLORS["RESET"])
        time_color = COLORS["TIME"]
        source_color = COLORS["SOURCE"]

        msg = super().format(record)

        msg = msg.replace(
            record.asctime, f"{time_color}{record.asctime}{COLORS['RESET']}"
        ).replace(
            record.levelname, f"{level_color}{record.levelname}{COLORS['RESET']}"
        ).replace(
            f"{record.filename}:{record.lineno}",
            f"{source_color}{record.filename}:{record.lineno}{COLORS['RESET']}"
        )

        return msg


class WebhookHandler(logging.Handler):
    """Обработчик для отправки логов через вебхук"""
    
    def __init__(self, webhook_url: str, timeout: int = 5):
        """
        Args:
            webhook_url: URL вебхука
            timeout: Таймаут для HTTP запроса в секундах
        """
        super().__init__()
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.queue = Queue()
        self.worker_thread = Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
    
    def emit(self, record: logging.LogRecord):
        """Добавляет логи в очередь для отправки"""
        try:
            self.queue.put_nowait(record)
        except Exception:
            self.handleError(record)
    
    def _worker(self):
        """Рабочий поток для отправки логов"""
        while True:
            try:
                record = self.queue.get(timeout=1)
                self._send_log(record)
            except:
                continue
    
    def _send_log(self, record: logging.LogRecord):
        """Отправляет лог через вебхук"""
        try:
            message_text = self.format(record)
            
            # Если есть исключение, добавляем traceback
            if record.exc_info:
                traceback_text = self.formatException(record.exc_info)
                message_text = f"{message_text}\n{traceback_text}"
            
            # Обрезаем до лимита Discord (2000 символов)
            if len(message_text) > 2000:
                message_text = message_text[:1997] + "..."
            
            # Отправляем просто текст
            payload = {"content": message_text}
            
            requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout
            )
        except Exception as e:
            print(f"Ошибка отправки лога на вебхук: {e}")


logger = logging.getLogger("discord_bot")
logger.setLevel(logging.DEBUG)
logger.propagate = False

if not logger.handlers:
    # Консольный обработчик с цветами (INFO и выше)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = ColorFormatter(
        "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d — %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

# Обработчик для вебхука (INFO и выше) - добавляем к корневому логгеру для всех логгеров
if LOGGING_WEBHOOK_URL:
    webhook_handler = WebhookHandler(LOGGING_WEBHOOK_URL)
    webhook_handler.setLevel(logging.INFO)
    webhook_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(filename)s:%(lineno)d — %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )
    webhook_handler.setFormatter(webhook_formatter)
    
    # Добавляем к корневому логгеру, чтобы ловить все логи
    root_logger = logging.getLogger()
    root_logger.addHandler(webhook_handler)
    root_logger.setLevel(logging.INFO)

# Глушим шумные логгеры
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("aiosqlite.core").setLevel(logging.WARNING)
logging.getLogger("discord.http").setLevel(logging.ERROR)

__all__ = ["logger"]
